"""
Accuracy figure that replaces the invalid MPJPE panel, built from
stats_analysis_accuracy.py.

Everything shown is invariant to WHEN a frame was captured, which is what makes
it usable here: OptiTrack was a separate recording block, so no per-frame error
measure is meaningful (see project_mpjpe_invalid_no_simultaneous_capture).

  Panel 1 -- how close each system's limb lengths are to OptiTrack's. OptiTrack
             is the reference, so it has no bar (its error is 0 by definition),
             exactly as the old accuracy panel treated it.
  Panel 2 -- how much a bone length wobbles inside a single trial. A real bone
             cannot change length, so this is tracking error by definition.
  Panel 3 -- whether the reported skeleton is sized to the individual, measured
             as the spread of limb lengths across participants.

Legs only in panels 2 and 3: the legs are what actually distinguishes these
systems (upper body is Quest-driven in both consumer conditions), and shoulder
width is deliberately excluded everywhere because it is NOT an anatomically
fixed segment -- the shoulders genuinely move relative to each other, which is
why OptiTrack shows MORE variation there than the two consumer rigs, matching
the rig-lock artefact already documented for the jitter analysis.

Produces: StudyData/analysis/figures/accuracy_comparison.png

Run with:  MPLBACKEND=Agg conda run -n thesis-eval python plot_accuracy_comparison.py
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
from stats_analysis_3way import CONDITIONS

LEG_SEGMENTS = ["Thigh (L)", "Thigh (R)", "Shank (L)", "Shank (R)"]
ARM_SEGMENTS = ["Upper arm (L)", "Upper arm (R)", "Forearm (L)", "Forearm (R)"]
TWO_SYSTEMS = ["HYTRACK", "MetaQuest"]

BAR_COLOR = [CONDITION_COLOR["HYTRACK"], CONDITION_COLOR["MetaQuest"], OPTI_COLOR]
COLOR_OF = {"HYTRACK": CONDITION_COLOR["HYTRACK"],
            "MetaQuest": CONDITION_COLOR["MetaQuest"],
            "OptiTrack": OPTI_COLOR}


# --------------------------------------------------------------------------- #
# Data prep
# --------------------------------------------------------------------------- #

def group_mean(seg: pd.DataFrame, segments: list[str], value_col: str) -> pd.DataFrame:
    """Average a set of segments into one value per participant per condition."""
    sub = seg[seg.segment.isin(segments)]
    return (sub.groupby(["participant_id", "condition"])[value_col]
            .mean().reset_index()
            .pivot(index="participant_id", columns="condition", values=value_col))


def abs_error_vs_opti(seg: pd.DataFrame, segments: list[str]) -> pd.DataFrame:
    """|reported length - OptiTrack length| per participant, in cm."""
    wide = group_mean(seg, segments, "length_mean_m").dropna(subset=CONDITIONS)
    return pd.DataFrame({c: (wide[c] - wide["OptiTrack"]).abs() * 100.0
                         for c in TWO_SYSTEMS})


def style_panel(ax, title, ylabel):
    ax.set_ylabel(ylabel, fontsize=8.5)
    ax.set_title(title, fontsize=12.5, color=INK, loc="left", fontweight="bold", pad=12)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
    style_axes(ax)
    ax.tick_params(axis="x", pad=7)


def bars_by_condition(ax, wide: pd.DataFrame, conditions: list[str], fmt: str, scale=1.0):
    means = [wide[c].mean() * scale for c in conditions]
    errs = [ci95_halfwidth(wide[c]) * scale for c in conditions]
    ax.bar(range(len(conditions)), means, width=0.52,
           color=[COLOR_OF[c] for c in conditions], linewidth=0, zorder=3,
           yerr=errs, capsize=3.5,
           error_kw=dict(ecolor=INK_SECONDARY, elinewidth=0.9, capthick=0.9, zorder=4))
    for i, (m, e) in enumerate(zip(means, errs)):
        ax.text(i, m + e, fmt.format(m), ha="center", va="bottom", fontsize=10, color=INK)
    ax.set_xticks(range(len(conditions)))
    ax.set_xticklabels(conditions, fontsize=10)
    ax.set_ylim(0, max(m + e for m, e in zip(means, errs)) * 1.24)


def panel_length_error(ax, seg: pd.DataFrame):
    groups = {"Legs": LEG_SEGMENTS, "Arms": ARM_SEGMENTS}
    width = 0.34
    top = 0.0
    for gi, (gname, segments) in enumerate(groups.items()):
        err = abs_error_vs_opti(seg, segments)
        for si, system in enumerate(TWO_SYSTEMS):
            m = err[system].mean()
            e = ci95_halfwidth(err[system])
            x = gi + (si - 0.5) * width
            ax.bar(x, m, width=width * 0.9, color=COLOR_OF[system], linewidth=0, zorder=3,
                   yerr=e, capsize=3.5,
                   error_kw=dict(ecolor=INK_SECONDARY, elinewidth=0.9, capthick=0.9, zorder=4))
            ax.text(x, m + e, f"{m:.2f}", ha="center", va="bottom", fontsize=9.5, color=INK)
            top = max(top, m + e)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels(list(groups), fontsize=10)
    ax.set_ylim(0, top * 1.30)
    handles = [Line2D([0], [0], marker="s", linestyle="", markersize=8,
                      markerfacecolor=COLOR_OF[s], markeredgecolor="none", label=s)
               for s in TWO_SYSTEMS]
    ax.legend(handles=handles, loc="upper left", frameon=False, fontsize=9,
              handletextpad=0.4, borderpad=0.2)
    style_panel(ax, "Limb length error", "Difference from OptiTrack (cm)")


def main():
    seg = pd.read_csv(ANALYSIS_DIR / "segment_lengths_by_participant.csv")

    fig, axes = plt.subplots(1, 3, figsize=(14, 6.6))

    panel_length_error(axes[0], seg)

    cv = group_mean(seg, LEG_SEGMENTS, "length_cv_pct").dropna(subset=CONDITIONS)
    bars_by_condition(axes[1], cv, CONDITIONS, "{:.2f}")
    style_panel(axes[1], "Bone length stability", "Variation within a trial (%)")

    spread = (group_mean(seg, LEG_SEGMENTS, "length_mean_m")
              .dropna(subset=CONDITIONS).std(ddof=1) * 100.0)
    axes[2].bar(range(len(CONDITIONS)), [spread[c] for c in CONDITIONS], width=0.52,
                color=[COLOR_OF[c] for c in CONDITIONS], linewidth=0, zorder=3)
    for i, c in enumerate(CONDITIONS):
        axes[2].text(i, spread[c], f"{spread[c]:.2f}", ha="center", va="bottom",
                     fontsize=10, color=INK)
    axes[2].set_xticks(range(len(CONDITIONS)))
    axes[2].set_xticklabels(CONDITIONS, fontsize=10)
    axes[2].set_ylim(0, spread.max() * 1.30)
    style_panel(axes[2], "Adapts to body size?", "Spread of leg length across people (cm)")

    prose = [
        {"explain": "How far each system's reported limb lengths sit from\nOptiTrack's. OptiTrack is the reference, so it has no bar.",
         "conclusion": ("For the legs, HYTRACK is significantly closer to mocap\n"
                         "than MetaQuest. HYTRACK runs slightly long, MetaQuest\n"
                         "slightly short; both stay within about two centimetres."),
         "stats": "Legs: p=0.016 (left), p=0.018 (right)   Arms: p=0.029 (right), rest not significant"},
        {"explain": "A real bone cannot change length during a trial, so\nany variation here is tracking error. Legs only.",
         "conclusion": ("HYTRACK's leg lengths wobble by about 3% while it\n"
                         "tracks. MetaQuest's barely move because its legs are\n"
                         "generated from a fixed skeleton rather than measured."),
         "stats": "Friedman: p<0.001, large effect"},
        {"explain": "How much the reported leg length differs from person\nto person. Real people vary, so a system that adapts\nshould too.",
         "conclusion": ("OptiTrack and MetaQuest size the skeleton to each\n"
                         "individual. HYTRACK gives nearly everyone the same\n"
                         "leg length -- it does not adapt to body size."),
         "stats": "Descriptive spread across participants (no test)"},
    ]

    fig.tight_layout(rect=(0, 0.54, 1, 1), w_pad=4.0)

    for ax, p in zip(axes, prose):
        pos = ax.get_position()
        fig.add_artist(Line2D([pos.x0, pos.x1], [0.505, 0.505],
                              color=GRIDLINE, linewidth=1.0, zorder=0))
        fig.text(pos.x0, 0.475, p["explain"], ha="left", va="top",
                 fontsize=8.5, color=INK_MUTED, linespacing=1.5)
        fig.text(pos.x0, 0.360, p["conclusion"], ha="left", va="top",
                 fontsize=9.5, color=INK_SECONDARY, linespacing=1.7)
        fig.text(pos.x0, 0.195, p["stats"], ha="left", va="top",
                 fontsize=8, color=INK_MUTED)

    n = len(abs_error_vs_opti(seg, LEG_SEGMENTS))
    fig.text(0.5, 0.115,
             f"n = {n} participants (completed all three conditions)     "
             "Error bars = 95% confidence interval     "
             "p < 0.05 = statistically significant\n"
             "Tests = Wilcoxon signed-rank on absolute error (panel 1), "
             "Friedman across all three conditions (panel 2)\n"
             "Nothing here needs the recordings to be synchronised, which is why these "
             "measures work where per-frame position error does not",
             ha="center", va="top", fontsize=8.5, color=INK_MUTED, linespacing=1.9)

    fig.savefig(FIG_DIR / "accuracy_comparison.png", dpi=300, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Wrote {FIG_DIR / 'accuracy_comparison.png'}")


if __name__ == "__main__":
    main()
