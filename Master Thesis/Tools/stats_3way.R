#!/usr/bin/env Rscript
# ---------------------------------------------------------------------------
# Three-condition (HYTRACK / MetaQuest / OptiTrack) within-subjects comparison
# of the objective tracking metrics. R counterpart of stats_analysis_3way.py.
#
# METRICS COVERED: only the ones computed *within* a single condition's own data
# stream -- whole-body limb jitter, legs-only jitter, and tracking dropout.
# These never compare across sessions, so the no-simultaneous-capture problem
# does not touch them. MPJPE/accuracy is deliberately absent: it requires frame
# correspondence between a condition and OptiTrack that does not exist (see the
# project memory note on the invalidated MPJPE analysis).
#
# Reads the tidy CSVs produced by the Python pipeline; writes R-suffixed outputs
# alongside the Python ones so diff_r_vs_python.py can compare them.
#
# Run from the Tools directory:
#   conda run -n r-thesis Rscript stats_3way.R
# ---------------------------------------------------------------------------

source("stats_common.R")

# Same joint sets as the Python analysis. In both HYTRACK's and MetaQuest's rigs
# the head and shoulders move almost rigidly with the hip, so their frame-to-frame
# displacement reflects rig construction rather than sensing and is excluded from
# the limb-jitter metric.
JITTER_RIG_LOCKED_JOINTS <- c("left_hip", "right_hip", "head",
                              "left_shoulder", "right_shoulder")
LEG_JOINTS <- c("left_knee", "right_knee", "left_ankle", "right_ankle")

main <- function() {
  ad <- analysis_dir()
  jitter <- read_tidy_csv(file.path(ad, "jitter_by_participant_joint.csv"))
  continuity <- read_tidy_csv(file.path(ad, "tracking_continuity_by_participant.csv"))

  metrics <- list(
    list(name = "Jitter, limb joints (RMS m)",
         wide = to_wide(jitter, "jitter_rms_m", drop_joints = JITTER_RIG_LOCKED_JOINTS)),
    list(name = "Jitter, legs only (RMS m)",
         wide = to_wide(jitter, "jitter_rms_m", keep_joints = LEG_JOINTS)),
    list(name = "Tracking dropout (%)",
         wide = to_wide(continuity, "pct_gaps_over_1_5x_expected"))
  )

  summaries <- list()
  posthocs <- list()
  for (m in metrics) {
    s <- omnibus(m$name, m$wide)
    ph <- posthoc(m$name, m$wide)
    report(s, ph)
    summaries[[length(summaries) + 1]] <- s
    posthocs[[length(posthocs) + 1]] <- ph
  }

  out_s <- file.path(ad, "friedman_3way_summary_R.csv")
  out_p <- file.path(ad, "friedman_3way_posthoc_R.csv")
  write_tidy_csv(bind_rows(summaries), out_s)
  write_tidy_csv(bind_rows(posthocs), out_p)
  cat("\nWrote", out_s, "\n")
  cat("Wrote", out_p, "\n")
}

main()
