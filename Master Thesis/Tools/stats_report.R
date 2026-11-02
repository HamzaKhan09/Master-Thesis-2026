#!/usr/bin/env Rscript
# ---------------------------------------------------------------------------
# The three rows of the technical results table, computed in R.
#
# R is the reporting source for statistics, so the numbers printed in the report
# table must come from here rather than from a parallel Python computation --
# otherwise the thesis text could quote an R p-value while the figure beside it
# shows SciPy's. The two differ for the dropout row, where SciPy abandons the
# exact Wilcoxon null distribution as soon as any zero difference is present and
# R does not (see diff_r_vs_python.py for the full attribution).
#
# plot_results_table.py renders results_table_rows_R.csv and computes nothing.
#
# All rows compare the three conditions on equal footing: Friedman omnibus with
# Holm-corrected pairwise Wilcoxon post-hoc.
#
# WITHDRAWN 2026-09-04: the "Leg length" row that used to appear here compared
# which consumer system's segment length landed closer to OptiTrack's. All three
# conditions turned out to log the retargeted avatar's rig, not the participant's
# anatomy, so the comparison had no ground truth on either side -- see
# project_mpjpe_invalid_no_simultaneous_capture / project_accuracy_without_ground_truth
# in the evaluation log. Do not re-add it.
#
# Run from the Tools directory:
#   conda run -n r-thesis Rscript stats_report.R
# ---------------------------------------------------------------------------

source("stats_common.R")

JITTER_RIG_LOCKED_JOINTS <- c("left_hip", "right_hip", "head",
                              "left_shoulder", "right_shoulder")
LEG_JOINTS <- c("left_knee", "right_knee", "left_ankle", "right_ankle")
M_TO_CM <- 100

SHORT <- c(HYTRACK = "HY", MetaQuest = "MQ", OptiTrack = "OT")

# Shared row skeleton so every row carries the same columns.
row_template <- function(measure, wide, dp, test, p, effect_label, effect_value,
                         pairwise) {
  out <- tibble(measure = measure, n = nrow(wide), dp = dp, test = test,
                p = p, effect_label = effect_label, effect_value = effect_value,
                pairwise = pairwise)
  for (cond in CONDITIONS) {
    out[[paste0(tolower(cond), "_mean")]] <- mean(wide[[cond]])
    out[[paste0(tolower(cond), "_sd")]] <- sd(wide[[cond]])
  }
  out
}

three_way_row <- function(measure, wide, dp, ph) {
  s <- omnibus(measure, wide)

  verdicts <- character(nrow(ph))
  for (i in seq_len(nrow(ph))) {
    pr <- strsplit(ph$pair[i], " vs ", fixed = TRUE)[[1]]
    a <- SHORT[[pr[1]]]
    b <- SHORT[[pr[2]]]
    if (!is.na(ph$p_holm[i]) && ph$p_holm[i] < ALPHA) {
      rel <- if (mean(wide[[pr[1]]]) < mean(wide[[pr[2]]])) "<" else ">"
      verdicts[i] <- paste0(a, rel, b)
    } else {
      verdicts[i] <- paste0(a, "≈", b)
    }
  }

  row_template(measure, wide, dp, "Friedman", s$friedman_p,
               "W", s$kendalls_w, paste(verdicts, collapse = "   "))
}

main <- function() {
  ad <- analysis_dir()
  jit <- read_tidy_csv(file.path(ad, "jitter_by_participant_joint.csv"))
  cont <- read_tidy_csv(file.path(ad, "tracking_continuity_by_participant.csv"))

  # The stored jitter column is displacement between consecutive frames; dividing
  # by that trial's own mean frame interval converts it to a velocity (the MPJVE
  # metric family), and using each row's own dt also removes the small 5.70-5.72 Hz
  # sampling-rate differences between conditions.
  jit$velocity_cm_s <- jit$jitter_rms_m / jit$mean_frame_dt_s * M_TO_CM

  # The three-way metrics, each computed once so the row and its post-hoc detail
  # cannot disagree.
  metrics <- list(
    list(name = "Motion fidelity, limbs\n(cm/s)", dp = 2,
         wide = to_wide(jit, "velocity_cm_s",
                        drop_joints = JITTER_RIG_LOCKED_JOINTS)),
    list(name = "Motion fidelity, legs\n(cm/s)", dp = 2,
         wide = to_wide(jit, "velocity_cm_s", keep_joints = LEG_JOINTS)),
    list(name = "Robustness\n(% frames lost)", dp = 3,
         wide = to_wide(cont, "pct_gaps_over_1_5x_expected"))
  )

  row_list <- list()
  ph_list <- list()
  for (m in metrics) {
    ph <- posthoc(m$name, m$wide)
    row_list[[length(row_list) + 1]] <- three_way_row(m$name, m$wide, m$dp, ph)
    ph_list[[length(ph_list) + 1]] <- ph
  }
  rows <- bind_rows(row_list)

  out <- file.path(ad, "results_table_rows_R.csv")
  write_tidy_csv(rows, out)

  # Pairwise detail, so the figure captions can quote Holm-corrected p-values
  # instead of restating them by hand.
  out_ph <- file.path(ad, "results_table_posthoc_R.csv")
  write_tidy_csv(bind_rows(ph_list), out_ph)

  for (i in seq_len(nrow(rows))) {
    r <- rows[i, ]
    cat(sprintf("  %-32s p=%-9.4f %s=%+.2f   %s\n",
                gsub("\n", " ", r$measure), r$p, r$effect_label,
                r$effect_value, r$pairwise))
  }
  cat("\nWrote", out, "\n")
  cat("Wrote", out_ph, "\n")
}

main()
