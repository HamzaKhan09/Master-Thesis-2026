"""
Standalone, report-ready robustness figure -- companion to the accuracy and
motion-fidelity figures, same size and layout.

Deliberately NOT a paired-line plot like the others: 16 of 19 participants had
zero dropped frames in all three conditions, so connecting lines would draw 16
flat lines along the axis and hide the only informative feature (which
participants deviated, and by how little). A jittered dot plot shows the pile-up
at zero honestly, with the three outliers visible as what they are.

Dropout is measured within a single condition's own timestamp stream, so it is
unaffected by OptiTrack having been recorded as a separate block.

Produces: StudyData/analysis/figures/robustness.png

Run with:  MPLBACKEND=Agg conda run -n thesis-eval python plot_robustness_figure.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from plot_study_data_simple import (
    ANALYSIS_DIR, FIG_DIR, SURFACE,
    CONDITION_COLOR, INK, INK_SECONDARY, INK_MUTED, GRIDLINE,
    style_axes,
)
from plot_scorecard_full import OPTI_COLOR
from stats_analysis_3way import CONDITIONS
import r_results

COLOR_OF = {"HYTRACK": CONDITION_COLOR["HYTRACK"],
            "MetaQuest": CONDITION_COLOR["MetaQuest"],
            "OptiTrack": OPTI_COLOR}
DOT = "#9a9a93"


def main():
    cont = pd.read_csv(ANALYSIS_DIR / "tracking_continuity_by_participant.csv")
    wide = (cont.pivot(index="participant_id", columns="condition",
                       values="pct_gaps_over_1_5x_expected")
            .dropna(subset=CONDITIONS)[CONDITIONS])
    n = len(wide)

    fig, ax = plt.subplots(figsize=(8.2, 8.6))
    rng = np.random.default_rng(0)

    for i, cond in enumerate(CONDITIONS):
        vals = wide[cond].values
        # horizontal jitter only: without it the participants sitting at exactly
        # zero stack into a single dot and the sample size becomes invisible
        xs = i + rng.uniform(-0.13, 0.13, size=len(vals))
        ax.plot(xs, vals, linestyle="none", marker="o", markersize=6.5,
                markerfacecolor=DOT, markeredgecolor="none", alpha=0.55, zorder=2)
        ax.plot(i, vals.mean(), marker="o", markersize=13,
                markerfacecolor=COLOR_OF[cond], markeredgecolor=SURFACE,
                markeredgewidth=2.0, zorder=5)
        # count sits just under each cluster, inside the axes, so the condition
        # names can keep normal tick spacing instead of being pushed far below
        ax.text(i, -0.048, f"{(vals == 0).sum()} of {n} at zero",
                ha="center", va="center", fontsize=9.5, color=INK_MUTED)

    ax.set_xticks(range(len(CONDITIONS)))
    ax.set_xticklabels(CONDITIONS, fontsize=11.5)
    ax.set_xlim(-0.45, len(CONDITIONS) - 0.55)
    ax.set_ylim(-0.075, wide.values.max() * 1.22)
    ax.set_ylabel("Frames arriving late or missing (%)", fontsize=10.5)
    ax.set_title("Robustness", fontsize=14, color=INK, loc="left", fontweight="bold", pad=14)
    style_axes(ax)
    ax.tick_params(axis="x", pad=8)

    ax.legend(handles=[
        Line2D([0], [0], linestyle="none", marker="o", markersize=6.5,
               markerfacecolor=DOT, markeredgecolor="none", alpha=0.7, label="one participant"),
        Line2D([0], [0], linestyle="none", marker="o", markersize=10,
               markerfacecolor=INK_SECONDARY, markeredgecolor=SURFACE, label="condition mean"),
    ], loc="upper center", frameon=False, fontsize=10, ncol=2,
        handletextpad=0.5, columnspacing=1.8)

    fig.tight_layout(rect=(0, 0.46, 1, 1))
    pos = ax.get_position()
    fig.add_artist(Line2D([pos.x0, pos.x1], [pos.y0 - 0.050, pos.y0 - 0.050],
                          color=GRIDLINE, linewidth=1.0, zorder=0))

    explain = ("Share of frames that arrived late or went missing during a trial. "
               "Lower is better.")
    conclusion = ("All three systems delivered frames reliably, with no significant\n"
                  "difference between them. 16 of 19 participants lost no frames at all in\n"
                  "any condition, and the single worst case was 0.22% of frames.")
    # p-value and sampling rate both read from the analysis output rather than
    # written here, so the caption cannot drift.
    lo, hi = r_results.achieved_rate_hz()
    stats_line = (
        f"n = {n}     Friedman p {r_results.fmt_p(r_results.omnibus_p(r_results.ROBUSTNESS))}"
        ", no significant difference     "
        f"Achieved rate {lo:.2f}-{hi:.2f} Hz in all three conditions")

    y = pos.y0 - 0.082
    fig.text(pos.x0, y, explain, ha="left", va="top",
             fontsize=9.5, color=INK_MUTED, linespacing=1.6)
    y -= 1 * 0.026 + 0.020
    fig.text(pos.x0, y, conclusion, ha="left", va="top",
             fontsize=11, color=INK_SECONDARY, linespacing=1.7)
    y -= 3 * 0.032 + 0.026
    fig.text(pos.x0, y, stats_line, ha="left", va="top",
             fontsize=9, color=INK_MUTED, linespacing=1.9)

    fig.savefig(FIG_DIR / "robustness.png", dpi=300, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Wrote {FIG_DIR / 'robustness.png'}")


if __name__ == "__main__":
    main()
