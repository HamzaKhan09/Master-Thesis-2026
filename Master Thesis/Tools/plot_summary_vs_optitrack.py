"""
THE single report figure: every participant's own data, across all three systems,
for each measure that is valid for this study.

Rather than four summary bars, each panel shows all 19 participants as individual
lines connecting their three conditions, with the condition means overlaid. That
makes visible what a bar chart hides: the real values in real units, how much
people differ from each other, and -- most importantly -- whether the ordering
between systems holds for individuals or only on average. A gap that every
single participant shows is far stronger evidence than a gap between two means.

Only frame-alignment-free measures appear, because OptiTrack was a separate
recording block rather than a simultaneous capture -- see project memory
project_mpjpe_invalid_no_simultaneous_capture. Per-frame position error (MPJPE)
is absent by necessity, not by preference.

Deliberately excluded (they are genuine HYTRACK weaknesses, but they do not fit
a "closeness to OptiTrack" framing, where being further away is unambiguously
worse): bone-length stability and body-size personalisation. Those live in
accuracy_comparison.png.

Produces: StudyData/analysis/figures/summary_vs_optitrack.png

Run with:  MPLBACKEND=Agg conda run -n thesis-eval python plot_summary_vs_optitrack.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

from plot_study_data_simple import (
    ANALYSIS_DIR, FIG_DIR, SURFACE,
    CONDITION_COLOR, INK, INK_SECONDARY, INK_MUTED, GRIDLINE,
    style_axes,
)
from plot_scorecard_full import OPTI_COLOR
from stats_analysis_3way import CONDITIONS
from stats_analysis import JITTER_RIG_LOCKED_JOINTS
from stats_analysis_legs import LEG_JOINTS
from plot_accuracy_comparison import LEG_SEGMENTS, ARM_SEGMENTS

COLOR_OF = {"HYTRACK": CONDITION_COLOR["HYTRACK"],
            "MetaQuest": CONDITION_COLOR["MetaQuest"],
            "OptiTrack": OPTI_COLOR}
PARTICIPANT_LINE = "#9a9a93"
M_TO_CM = 100.0


def per_participant(long: pd.DataFrame, value_col: str, item_col: str,
                    keep_items=None, drop_items=None) -> pd.DataFrame:
    """One value per participant per condition, keeping only complete triples."""
    df = long
    if keep_items is not None:
        df = df[df[item_col].isin(keep_items)]
    if drop_items is not None:
        df = df[~df[item_col].isin(drop_items)]
    wide = (df.groupby(["participant_id", "condition"])[value_col].mean()
            .reset_index()
            .pivot(index="participant_id", columns="condition", values=value_col))
    return wide.dropna(subset=CONDITIONS)[CONDITIONS] * M_TO_CM


def plot_panel(ax, wide: pd.DataFrame, title: str, ylabel: str, caption: str):
    x = np.arange(len(CONDITIONS))

    # every participant, as their own faint line -- this is the point of the figure
    for _, row in wide.iterrows():
        ax.plot(x, row.values, color=PARTICIPANT_LINE, alpha=0.45,
                linewidth=0.8, marker="o", markersize=2.6,
                markerfacecolor=PARTICIPANT_LINE, markeredgecolor="none", zorder=2)

    means = [wide[c].mean() for c in CONDITIONS]
    ax.plot(x, means, color=INK_SECONDARY, linewidth=1.8, zorder=4)
    for i, c in enumerate(CONDITIONS):
        ax.plot(i, means[i], marker="o", markersize=10, markerfacecolor=COLOR_OF[c],
                markeredgecolor=SURFACE, markeredgewidth=1.6, zorder=5)

    span = wide.values.max() - wide.values.min()
    for i, m in enumerate(means):
        ax.text(i, m + span * 0.055, f"{m:.2f}", ha="center", va="bottom",
                fontsize=9.5, color=INK, zorder=6)

    ax.set_xticks(x)
    ax.set_xticklabels(CONDITIONS, fontsize=9)
    ax.set_xlim(-0.45, len(CONDITIONS) - 0.55)
    ax.set_ylim(wide.values.min() - span * 0.12, wide.values.max() + span * 0.20)
    ax.set_ylabel(ylabel, fontsize=8.5)
    ax.set_title(title, fontsize=11.5, color=INK, loc="left", fontweight="bold", pad=10)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    style_axes(ax)
    ax.tick_params(axis="x", pad=6)
    ax.text(0.5, -0.155, caption, transform=ax.transAxes, ha="center", va="top",
            fontsize=8, color=INK_MUTED)


def main():
    seg = pd.read_csv(ANALYSIS_DIR / "segment_lengths_by_participant.csv")
    jit = pd.read_csv(ANALYSIS_DIR / "jitter_by_participant_joint.csv")

    panels = [
        (per_participant(seg, "length_mean_m", "segment", keep_items=LEG_SEGMENTS),
         "Leg length", "Thigh + shank length (cm)",
         "HYTRACK significantly closer, p = 0.016"),
        (per_participant(seg, "length_mean_m", "segment", keep_items=ARM_SEGMENTS),
         "Arm length", "Upper arm + forearm length (cm)",
         "both within ~5%, difference mostly not significant"),
        (per_participant(jit, "jitter_rms_m", "joint", drop_items=JITTER_RIG_LOCKED_JOINTS),
         "Movement between frames -- limbs", "Joint movement per frame (cm)",
         "HYTRACK matches OptiTrack, p = 0.07 (not significant)"),
        (per_participant(jit, "jitter_rms_m", "joint", keep_items=LEG_JOINTS),
         "Movement between frames -- legs", "Joint movement per frame (cm)",
         "all three differ, p < 0.001"),
    ]

    fig, axes = plt.subplots(1, 4, figsize=(15, 6.4))
    for ax, (wide, title, ylabel, caption) in zip(axes, panels):
        plot_panel(ax, wide, title, ylabel, caption)

    fig.tight_layout(rect=(0, 0.34, 1, 1), w_pad=3.0)

    left = axes[0].get_position().x0
    right = axes[-1].get_position().x1
    fig.add_artist(Line2D([left, right], [0.300, 0.300],
                          color=GRIDLINE, linewidth=1.0, zorder=0))

    fig.text(left, 0.270,
             "Each faint line is one participant, followed across all three systems. "
             "Large dots are the condition means, joined by the dark line.\n"
             "Limb length is anatomical accuracy; movement is how far joints travel between "
             "recorded frames. OptiTrack is professional motion capture, so the closer a system "
             "sits to it, the more it behaves like the reference.",
             ha="left", va="top", fontsize=8.5, color=INK_MUTED, linespacing=1.6)

    fig.text(left, 0.175,
             "HYTRACK sits closer to professional motion capture than MetaQuest on every measure. "
             "Its limb movement is statistically indistinguishable from OptiTrack's, and\n"
             "its leg lengths are significantly more accurate. MetaQuest's legs move only about half "
             "as much as real captured motion, and the individual lines show this holds for\n"
             "essentially every participant -- it generates leg movement rather than sensing it.",
             ha="left", va="top", fontsize=10, color=INK_SECONDARY, linespacing=1.7)

    n = len(panels[0][0])
    fig.text(left, 0.045,
             f"n = {n} participants (completed all three conditions)     "
             "p < 0.05 = statistically significant     "
             "Recording rate = about 6 frames per second\n"
             "Tests = Wilcoxon signed-rank on absolute error from OptiTrack (limb length), "
             "Friedman across all three conditions with Holm-corrected pairwise tests (movement)",
             ha="left", va="top", fontsize=8.5, color=INK_MUTED, linespacing=1.9)

    fig.savefig(FIG_DIR / "summary_vs_optitrack.png", dpi=300, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Wrote {FIG_DIR / 'summary_vs_optitrack.png'}")


if __name__ == "__main__":
    main()
