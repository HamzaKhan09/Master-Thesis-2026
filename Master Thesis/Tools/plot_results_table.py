"""
Summary statistics table for the technical evaluation -- the valid replacement
for stats_table.png, whose Accuracy row was built on MPJPE and is therefore
invalid (see project_mpjpe_invalid_no_simultaneous_capture).

PROVENANCE: this script RENDERS ONLY. Every number comes from
results_table_rows_R.csv, produced by stats_report.R, because R is the reporting
source for statistics. It used to recompute the statistics here in Python, which
risked the thesis text quoting an R p-value while the table beside it showed
SciPy's -- the two genuinely differ on the Robustness row, where SciPy abandons
the exact Wilcoxon null distribution as soon as any zero difference is present
and R does not (diff_r_vs_python.py attributes every difference).

The "cannot silently drift" property is preserved by a freshness check instead:
if any source CSV is newer than the R output, this refuses to render rather than
drawing stale numbers.

Rows, matching the report figures plus robustness:
  - Motion fidelity, limbs (cm/s)  -- mean joint velocity
  - Motion fidelity, legs (cm/s)   -- mean joint velocity
  - Robustness (% frames)          -- timing-gap dropout

WITHDRAWN 2026-09-04: this table used to carry a "Leg length (cm)" row. It
compared which consumer system's segment length landed closer to OptiTrack's,
but all three conditions log the retargeted avatar's rig rather than the
participant's anatomy, so there was no ground truth on either side. Removed
in stats_report.R -- do not re-add it here.

Produces: StudyData/analysis/figures/results_table.png

Run with:  conda run -n r-thesis Rscript stats_report.R      (first)
           MPLBACKEND=Agg conda run -n thesis-eval python plot_results_table.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from plot_study_data_simple import (
    ANALYSIS_DIR, FIG_DIR, INK, INK_MUTED, GRIDLINE, BASELINE,
)
from stats_analysis_3way import CONDITIONS

R_ROWS = "results_table_rows_R.csv"
R_SOURCES = ["jitter_by_participant_joint.csv",
             "tracking_continuity_by_participant.csv"]

COLUMNS = ["Measure", "n", "HYTRACK\n(mean ± SD)", "MetaQuest\n(mean ± SD)",
           "OptiTrack\n(mean ± SD)", "Test", "p", "Effect\nsize",
           "Pairwise result\n(Holm-corrected)"]
COL_X = [0.005, 0.150, 0.235, 0.365, 0.495, 0.600, 0.675, 0.735, 0.995]
COL_ALIGN = ["left", "center", "center", "center", "center",
             "center", "center", "center", "right"]


def fmt(mean: float, sd: float, dp: int) -> str:
    return f"{mean:.{dp}f} ± {sd:.{dp}f}"


def fmt_p(p: float) -> str:
    if not np.isfinite(p):
        return "--"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def load_rows() -> list[dict]:
    """Read the R-computed rows, refusing to render anything stale."""
    r_path = ANALYSIS_DIR / R_ROWS
    if not r_path.exists():
        raise SystemExit(
            f"{R_ROWS} not found -- the statistics are computed in R.\n"
            f"Run first:  conda run -n r-thesis Rscript stats_report.R")

    r_mtime = r_path.stat().st_mtime
    stale = [s for s in R_SOURCES
             if (ANALYSIS_DIR / s).exists()
             and (ANALYSIS_DIR / s).stat().st_mtime > r_mtime]
    if stale:
        raise SystemExit(
            f"{R_ROWS} is older than its source data ({', '.join(stale)}).\n"
            f"Re-run:  conda run -n r-thesis Rscript stats_report.R")

    df = pd.read_csv(r_path)
    rows = []
    for _, r in df.iterrows():
        dp = int(r["dp"])
        # R writes CRLF inside quoted multi-line cells on Windows; the stray \r
        # has no glyph and renders as a box in the PNG.
        def clean(v) -> str:
            return str(v).replace("\r\n", "\n").replace("\r", "\n")
        # rank-biserial is directional so it keeps its sign; Kendall's W is not.
        effect = (f"{r['effect_label']} = {r['effect_value']:+.2f}"
                  if r["effect_label"] == "r"
                  else f"{r['effect_label']} = {r['effect_value']:.2f}")
        rows.append({
            "Measure": clean(r["measure"]), "n": str(int(r["n"])),
            **{c: fmt(r[f"{c.lower()}_mean"], r[f"{c.lower()}_sd"], dp)
               for c in CONDITIONS},
            "Test": clean(r["test"]), "p": fmt_p(float(r["p"])),
            "Effect": effect, "Pairwise": clean(r["pairwise"]),
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
             "r = matched-pairs rank-biserial correlation.",
             fontsize=8.5, color=INK_MUTED, ha="left", va="bottom", linespacing=1.8)

    fig.tight_layout(rect=(0, 0.09, 1, 1))
    fig.savefig(FIG_DIR / "results_table.png", dpi=300, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    rows = load_rows()
    make_table(rows)
    for r in rows:
        measure = r["Measure"].replace("\n", " ")
        print(f"  {measure:<32} p={r['p']:<8} {r['Effect']:<12} {r['Pairwise']}")
    print(f"\nWrote {FIG_DIR / 'results_table.png'}  (numbers computed in R)")


if __name__ == "__main__":
    main()
