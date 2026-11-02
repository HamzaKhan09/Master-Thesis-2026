"""
Leg-only version of plot_stats_table.py -- full statistics table (mean +/- SD,
test used, p-value, Cohen's dz, achieved power) for MPJPE and Jitter restricted
to leg joints (knees + ankles). Reads paired_test_legs_summary.csv, produced by
stats_analysis_legs.py.

Robustness and Latency get a single explanatory row each instead of numbers:
neither is logged per-joint, so there is no legs-only value to report.

Produces: StudyData/analysis/figures/stats_table_legs.png

Run with:  MPLBACKEND=Agg conda run -n thesis-eval python plot_stats_table_legs.py
"""
from __future__ import annotations

import pandas as pd
import matplotlib.pyplot as plt

from plot_study_data_simple import ANALYSIS_DIR, FIG_DIR, INK, INK_MUTED, GRIDLINE, BASELINE
from plot_stats_table import COLUMNS, COL_X, COL_ALIGN, opti_stats, fmt_ms
from stats_analysis_legs import LEG_JOINTS


def build_rows(summary: pd.DataFrame, jitter_legs: pd.DataFrame) -> list[list[str]]:
    rows = []

    r = summary[summary.metric == "MPJPE (legs, m)"].iloc[0]
    rows.append([
        "Accuracy\n(MPJPE, legs)", str(r.n),
        fmt_ms(r.hytrack_mean, r.hytrack_std, "{:.3f} m"),
        fmt_ms(r.metaquest_mean, r.metaquest_std, "{:.3f} m"),
        "n/a -- ground truth",
        f"{r.recommended_test}\n({'t' if r.diff_normal else 'W'}="
        f"{r.t_stat:.2f})" if r.diff_normal else f"{r.recommended_test}\n(W={r.wilcoxon_stat:.1f})",
        f"{(r.t_p if r.diff_normal else r.wilcoxon_p):.3f}",
        f"{r.cohens_dz:.3f}",
        f"{r.power_achieved_at_n:.3f}",
    ])

    jitter_wb = jitter_legs.groupby(["participant_id", "condition"]).jitter_rms_m.mean().reset_index()
    n_o, m_o, sd_o = opti_stats(jitter_wb, "jitter_rms_m")
    r = summary[summary.metric == "Jitter (legs, RMS m)"].iloc[0]
    p_val = r.t_p if r.diff_normal else r.wilcoxon_p
    rows.append([
        "Smoothness\n(Jitter, legs)", str(r.n),
        fmt_ms(r.hytrack_mean, r.hytrack_std, "{:.3f} m"),
        fmt_ms(r.metaquest_mean, r.metaquest_std, "{:.3f} m"),
        f"{fmt_ms(m_o, sd_o, '{:.3f} m')}\n(n={n_o})",
        f"{r.recommended_test}\n(t={r.t_stat:.2f})" if r.diff_normal else f"{r.recommended_test}\n(W={r.wilcoxon_stat:.1f})",
        f"{p_val:.4f}" if p_val >= 0.0005 else "<0.001",
        f"{r.cohens_dz:.3f}",
        f"{r.power_achieved_at_n:.3f}",
    ])

    rows.append([
        "Robustness\n(Dropout %)", "--",
        "not per-joint", "not per-joint", "not per-joint",
        "-- (logged per session,\nnot per joint)", "--", "--", "--",
    ])

    rows.append([
        "Latency", "0",
        "not measurable", "not measurable", "not measurable",
        "-- (no data)", "--", "--", "--",
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
              "Test/statistic/p come from the paired HYTRACK-vs-MetaQuest test only (stats_analysis_legs.py); "
              "OptiTrack column is descriptive, not part of that test.\n"
              "Legs = left/right knee + ankle (hips excluded, root-relative reference joint). "
              "Robustness and Latency aren't logged per-joint -- see stats_table.png for those two.",
              fontsize=7.5, color=INK_MUTED, ha="left", va="bottom")

    fig.suptitle("Full statistics, legs only -- HYTRACK vs MetaQuest vs OptiTrack", fontsize=13.5,
                 color=INK, x=0.01, ha="left", y=0.995)

    fig.tight_layout(rect=(0, 0.06, 1, 0.94))
    fig.savefig(FIG_DIR / "stats_table_legs.png", dpi=300, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    summary = pd.read_csv(ANALYSIS_DIR / "paired_test_legs_summary.csv")
    jitter = pd.read_csv(ANALYSIS_DIR / "jitter_by_participant_joint.csv")
    jitter_legs = jitter[jitter.joint.isin(LEG_JOINTS)]

    rows = build_rows(summary, jitter_legs)
    make_table(rows)
    print(f"Wrote {FIG_DIR / 'stats_table_legs.png'}")


if __name__ == "__main__":
    main()
