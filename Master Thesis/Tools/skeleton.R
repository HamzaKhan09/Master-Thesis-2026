#!/usr/bin/env Rscript
# ---------------------------------------------------------------------------
# Skeleton consistency: is a system's LEG tracking more or less physically
# consistent than its OWN arm tracking?
#
# This within-system contrast is the informative comparison, not the raw
# across-system one. In both HMD conditions the arms come from the same Quest
# tracking, so arms act as a control; the legs are the manipulation.
#
#   HYTRACK   legs noisier than arms  -> genuine per-frame estimation error
#   MetaQuest legs MORE rigid than arms -> a sensor cannot be more precise on a
#             limb it never observes; that is the signature of a synthesised leg
#   OptiTrack legs == arms            -> a real reference system, precise on both
#
# Paired Wilcoxon signed-rank within each condition, Holm-corrected across the
# three conditions.
#
# Run from the Tools directory:
#   conda run -n r-thesis Rscript skeleton.R
# ---------------------------------------------------------------------------

source("stats_common.R")

main <- function() {
  ad <- analysis_dir()
  cons <- read_tidy_csv(file.path(ad, "skeleton_consistency_by_participant.csv"))

  rows <- list()
  for (cond in CONDITIONS) {
    w <- cons %>%
      filter(.data$condition == cond) %>%
      select(all_of(c("participant_id", "group", "sd_cm"))) %>%
      pivot_wider(names_from = "group", values_from = "sd_cm") %>%
      drop_na(all_of(c("Legs", "Arms")))

    wt <- suppressWarnings(wilcox.test(w$Legs, w$Arms, paired = TRUE))
    rows[[length(rows) + 1]] <- tibble(
      condition = cond, n = nrow(w),
      legs_mean_cm = mean(w$Legs), legs_sd_cm = sd(w$Legs),
      arms_mean_cm = mean(w$Arms), arms_sd_cm = sd(w$Arms),
      ratio_legs_over_arms = mean(w$Legs) / mean(w$Arms),
      n_legs_gt_arms = sum(w$Legs > w$Arms),
      p_raw = wt$p.value,
      rank_biserial_r = rank_biserial(w$Legs, w$Arms)
    )
  }

  out <- bind_rows(rows)
  out$p_holm <- p.adjust(out$p_raw, method = "holm")
  out$significant <- out$p_holm < ALPHA

  path <- file.path(ad, "skeleton_consistency_tests_R.csv")
  write_tidy_csv(out, path)

  cat("=== Legs vs own arms, within each system (paired Wilcoxon) ===\n")
  for (i in seq_len(nrow(out))) {
    r <- out[i, ]
    verdict <- if (!r$significant) "no difference" else if (r$ratio_legs_over_arms > 1)
      "legs NOISIER than own arms" else "legs MORE RIGID than own arms"
    cat(sprintf("  %-10s n=%2d  legs %.4f cm  arms %.4f cm  ratio %5.2f  "
                , r$condition, r$n, r$legs_mean_cm, r$arms_mean_cm,
                r$ratio_legs_over_arms))
    cat(sprintf("p=%.5g%s  (%d/%d)  -> %s\n", r$p_holm,
                if (r$significant) "*" else " ",
                r$n_legs_gt_arms, r$n, verdict))
  }
  cat("\nWrote", path, "\n")
}

main()
