"""
Summary statistics table for the SUS / IPQ / VEQ / custom-item questionnaire
results -- the subjective-measures companion to results_table.png.

PROVENANCE: this script RENDERS ONLY. Every number comes from
questionnaire_tests_R.csv, produced by questionnaire.R, because R is the
reporting source for statistics (see stats_report.R / results_table_rows_R.csv
for the same convention on the technical side).

Rows are all ten administered measures, ordered by ascending omnibus p (most to
least discriminating), matching EVALUATION_LOG.md Section 4's table order.

Produces: StudyData/analysis/figures/questionnaire_results_table.png

Run with:  conda run -n r-thesis Rscript questionnaire.R      (first)
           MPLBACKEND=Agg conda run -n thesis-eval python plot_questionnaire_table.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from plot_study_data_simple import (
    ANALYSIS_DIR, FIG_DIR, INK, INK_MUTED, GRIDLINE, BASELINE,
)

R_TESTS = "questionnaire_tests_R.csv"
R_SOURCES = ["questionnaire_scores_by_participant.csv", "questionnaire_items_coded.csv"]
CONDITIONS = ["HYTRACK", "MetaQuest", "OptiTrack"]

COLUMNS = ["Measure", "n", "HYTRACK\n(mean ± SD)", "MetaQuest\n(mean ± SD)",
           "OptiTrack\n(mean ± SD)", "Test", "p", "Effect\nsize",
           "Pairwise result\n(Holm-corrected)"]
COL_X = [0.005, 0.150, 0.235, 0.365, 0.495, 0.600, 0.675, 0.735, 0.995]
COL_ALIGN = ["left", "center", "center", "center", "center",
             "center", "center", "center", "right"]


def fmt(mean: float, sd: float) -> str:
    return f"{mean:.2f} ± {sd:.2f}"


def fmt_p(p: float) -> str:
    if not np.isfinite(p):
        return "--"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def load_rows() -> list[dict]:
    """Read the R-computed rows, refusing to render anything stale."""
    r_path = ANALYSIS_DIR / R_TESTS
    if not r_path.exists():
        raise SystemExit(
            f"{R_TESTS} not found -- the statistics are computed in R.\n"
            f"Run first:  conda run -n r-thesis Rscript questionnaire.R")

    r_mtime = r_path.stat().st_mtime
    stale = [s for s in R_SOURCES
             if (ANALYSIS_DIR / s).exists()
             and (ANALYSIS_DIR / s).stat().st_mtime > r_mtime]
    if stale:
        raise SystemExit(
            f"{R_TESTS} is older than its source data ({', '.join(stale)}).\n"
            f"Re-run:  conda run -n r-thesis Rscript questionnaire.R")

    df = pd.read_csv(r_path).sort_values("friedman_p").reset_index(drop=True)
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "Measure": str(r["measure"]), "n": str(int(r["n"])),
            **{c: fmt(r[f"{c.lower()}_mean"], r[f"{c.lower()}_sd"]) for c in CONDITIONS},
            "Test": "Friedman", "p": fmt_p(float(r["friedman_p"])),
            "Effect": f"W = {r['kendalls_w']:.2f}", "Pairwise": str(r["pairwise"]),
        })
    return rows


def make_table(rows: list[dict]):
    n_rows = len(rows) + 1
    fig, ax = plt.subplots(figsize=(16.5, 0.7 + n_rows * 0.92))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, n_rows)
    ax.axis("off")

    for x, label, align in zip(COL_X, COLUMNS, COL_ALIGN):
        ax.text(x, n_rows - 0.5, label, ha=align, va="center", fontsize=10.5,
                color=INK, fontweight="bold", linespacing=1.3)
    ax.axhline(n_rows - 1, color=INK, linewidth=1.2)

    keys = ["Measure", "n", *CONDITIONS, "Test", "p", "Effect", "Pairwise"]
    for i, row in enumerate(rows):
        y = n_rows - 1.5 - i
        if i % 2 == 1:
            ax.axhspan(y - 0.5, y + 0.5, color=GRIDLINE, alpha=0.5, zorder=0)
        for x, key, align in zip(COL_X, keys, COL_ALIGN):
            ax.text(x, y, row[key], ha=align, va="center", fontsize=10, color=INK,
                    fontweight="bold" if align == "left" else "normal", linespacing=1.3)
        ax.axhline(y - 0.5, color=BASELINE, linewidth=0.6)

    fig.text(0.005, 0.012,
             "HY = HYTRACK   MQ = MetaQuest   OT = OptiTrack.   "
             "'<' means significantly lower, '≈' means no significant difference.   "
             "p < 0.05 = statistically significant.\n"
             "W = Kendall's W (0.1 small, 0.3 moderate, 0.5 large).   "
             "* = custom item, not from a validated instrument.   "
             "SUS is scored 0-100; every other measure is a 7-point rating.   "
             "IPQ Involvement's omnibus reaches p<0.05 but no individual pair "
             "survives Holm correction -- do not read a pairwise story into that row.",
             fontsize=8.5, color=INK_MUTED, ha="left", va="bottom", linespacing=1.8)

    fig.tight_layout(rect=(0, 0.09, 1, 1))
    fig.savefig(FIG_DIR / "questionnaire_results_table.png", dpi=300, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    rows = load_rows()
    make_table(rows)
    for r in rows:
        measure = r["Measure"].replace("\n", " ")
        print(f"  {measure:<26} p={r['p']:<8} {r['Effect']:<12} {r['Pairwise']}")
    print(f"\nWrote {FIG_DIR / 'questionnaire_results_table.png'}  (numbers computed in R)")


if __name__ == "__main__":
    main()
