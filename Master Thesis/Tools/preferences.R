#!/usr/bin/env Rscript
# ---------------------------------------------------------------------------
# Forced-choice preference items: is the observed split different from chance?
#
# Three-option items are tested against a uniform null (no preference among the
# three systems) with a chi-square goodness-of-fit test; the two-option item
# uses an exact binomial test. Counts come from preference_analysis.py, which
# owns the positional-label mapping.
#
# Run from the Tools directory:
#   conda run -n r-thesis Rscript preferences.R
# ---------------------------------------------------------------------------

source("stats_common.R")

TWO_WAY <- "Marker-based vs markerless"

main <- function() {
  ad <- analysis_dir()
  # Optional suffix selecting a variant run (e.g. "_n19"), matching the inputs
  # written by preference_analysis.py --suffix. Keeps outputs separate so a
  # variant can never overwrite the primary results.
  sfx <- if (length(commandArgs(TRUE))) commandArgs(TRUE)[1] else ""
  counts <- read_tidy_csv(file.path(ad, paste0("preference_counts", sfx, ".csv")))

  rows <- list()
  for (item in unique(counts$item)) {
    sub <- counts[counts$item == item, ]
    n <- sum(sub$n)

    if (item == TWO_WAY) {
      # exact binomial against a 50/50 split
      top <- sub[which.max(sub$n), ]
      bt <- binom.test(top$n, n, p = 0.5)
      rows[[length(rows) + 1]] <- tibble(
        item = item, n = n, test = "Binomial (exact)",
        top_choice = top$choice, top_n = top$n,
        top_pct = top$n / n * 100, p = bt$p.value)
    } else {
      # three systems were available, so absent options count as zero
      obs <- c(HYTRACK = 0, MetaQuest = 0, OptiTrack = 0)
      obs[sub$choice] <- sub$n
      ct <- suppressWarnings(chisq.test(obs, p = rep(1 / 3, 3)))
      top <- sub[which.max(sub$n), ]
      rows[[length(rows) + 1]] <- tibble(
        item = item, n = n,
        test = sprintf("Chi-square GOF, chi2(%d)=%.2f", ct$parameter, ct$statistic),
        top_choice = top$choice, top_n = top$n,
        top_pct = top$n / n * 100, p = ct$p.value)
    }
  }

  out <- bind_rows(rows)
  out$p_holm <- p.adjust(out$p, method = "holm")
  out$significant <- out$p_holm < ALPHA

  path <- file.path(ad, paste0("preference_tests_R", sfx, ".csv"))
  write_tidy_csv(out, path)

  cat(sprintf("=== Forced-choice preferences (n = %d) ===\n", max(out$n)))
  for (i in seq_len(nrow(out))) {
    r <- out[i, ]
    cat(sprintf("  %-30s %-34s top: %-12s %2d/%d (%.0f%%)  p=%.4f%s\n",
                r$item, r$test, r$top_choice, r$top_n, r$n, r$top_pct,
                r$p_holm, if (r$significant) "*" else " "))
  }
  cat("\n  p is Holm-corrected across the five items.\n")
  cat("\nWrote", path, "\n")
}

main()
