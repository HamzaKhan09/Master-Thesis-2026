#!/usr/bin/env Rscript
# ---------------------------------------------------------------------------
# SUS / IPQ / VEQ questionnaire statistics. R counterpart of the testing and
# reliability halves of questionnaire_analysis.py.
#
# WHAT THIS SCRIPT DOES *NOT* DO -- deliberately:
# It does not re-derive the condition mapping. The evaluation form labels the two
# camera-based conditions "1st/2nd HMD-based system", which is POSITIONAL, and
# the mapping differs per participant (it follows the counterbalance schedule's
# planned order). That logic lives in exactly one place -- questionnaire_analysis.py
# -- because duplicating it would risk the two implementations silently
# disagreeing for roughly half the sample. This script consumes its output.
#
# Nor does it re-apply reverse coding: questionnaire_items_coded.csv already
# holds the coded values. The reverse key (SP2, INV3, REAL1, REAL3) was settled
# by checking the Google Form's actual anchor labels, not by fitting the data.
#
# psych::alpha() is used for reliability rather than a hand-rolled formula. It
# reports corrected item-total correlations (r.drop) directly, and with
# check.keys = TRUE it warns when an item runs opposite to its own scale -- the
# signature of a reverse-coding error. Both are reported below.
#
# Run from the Tools directory:
#   conda run -n r-thesis Rscript questionnaire.R
# ---------------------------------------------------------------------------

source("stats_common.R")
suppressPackageStartupMessages(library(psych))

SHORT <- c(HYTRACK = "HY", MetaQuest = "MQ", OptiTrack = "OT")

# Friedman + Holm-corrected pairwise Wilcoxon for one measure, formatted as the
# compact verdict string used in the write-up (e.g. "HY>MQ  HY~OT  MQ<OT").
verdict_string <- function(ph, wide) {
  parts <- character(nrow(ph))
  for (i in seq_len(nrow(ph))) {
    pr <- strsplit(ph$pair[i], " vs ", fixed = TRUE)[[1]]
    a <- SHORT[[pr[1]]]
    b <- SHORT[[pr[2]]]
    if (!is.na(ph$p_holm[i]) && ph$p_holm[i] < ALPHA) {
      rel <- if (mean(wide[[pr[1]]]) < mean(wide[[pr[2]]])) "<" else ">"
      parts[i] <- paste0(a, rel, b)
    } else {
      parts[i] <- paste0(a, "≈", b)
    }
  }
  paste(parts, collapse = "  ")
}

reliability_table <- function(items) {
  subscales <- unique(items$subscale)
  rows <- lapply(subscales, function(sc) {
    wide <- items %>%
      filter(.data$subscale == sc) %>%
      select(all_of(c("participant_id", "condition", "item", "value"))) %>%
      pivot_wider(names_from = "item", values_from = "value") %>%
      select(-all_of(c("participant_id", "condition")))

    k <- ncol(wide)
    if (k < 2) {
      return(tibble(subscale = sc, n_items = k, cronbach_alpha = NA_real_,
                    min_item_total_r = NA_real_, flagged_item = "",
                    psych_would_reverse = ""))
    }
    a <- suppressWarnings(psych::alpha(as.data.frame(wide), check.keys = FALSE,
                                       warnings = FALSE))
    r_drop <- a$item.stats$r.drop
    names(r_drop) <- rownames(a$item.stats)

    # Items psych's check.keys would flip: those whose corrected item-total
    # correlation is negative. Derived from r.drop rather than from
    # alpha(check.keys = TRUE)$keys, whose return shape varies across psych
    # versions. This is the automatic check that would have caught the IPQ
    # mis-keying immediately.
    flipped <- names(r_drop)[!is.na(r_drop) & r_drop < 0]

    tibble(subscale = sc, n_items = k,
           cronbach_alpha = a$total$raw_alpha,
           min_item_total_r = min(r_drop, na.rm = TRUE),
           flagged_item = if (min(r_drop, na.rm = TRUE) < 0)
             names(which.min(r_drop)) else "",
           psych_would_reverse = paste(flipped, collapse = ","))
  })
  bind_rows(rows)
}

main <- function() {
  # Optional suffix selecting a variant run (e.g. "_n19" for the sensitivity
  # check that drops P20). It picks the matching inputs written by
  # questionnaire_analysis.py --suffix and keeps the outputs separate, so a
  # variant can never overwrite the primary n = 20 results.
  ad <- analysis_dir()
  sfx <- if (length(commandArgs(TRUE))) commandArgs(TRUE)[1] else ""
  named <- function(stem) file.path(ad, paste0(stem, sfx, ".csv"))

  scores <- read_tidy_csv(named("questionnaire_scores_by_participant"))
  items <- read_tidy_csv(named("questionnaire_items_coded"))

  n_participants <- length(unique(scores$participant_id))
  cat(sprintf("Scored %d responses from %d participants\n",
              nrow(scores), n_participants))

  # ---- reliability -------------------------------------------------------
  rel <- reliability_table(items)
  cat("\n=== Reliability (Cronbach's alpha, psych::alpha) ===\n")
  for (i in seq_len(nrow(rel))) {
    r <- rel[i, ]
    a <- r$cronbach_alpha
    note <- if (is.na(a)) "n/a (single item)" else {
      lbl <- if (a >= 0.8) "very good" else if (a >= 0.7) "good" else
        if (a >= 0.6) "acceptable" else "POOR"
      sprintf("%.3f  %s", a, lbl)
    }
    flag <- if (nzchar(r$flagged_item)) paste0("   <-- CHECK CODING: ", r$flagged_item) else ""
    cat(sprintf("  %-24s k=%-3d alpha=%s%s\n", r$subscale, r$n_items, note, flag))
  }

  # ---- condition comparison ----------------------------------------------
  measures <- setdiff(names(scores), c("participant_id", "condition"))
  summaries <- list()
  posthocs <- list()
  test_rows <- list()

  for (m in measures) {
    wide <- scores %>%
      select(all_of(c("participant_id", "condition", m))) %>%
      rename(.v = all_of(m)) %>%
      pivot_wider(names_from = "condition", values_from = ".v") %>%
      drop_na(all_of(CONDITIONS)) %>%
      arrange(.data$participant_id)

    s <- omnibus(m, wide)
    ph <- posthoc(m, wide)
    summaries[[length(summaries) + 1]] <- s
    posthocs[[length(posthocs) + 1]] <- ph

    test_rows[[length(test_rows) + 1]] <- tibble(
      measure = m, n = s$n,
      friedman_chi2 = s$friedman_chi2, friedman_p = s$friedman_p,
      kendalls_w = s$kendalls_w, significant = s$omnibus_significant,
      pairwise = verdict_string(ph, wide),
      hytrack_mean = s$hytrack_mean, hytrack_sd = s$hytrack_sd,
      metaquest_mean = s$metaquest_mean, metaquest_sd = s$metaquest_sd,
      optitrack_mean = s$optitrack_mean, optitrack_sd = s$optitrack_sd
    )
  }

  tests <- bind_rows(test_rows)
  cat("\n=== Condition comparison (Friedman, Holm-corrected post-hoc) ===\n")
  for (i in seq_len(nrow(tests))) {
    r <- tests[i, ]
    cat(sprintf("  %-24s HY %6.2f  MQ %6.2f  OT %6.2f   p=%.4f%s  W=%.2f   %s\n",
                r$measure, r$hytrack_mean, r$metaquest_mean, r$optitrack_mean,
                r$friedman_p, if (r$significant) "*" else " ",
                r$kendalls_w, r$pairwise))
  }

  out_t <- named("questionnaire_tests_R")
  out_r <- named("questionnaire_reliability_R")
  out_p <- named("questionnaire_posthoc_R")
  write_tidy_csv(tests, out_t)
  write_tidy_csv(rel, out_r)
  write_tidy_csv(bind_rows(posthocs), out_p)
  cat("\nWrote", out_t, "\n")
  cat("Wrote", out_r, "\n")
  cat("Wrote", out_p, "\n")
}

main()
