"""
Full statistics table companion to scorecard_full_comparison.png -- the numbers
behind the headline verdicts: mean +/- SD per system, the paired test used, its
statistic, p-value, Cohen's dz, and achieved power (the professor's G*Power ask).

No OptiTrack column: it isn't part of the paired HYTRACK-vs-MetaQuest test, and
including it produced "n/a -- ground truth" / context-only cells that read as
noise (2026-08-28 feedback). Its own descriptive numbers stay documented in
project memory and on scorecard_full_comparison.png instead of here.

Reads paired_test_wholebody_summary.csv (HYTRACK vs MetaQuest test results,
produced by stats_analysis.py).

Produces: StudyData/analysis/figures/stats_table.png

Run with:  MPLBACKEND=Agg conda run -n thesis-eval python plot_stats_table.py
"""
from __future__ import annotations

import pandas as pd
import matplotlib.pyplot as plt

from plot_study_data_simple import ANALYSIS_DIR, FIG_DIR, INK, INK_MUTED, GRIDLINE, BASELINE

COLUMNS = ["Metric", "n", "HYTRACK\n(mean ± SD)", "MetaQuest\n(mean ± SD)",
           "Test used\n(statistic)", "p-value", "Cohen's dz", "Power\n(achieved)"]
COL_X = [0.01, 0.11, 0.27, 0.46, 0.63, 0.78, 0.88, 0.97]
COL_ALIGN = ["left", "center", "center", "center", "center", "center", "center", "center"]


def fmt_ms(mean, sd, unit_fmt) -> str:
    return f"{unit_fmt.format(mean)} ± {unit_fmt.format(sd)}"


def build_rows(summary: pd.DataFrame) -> list[list[str]]:
    rows = []

    r = summary[summary.metric == "MPJPE (whole-body, m)"].iloc[0]
    rows.append([
        "Accuracy\n(MPJPE)", str(r.n),
        fmt_ms(r.hytrack_mean, r.hytrack_std, "{:.3f} m"),
        fmt_ms(r.metaquest_mean, r.metaquest_std, "{:.3f} m"),
        f"{r.recommended_test}\n({'t' if r.diff_normal else 'W'}="
        f"{r.t_stat:.2f})" if r.diff_normal else f"{r.recommended_test}\n(W={r.wilcoxon_stat:.1f})",
        f"{(r.t_p if r.diff_normal else r.wilcoxon_p):.3f}",
        f"{r.cohens_dz:.3f}",
        f"{r.power_achieved_at_n:.3f}",
    ])

    r = summary[summary.metric.str.startswith("Jitter")].iloc[0]
    p_val = r.t_p if r.diff_normal else r.wilcoxon_p
    rows.append([
        "Smoothness\n(Jitter, limbs)", str(r.n),
        fmt_ms(r.hytrack_mean, r.hytrack_std, "{:.3f} m"),
        fmt_ms(r.metaquest_mean, r.metaquest_std, "{:.3f} m"),
        f"{r.recommended_test}\n(t={r.t_stat:.2f})" if r.diff_normal else f"{r.recommended_test}\n(W={r.wilcoxon_stat:.1f})",
        f"{p_val:.4f}" if p_val >= 0.0005 else "<0.001",
        f"{r.cohens_dz:.3f}",
        f"{r.power_achieved_at_n:.3f}",
    ])

    r = summary[summary.metric.str.startswith("Tracking dropout")].iloc[0]
    rows.append([
        "Robustness\n(Dropout %)", str(r.n),
        fmt_ms(r.hytrack_mean, r.hytrack_std, "{:.3f}%"),
        fmt_ms(r.metaquest_mean, r.metaquest_std, "{:.3f}%"),
        f"{r.recommended_test}\n(t={r.t_stat:.2f})" if r.diff_normal else f"{r.recommended_test}\n(W={r.wilcoxon_stat:.1f})",
        f"{(r.t_p if r.diff_normal else r.wilcoxon_p):.3f}",
        f"{r.cohens_dz:.3f}",
        f"{r.power_achieved_at_n:.3f}",
    ])

    return rows


def make_table(rows: list[list[str]]):
    n_rows = len(rows) + 1
    fig_h = 0.9 + n_rows * 0.85
    fig, ax = plt.subplots(figsize=(14.5, fig_h))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, n_rows)
    ax.axis("off")

    row_h = 1.0
    header_y = n_rows - 0.5

    for x, label, align in zip(COL_X, COLUMNS, COL_ALIGN):
        ax.text(x, header_y, label, ha=align, va="center", fontsize=10.5,
                color=INK, fontweight="bold", linespacing=1.3)
    ax.axhline(n_rows - 1, color=INK, linewidth=1.2, xmin=0.0, xmax=1.0)

    for i, row in enumerate(rows):
        y = n_rows - 1.5 - i
        if i % 2 == 1:
            ax.axhspan(y - row_h / 2, y + row_h / 2, color=GRIDLINE, alpha=0.5, zorder=0)
        for x, val, align in zip(COL_X, row, COL_ALIGN):
            fw = "bold" if align == "left" else "normal"
            ax.text(x, y, val, ha=align, va="center", fontsize=10, color=INK,
                    fontweight=fw, linespacing=1.3)
        ax.axhline(y - row_h / 2, color=BASELINE, linewidth=0.6, xmin=0.0, xmax=1.0)

    fig.text(0.01, 0.01,
              "p-value: chance of this gap happening if the two systems were truly equal (< 0.05 = statistically significant). "
              "Cohen's dz: effect size (~0.2 small, 0.5 medium, 0.8 large). "
              "Power: chance this sample size could detect a true effect (0.80+ is adequate).",
              fontsize=7.5, color=INK_MUTED, ha="left", va="bottom")

    fig.tight_layout(rect=(0, 0.05, 1, 1.0))
    fig.savefig(FIG_DIR / "stats_table.png", dpi=300, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    summary = pd.read_csv(ANALYSIS_DIR / "paired_test_wholebody_summary.csv")

    rows = build_rows(summary)
    make_table(rows)
    print(f"Wrote {FIG_DIR / 'stats_table.png'}")


if __name__ == "__main__":
    main()
