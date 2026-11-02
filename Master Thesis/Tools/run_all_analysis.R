# ===========================================================================
#  RUN THE WHOLE STATISTICAL ANALYSIS
#
#  Open this file in RStudio and press the "Source" button (top right of the
#  editor pane), or Ctrl+Shift+S. Everything else is automatic.
#
#  BEFORE THE FIRST RUN, once only, paste this into the Console and press Enter:
#      install.packages(c("dplyr", "tidyr", "tibble", "psych"))
#
#  IF YOU GET AN ERROR ABOUT stats_common.R NOT BEING FOUND:
#      In RStudio go to  Session -> Set Working Directory -> To Source File
#      Location, then press Source again. R needs to be "standing in" the
#      Tools folder for the scripts to find the data.
# ===========================================================================

cat("\n")
cat("===========================================================\n")
cat(" HYTRACK -- statistical analysis\n")
cat("===========================================================\n\n")

# --- check we are in the right folder --------------------------------------
if (!file.exists("stats_common.R")) {
  stop("Cannot find stats_common.R.\n",
       "  You are currently in: ", getwd(), "\n",
       "  In RStudio: Session -> Set Working Directory -> To Source File Location,\n",
       "  then press Source again.", call. = FALSE)
}

# --- check the packages are installed --------------------------------------
needed <- c("dplyr", "tidyr", "tibble", "psych")
missing <- needed[!vapply(needed, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing)) {
  stop("Missing R packages: ", paste(missing, collapse = ", "), "\n",
       "  Paste this into the Console and press Enter:\n",
       '  install.packages(c("', paste(missing, collapse = '", "'), '"))',
       call. = FALSE)
}

# --- run each analysis in order --------------------------------------------
# Each script prints its own results and writes a CSV next to the data.
steps <- list(
  c("stats_3way.R",   "Motion fidelity and dropout, all three conditions"),
  c("stats_report.R", "The four rows of the results table"),
  c("skeleton.R",     "Skeleton consistency: legs vs arms within each system"),
  c("questionnaire.R", "Questionnaire scores, reliability and comparisons"),
  c("preferences.R",  "Forced-choice preferences from the final questionnaire")
)

for (i in seq_along(steps)) {
  name <- steps[[i]][1]
  what <- steps[[i]][2]
  cat("\n\n")
  cat("-----------------------------------------------------------\n")
  cat(sprintf(" STEP %d of %d:  %s\n", i, length(steps), what))
  cat(sprintf(" (script: %s)\n", name))
  cat("-----------------------------------------------------------\n")
  source(name, local = new.env(), echo = FALSE)
}

cat("\n\n")
cat("===========================================================\n")
cat(" DONE. All results were also written as .csv files into\n")
cat(" StudyData/analysis/ -- the ones ending in _R.csv are these.\n")
cat("===========================================================\n\n")
