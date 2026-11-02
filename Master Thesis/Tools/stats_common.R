# ---------------------------------------------------------------------------
# Shared helpers for the R statistics layer.
#
# DIVISION OF LABOUR: Python owns the technical evaluation pipeline (parsing the
# joint_positions logs, reconstructing trial windows, computing per-joint
# velocities, segment lengths, dropout, and the questionnaire condition mapping).
# R owns the STATISTICS, reading the tidy per-participant CSVs that pipeline
# emits. Nothing is recomputed in both places except the tests themselves, which
# is the point -- the two implementations are diffed against each other by
# diff_r_vs_python.py.
#
# Every test here mirrors the Python one deliberately:
#   omnibus       Friedman
#   omnibus ES    Kendall's W = chi2 / (n * (k - 1))
#   post-hoc      pairwise Wilcoxon signed-rank, Holm-corrected
#   post-hoc ES   matched-pairs rank-biserial (T+ - T-) / (T+ + T-)
# ---------------------------------------------------------------------------

suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(tibble)
})

# Base-R I/O rather than readr: the conda build of readr on Windows fails to load
# (its tzdb shared object is broken). check.names = FALSE keeps column names such
# as "SUS (0-100)" and "Leg embodiment*" intact so they still match the Python
# output; na = "" matches pandas' default CSV representation of missing values.
read_tidy_csv <- function(path) {
  read.csv(path, stringsAsFactors = FALSE, check.names = FALSE)
}

write_tidy_csv <- function(x, path) {
  write.csv(x, path, row.names = FALSE, na = "")
}

CONDITIONS <- c("HYTRACK", "MetaQuest", "OptiTrack")
ALPHA <- 0.05

# Locate StudyData/analysis whether the script is run from Tools/ or the repo root.
analysis_dir <- function() {
  candidates <- c(Sys.getenv("THESIS_ANALYSIS_DIR"),
                  file.path("..", "StudyData", "analysis"),
                  file.path("StudyData", "analysis"),
                  file.path(".", "StudyData", "analysis"))
  for (p in candidates) {
    if (nzchar(p) && dir.exists(p)) return(normalizePath(p, winslash = "/"))
  }
  stop("Could not locate StudyData/analysis. Run from the Tools directory, or ",
       "set THESIS_ANALYSIS_DIR.", call. = FALSE)
}

# One value per participant per condition, keeping only participants measured
# under all three conditions. Mirrors wide_all_conditions() in Python.
to_wide <- function(df, value_col, keep_joints = NULL, drop_joints = NULL) {
  if (!is.null(keep_joints)) df <- df %>% filter(.data$joint %in% keep_joints)
  if (!is.null(drop_joints)) df <- df %>% filter(!(.data$joint %in% drop_joints))

  wide <- df %>%
    group_by(.data$participant_id, .data$condition) %>%
    summarise(.v = mean(.data[[value_col]], na.rm = TRUE), .groups = "drop") %>%
    pivot_wider(names_from = "condition", values_from = ".v")

  missing <- setdiff(CONDITIONS, names(wide))
  if (length(missing)) {
    stop("missing condition(s) ", paste(missing, collapse = ", "),
         " for ", value_col, call. = FALSE)
  }
  wide %>%
    select(all_of(c("participant_id", CONDITIONS))) %>%
    drop_na(all_of(CONDITIONS)) %>%
    arrange(.data$participant_id)
}

# Matched-pairs rank-biserial correlation. Positive => x tends to exceed y.
# Zero differences are dropped, per convention. Implemented directly rather than
# via rstatix::wilcox_effsize, which returns Z/sqrt(N) -- a DIFFERENT effect size
# that would not be comparable to the Python column of the same name.
rank_biserial <- function(x, y) {
  d <- x - y
  d <- d[d != 0]
  if (!length(d)) return(NA_real_)
  r <- rank(abs(d))
  t_plus <- sum(r[d > 0])
  t_minus <- sum(r[d < 0])
  total <- t_plus + t_minus
  if (total == 0) NA_real_ else (t_plus - t_minus) / total
}

# R uses an exact Wilcoxon null distribution only when there are no ties among
# the absolute differences and n < 50; otherwise it falls back to a normal
# approximation WITH a continuity correction. SciPy's default applies no
# continuity correction. Knowing which branch ran is what makes a p-value
# difference against Python explainable rather than mysterious.
exact_possible <- function(x, y) {
  d <- x - y
  d <- d[d != 0]
  length(d) > 0 && length(d) < 50 && !any(duplicated(abs(d)))
}

# Friedman + Kendall's W + per-condition Shapiro-Wilk (reported as context for
# the non-parametric choice, never used to switch tests).
omnibus <- function(name, wide) {
  m <- as.matrix(wide[, CONDITIONS])
  n <- nrow(m)
  k <- length(CONDITIONS)
  ft <- friedman.test(m)

  row <- tibble(
    metric = name, n = n, k_conditions = k,
    friedman_chi2 = unname(ft$statistic),
    friedman_df = unname(ft$parameter),
    friedman_p = ft$p.value,
    kendalls_w = unname(ft$statistic) / (n * (k - 1)),
    omnibus_significant = ft$p.value < ALPHA
  )
  for (cond in CONDITIONS) {
    v <- wide[[cond]]
    row[[paste0(tolower(cond), "_mean")]] <- mean(v)
    row[[paste0(tolower(cond), "_sd")]] <- sd(v)
    row[[paste0(tolower(cond), "_shapiro_p")]] <-
      if (length(unique(v)) > 1) shapiro.test(v)$p.value else NA_real_
  }
  row
}

# All three pairwise Wilcoxon signed-rank tests, Holm-corrected within the metric.
posthoc <- function(name, wide) {
  pairs <- combn(CONDITIONS, 2, simplify = FALSE)
  rows <- lapply(pairs, function(pr) {
    x <- wide[[pr[1]]]
    y <- wide[[pr[2]]]
    if (all(x - y == 0)) {
      return(tibble(metric = name, pair = paste(pr[1], "vs", pr[2]), n = nrow(wide),
                    mean_a = mean(x), mean_b = mean(y), median_diff = 0,
                    wilcoxon_stat = NA_real_, wilcoxon_v = NA_real_,
                    p_raw = NA_real_, p_raw_nocorrect = NA_real_, exact_used = NA,
                    n_zero_dropped = nrow(wide), n_tied_abs = 0L,
                    rank_biserial_r = NA_real_))
    }
    wt <- suppressWarnings(wilcox.test(x, y, paired = TRUE))
    wt_nc <- suppressWarnings(
      wilcox.test(x, y, paired = TRUE, exact = FALSE, correct = FALSE))

    # Signed-rank bookkeeping, so a difference against SciPy can be attributed
    # to a specific cause rather than guessed at.
    d <- x - y
    n_zero <- sum(d == 0)
    dz <- d[d != 0]
    rk <- rank(abs(dz))
    t_plus <- sum(rk[dz > 0])
    t_minus <- sum(rk[dz < 0])

    tibble(
      metric = name, pair = paste(pr[1], "vs", pr[2]), n = nrow(wide),
      mean_a = mean(x), mean_b = mean(y), median_diff = median(d),
      # R reports V = T+; SciPy reports min(T+, T-). Both are emitted so the
      # column named wilcoxon_stat is directly comparable to the Python output.
      wilcoxon_stat = min(t_plus, t_minus),
      wilcoxon_v = unname(wt$statistic),
      p_raw = wt$p.value,            # R default: exact when possible, else corrected
      p_raw_nocorrect = wt_nc$p.value,  # matches SciPy's default (no continuity corr.)
      exact_used = exact_possible(x, y),
      n_zero_dropped = n_zero,
      n_tied_abs = sum(duplicated(abs(dz))),
      rank_biserial_r = rank_biserial(x, y)
    )
  })
  out <- bind_rows(rows)
  out$p_holm <- p.adjust(out$p_raw, method = "holm")
  out$significant_after_holm <- !is.na(out$p_holm) & out$p_holm < ALPHA
  out
}

report <- function(s, ph) {
  cat(sprintf("\n=== %s (n=%d, all 3 conditions) ===\n", s$metric, s$n))
  for (cond in CONDITIONS) {
    key <- tolower(cond)
    cat(sprintf("  %-10s: mean=%.5f  sd=%.5f   (Shapiro p=%.4f)\n", cond,
                s[[paste0(key, "_mean")]], s[[paste0(key, "_sd")]],
                s[[paste0(key, "_shapiro_p")]]))
  }
  cat(sprintf("  Friedman: chi2(%d)=%.3f, p=%.5g, Kendall's W=%.3f  -> %s\n",
              s$friedman_df, s$friedman_chi2, s$friedman_p, s$kendalls_w,
              if (s$omnibus_significant) "SIGNIFICANT" else "not significant"))
  if (!s$omnibus_significant) {
    cat("  (post-hoc pairs shown for completeness; omnibus was not significant,\n",
        "   so these should not be interpreted as findings)\n", sep = "")
  }
  cat("  post-hoc (Wilcoxon, Holm-corrected):\n")
  for (i in seq_len(nrow(ph))) {
    r <- ph[i, ]
    if (is.na(r$p_raw)) {
      cat(sprintf("    %-26s no test possible (all differences zero)\n", r$pair))
      next
    }
    cat(sprintf("    %-26s p_raw=%.5g  p_holm=%.5g%s   rank-biserial r=%+.3f  [%s]\n",
                r$pair, r$p_raw, r$p_holm,
                if (r$significant_after_holm) "*" else " ",
                r$rank_biserial_r,
                if (isTRUE(r$exact_used)) "exact" else "normal approx."))
  }
}
