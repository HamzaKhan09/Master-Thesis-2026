"""
Comparative scorecard: HYTRACK vs MetaQuest across every metric we can actually
measure -- Accuracy (MPJPE, measured against OptiTrack as ground truth),
Smoothness (jitter), Robustness (tracking dropout rate). OptiTrack itself is
never plotted as a bar -- it's the ground truth accuracy is measured against,
not a competing system -- but the Accuracy panel says so explicitly. Latency
is excluded: latency_log.csv's input_time_ms is empty in 100% of rows, so
there is no real latency number to plot.

One figure, one row per metric, each a discrete HYTRACK-vs-MetaQuest bar pair
with a plain-language verdict -- so each metric can be read on its own instead
of needing to cross-reference multiple charts.

Produces: StudyData/analysis/figures/scorecard_comparison.png

Run with:  MPLBACKEND=Agg <thesis-eval python> plot_scorecard.py
"""
from __future__ import annotations

import pandas as pd
import matplotlib.pyplot as plt

from plot_study_data_simple import (
    ANALYSIS_DIR, FIG_DIR,
    CONDITION_COLOR, CONDITION_HATCH, INK, INK_MUTED,
    style_axes, whole_body_wide, verdict,
)
from stats_analysis import JITTER_RIG_LOCKED_JOINTS


def plot_metric_row(ax, wide: pd.DataFrame, title: str, ylabel: str, caption: str,
                     unit_fmt: str):
    v = verdict(wide)
    bars = ax.bar(["HYTRACK", "MetaQuest"], [v["h_mean"], v["m_mean"]],
                   width=0.45,
                   color=[CONDITION_COLOR["HYTRACK"], CONDITION_COLOR["MetaQuest"]],
                   hatch=[CONDITION_HATCH["HYTRACK"], CONDITION_HATCH["MetaQuest"]],
                   edgecolor=INK, linewidth=0.6, zorder=3)
    for bar, val in zip(bars, [v["h_mean"], v["m_mean"]]):
        ax.text(bar.get_x() + bar.get_width() / 2, val, unit_fmt.format(val),
                ha="center", va="bottom", fontsize=10, color=INK)

    ax.set_ylim(0, max(v["h_mean"], v["m_mean"]) * 1.3)
    ax.set_title(title, fontsize=13, color=INK, loc="left", fontweight="bold")
    ax.set_ylabel(ylabel, fontsize=9)
    style_axes(ax)

    ax.text(0.5, -0.22, f"{caption}  (n={v['n']}, p={v['p']:.3f})",
            transform=ax.transAxes, ha="center", va="top", fontsize=8.5, color=INK_MUTED)


def make_scorecard(mpjpe: pd.DataFrame, jitter: pd.DataFrame, continuity: pd.DataFrame):
    fig, axes = plt.subplots(3, 1, figsize=(6, 12.5))

    plot_metric_row(
        axes[0], whole_body_wide(mpjpe, "mpjpe_m"),
        "Accuracy", "Position error vs. OptiTrack ground truth (m)",
        "measured against OptiTrack (ground truth) -- lower is better",
        "{:.3f} m",
    )

    # head/shoulders/hips excluded: near-rigid relative to the hip in both
    # consumer rigs (construction artifact, not real smoothness) -- see
    # stats_analysis.py / JITTER_RIG_LOCKED_JOINTS.
    jitter_limbs = jitter[~jitter.joint.isin(JITTER_RIG_LOCKED_JOINTS)]
    plot_metric_row(
        axes[1], whole_body_wide(jitter_limbs, "jitter_rms_m"),
        "Smoothness", "Jitter, limb joints only (m)",
        "frame-to-frame stability (elbows/wrists/knees/ankles) -- lower is better",
        "{:.3f} m",
    )

    plot_metric_row(
        axes[2], whole_body_wide(continuity, "pct_gaps_over_1_5x_expected"),
        "Robustness", "Frames with timing gaps (%)",
        "tracking dropout rate -- lower is better",
        "{:.3f}%",
    )

    fig.tight_layout(rect=(0, 0.0, 1, 1.0), h_pad=7.0)
    fig.savefig(FIG_DIR / "scorecard_comparison.png", dpi=300, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    mpjpe = pd.read_csv(ANALYSIS_DIR / "mpjpe_by_participant_joint.csv")
    jitter = pd.read_csv(ANALYSIS_DIR / "jitter_by_participant_joint.csv")
    continuity = pd.read_csv(ANALYSIS_DIR / "tracking_continuity_by_participant.csv")

    make_scorecard(mpjpe, jitter, continuity)
    print(f"Wrote {FIG_DIR / 'scorecard_comparison.png'}")


if __name__ == "__main__":
    main()
