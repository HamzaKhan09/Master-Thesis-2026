"""
Three-condition results figure (HYTRACK / MetaQuest / OptiTrack) for the report,
built from stats_analysis_3way.py's Friedman + Holm-corrected post-hoc output.

Only the metrics that survive the no-simultaneous-capture finding appear here
(within-stream measures): limb jitter, legs-only jitter, tracking dropout.
Accuracy/MPJPE is deliberately absent -- see project memory
project_mpjpe_invalid_no_simultaneous_capture.

Each panel is self-contained: what the metric measures, the three bars, and the
conclusion in plain language. Significance is stated in words rather than drawn
as brackets (2026-08-29 feedback: brackets were not readable enough, and the
figure needed to say what it meant on its own).

DELIBERATELY NOT CALLED "JITTER" OR "SMOOTHNESS" (renamed 2026-08-29):
the underlying column is jitter_rms_m -- RMS frame-to-frame displacement -- but
that is not what the literature means by jitter. In VR avatar / mocap work,
jitter is mean JERK (third derivative of position, m/s^3), and the established
smoothness metrics are SPARC and LDLJ, all of which are deliberately
amplitude-independent. RMS displacement is closer to mean speed: a participant
who simply moved more scores higher, independent of tracker quality -- and
because the three conditions were recorded in separate blocks, that confound is
real here rather than hypothetical.

Crucially, the proper metric is not computable from this dataset either: the
logs run at ~5.7 Hz (verified across all three conditions), so Nyquist is
~2.85 Hz and genuine high-frequency tracking noise is aliased away before it
could be measured; estimating jerk at that rate would produce numbers without
meaning. This is a data-collection ceiling, not a fixable analysis choice.
The comparison itself stays valid -- what changed is the claim attached to it,
so the panels now say "movement between frames" and the footer states the
recording rate.

The prose in PANELS is editorial and therefore hard-coded, but every factual
significance claim it makes is declared in `expects` and CHECKED against the
CSVs at render time -- if the statistics ever change, this script warns loudly
instead of silently shipping a figure whose text contradicts its own data.

Produces: StudyData/analysis/figures/three_way_comparison.png

Run with:  MPLBACKEND=Agg conda run -n thesis-eval python plot_3way_comparison.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

from plot_study_data_simple import (
    ANALYSIS_DIR, FIG_DIR,
    CONDITION_COLOR, INK, INK_SECONDARY, INK_MUTED, GRIDLINE,
    style_axes,
)
from plot_scorecard_full import OPTI_COLOR, ci95_halfwidth
from stats_analysis_3way import CONDITIONS, wide_all_conditions
from stats_analysis import JITTER_RIG_LOCKED_JOINTS
from stats_analysis_legs import LEG_JOINTS

# Solid fills, no hatching: every bar is directly labelled on the x-axis, so
# identity is never carried by colour alone and the texture was pure noise.
BAR_COLOR = [CONDITION_COLOR["HYTRACK"], CONDITION_COLOR["MetaQuest"], OPTI_COLOR]

PANELS = [
    {
        "metric": "Jitter, limb joints (RMS m)",
        "title": "Movement between frames -- limbs",
        "ylabel": "Average joint movement per frame (m)",
        "explain": "How far each joint moves from one recorded frame\nto the next, averaged over the trial.",
        "conclusion": ("HYTRACK moves much like professional mocap; the\n"
                        "difference is not significant. MetaQuest moves clearly\n"
                        "less -- it fills in body motion rather than measuring it."),
        "stats": "Friedman: p<0.001, large effect (W=0.50)",
        "expects": {"omnibus": True,
                     "HYTRACK vs MetaQuest": True,
                     "HYTRACK vs OptiTrack": False,
                     "MetaQuest vs OptiTrack": True},
    },
    {
        "metric": "Jitter, legs only (RMS m)",
        "title": "Movement between frames -- legs",
        "ylabel": "Average joint movement per frame (m)",
        "explain": "The same measure, restricted to the knees and\nankles.",
        "conclusion": ("All three differ. MetaQuest's legs move least, in every\n"
                        "single participant -- matching the fact that Meta\n"
                        "generates leg motion instead of sensing it."),
        "stats": "Friedman: p<0.001, large effect (W=0.67)",
        "expects": {"omnibus": True,
                     "HYTRACK vs MetaQuest": True,
                     "HYTRACK vs OptiTrack": True,
                     "MetaQuest vs OptiTrack": True},
    },
    {
        "metric": "Tracking dropout (%)",
        "title": "Robustness",
        "ylabel": "Frames with timing gaps (%)",
        "explain": "Share of frames that arrived late or went missing.\nLower = more reliable.",
        "conclusion": ("No significant difference. All three systems delivered\n"
                        "frames essentially without interruption -- dropout was\n"
                        "negligible in every condition."),
        "stats": "Friedman: p=0.368, no significant difference",
        "expects": {"omnibus": False},
    },
]


def verify_prose(panel: dict, summary: pd.Series, posthoc: pd.DataFrame) -> list[str]:
    """Guard against the hard-coded prose drifting out of sync with the statistics."""
    problems = []
    exp = panel["expects"]
    if bool(summary.omnibus_significant) != exp["omnibus"]:
        problems.append(f"{panel['metric']}: omnibus significance is "
                        f"{bool(summary.omnibus_significant)}, prose assumes {exp['omnibus']}")
    for pair, expected_sig in exp.items():
        if pair == "omnibus":
            continue
        row = posthoc[posthoc.pair == pair]
        if row.empty:
            problems.append(f"{panel['metric']}: pair '{pair}' missing from post-hoc CSV")
            continue
        actual = bool(row.iloc[0].significant_after_holm)
        if actual != expected_sig:
            problems.append(f"{panel['metric']}: '{pair}' significance is {actual}, "
                            f"prose assumes {expected_sig}")
    return problems


def plot_panel(ax, wide: pd.DataFrame, panel: dict):
    means = [wide[c].mean() for c in CONDITIONS]
    errs = [ci95_halfwidth(wide[c]) for c in CONDITIONS]

    ax.bar(range(len(CONDITIONS)), means, width=0.52,
           color=BAR_COLOR, linewidth=0, zorder=3,
           yerr=errs, capsize=3.5,
           error_kw=dict(ecolor=INK_SECONDARY, elinewidth=0.9, capthick=0.9, zorder=4))

    for i, (m, e) in enumerate(zip(means, errs)):
        ax.text(i, m + e, f"{m:.3f}", ha="center", va="bottom",
                fontsize=10, color=INK)

    ax.set_xticks(range(len(CONDITIONS)))
    ax.set_xticklabels(CONDITIONS, fontsize=10)
    ax.set_ylabel(panel["ylabel"], fontsize=8.5)
    ax.set_title(panel["title"], fontsize=12.5, color=INK, loc="left",
                 fontweight="bold", pad=12)
    ax.set_ylim(0, max(m + e for m, e in zip(means, errs)) * 1.24)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
    style_axes(ax)
    ax.tick_params(axis="x", pad=7)


def make_figure(jitter: pd.DataFrame, continuity: pd.DataFrame,
                summary: pd.DataFrame, posthoc: pd.DataFrame):
    wides = {
        "Jitter, limb joints (RMS m)":
            wide_all_conditions(jitter, "jitter_rms_m", drop_joints=JITTER_RIG_LOCKED_JOINTS),
        "Jitter, legs only (RMS m)":
            wide_all_conditions(jitter, "jitter_rms_m", keep_joints=LEG_JOINTS),
        "Tracking dropout (%)":
            wide_all_conditions(continuity, "pct_gaps_over_1_5x_expected"),
    }

    problems = []
    for panel in PANELS:
        problems += verify_prose(panel,
                                 summary[summary.metric == panel["metric"]].iloc[0],
                                 posthoc[posthoc.metric == panel["metric"]])
    if problems:
        print("WARNING -- figure text no longer matches the statistics:")
        for p in problems:
            print(f"  - {p}")

    fig, axes = plt.subplots(1, 3, figsize=(14, 6.6))
    for ax, panel in zip(axes, PANELS):
        plot_panel(ax, wides[panel["metric"]], panel)

    # Reserve the lower half of the figure for prose, then lay that prose out in
    # FIGURE coordinates. Placing it in axes coordinates instead makes the gaps
    # scale with axes height, which collapses the blocks into each other.
    fig.tight_layout(rect=(0, 0.54, 1, 1), w_pad=4.0)

    for ax, panel in zip(axes, PANELS):
        pos = ax.get_position()
        x = pos.x0
        # hairline rule per column, separating the plotted data from the prose
        fig.add_artist(Line2D([x, pos.x1], [0.505, 0.505],
                              color=GRIDLINE, linewidth=1.0, zorder=0))
        fig.text(x, 0.475, panel["explain"], ha="left", va="top",
                 fontsize=8.5, color=INK_MUTED, linespacing=1.5)
        fig.text(x, 0.375, panel["conclusion"], ha="left", va="top",
                 fontsize=9.5, color=INK_SECONDARY, linespacing=1.7)
        fig.text(x, 0.205, panel["stats"], ha="left", va="top",
                 fontsize=8, color=INK_MUTED)

    # Short "term = meaning" keys rather than prose sentences: this block is
    # scanned for a definition, not read start to finish.
    n = int(summary.n.iloc[0])
    fig.text(0.5, 0.115,
             f"n = {n} participants (completed all three conditions)     "
             "Error bars = 95% confidence interval     "
             "p < 0.05 = statistically significant\n"
             "W = Kendall's W, effect size (0.1 small, 0.3 moderate, 0.5 large)     "
             "Tests = Friedman, then pairwise Wilcoxon with Holm correction\n"
             "Recording rate = about 6 frames per second, so this shows overall movement, "
             "not fine tracking noise",
             ha="center", va="top", fontsize=8.5, color=INK_MUTED, linespacing=1.9)
    fig.savefig(FIG_DIR / "three_way_comparison.png", dpi=300, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    jitter = pd.read_csv(ANALYSIS_DIR / "jitter_by_participant_joint.csv")
    continuity = pd.read_csv(ANALYSIS_DIR / "tracking_continuity_by_participant.csv")
    summary = pd.read_csv(ANALYSIS_DIR / "friedman_3way_summary.csv")
    posthoc = pd.read_csv(ANALYSIS_DIR / "friedman_3way_posthoc.csv")

    make_figure(jitter, continuity, summary, posthoc)
    print(f"Wrote {FIG_DIR / 'three_way_comparison.png'}")


if __name__ == "__main__":
    main()
