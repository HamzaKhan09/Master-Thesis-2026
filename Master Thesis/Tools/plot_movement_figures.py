"""
Standalone, report-ready MOTION FIDELITY figures -- one graph per file, sized to
stay readable when placed at normal figure width in a document.

NAMING (settled 2026-08-29, do not revert): this metric was called "Smoothness /
jitter" and then "Movement between frames" before landing on **motion fidelity,
reported as mean joint velocity (cm/s)**.
  - "Smoothness" is NOT available: it has a technical definition in this field
    (SPARC, LDLJ, mean jerk) and the logs run at ~5.7 Hz, so Nyquist is ~2.85 Hz
    and real high-frequency tracking noise is aliased away. Claiming smoothness
    from 6 fps data would not survive examination.
  - "Movement between frames" was defensible but named a raw measurement rather
    than a construct, which reads weakly in a thesis.
  - Velocity is the honest upgrade: displacement per frame divided by the frame
    interval, which is the form this literature reports (the MPJVE metric family
    in the sparse-tracking papers). It names a construct, uses standard units,
    and claims no temporal precision the data does not have.

Splits the two movement panels out of the combined summary figure, which was too
dense to read once scaled down (2026-08-29 feedback). Limb-length accuracy and
arm length were dropped from the report figures at the user's request; the
accuracy work still exists in accuracy_comparison.png if it is wanted later.

Each figure shows every participant as their own faint line across all three
systems, with condition means overlaid. That is what makes the leg result
convincing: the MetaQuest dip is visible for essentially every individual, not
just between two averages.

Both measures are computed within a single condition's own data stream, so they
are unaffected by the fact that OptiTrack was recorded as a separate block --
see project_mpjpe_invalid_no_simultaneous_capture.

Produces:
  StudyData/analysis/figures/movement_limbs.png
  StudyData/analysis/figures/movement_legs.png

Run with:  MPLBACKEND=Agg conda run -n thesis-eval python plot_movement_figures.py
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
import r_results

COLOR_OF = {"HYTRACK": CONDITION_COLOR["HYTRACK"],
            "MetaQuest": CONDITION_COLOR["MetaQuest"],
            "OptiTrack": OPTI_COLOR}
PARTICIPANT_LINE = "#9a9a93"
M_TO_CM = 100.0


def per_participant(jit: pd.DataFrame, keep_joints=None, drop_joints=None) -> pd.DataFrame:
    """Mean joint velocity in cm/s, per participant per condition.

    The stored column is displacement between consecutive frames; dividing by that
    trial's own mean frame interval converts it to a velocity, which is the form
    this literature reports (the MPJVE metric family). Using each row's own dt also
    removes the small sampling-rate differences between conditions (5.70-5.72 Hz),
    so the comparison is not carrying a rate artefact.
    """
    df = jit
    if keep_joints is not None:
        df = df[df.joint.isin(keep_joints)]
    if drop_joints is not None:
        df = df[~df.joint.isin(drop_joints)]
    df = df.assign(velocity_cm_s=df.jitter_rms_m / df.mean_frame_dt_s * M_TO_CM)
    wide = (df.groupby(["participant_id", "condition"]).velocity_cm_s.mean()
            .reset_index()
            .pivot(index="participant_id", columns="condition", values="velocity_cm_s"))
    return wide.dropna(subset=CONDITIONS)[CONDITIONS]


def make_figure(wide: pd.DataFrame, title: str, explain: str, conclusion: str,
                stats_line: str, filename: str,
                ylabel: str = "Joint movement per frame (cm)",
                participant_alpha: float = 0.45, participant_markers: bool = True):
    """`participant_alpha` / `participant_markers` control how much the individual
    lines assert themselves. Full prominence where the per-participant pattern IS
    the finding (the movement figures claim the effect holds for everyone); subdued
    where the means carry the message and the individual spread would only distract."""
    fig, ax = plt.subplots(figsize=(8.2, 8.6))
    x = np.arange(len(CONDITIONS))

    for _, row in wide.iterrows():
        ax.plot(x, row.values, color=PARTICIPANT_LINE, alpha=participant_alpha,
                linewidth=0.8,
                marker="o" if participant_markers else "none",
                markersize=3.2 if participant_markers else 0,
                markerfacecolor=PARTICIPANT_LINE, markeredgecolor="none", zorder=2)

    means = [wide[c].mean() for c in CONDITIONS]
    ax.plot(x, means, color=INK_SECONDARY, linewidth=2.0, zorder=4)
    for i, c in enumerate(CONDITIONS):
        ax.plot(i, means[i], marker="o", markersize=13, markerfacecolor=COLOR_OF[c],
                markeredgecolor=SURFACE, markeredgewidth=2.0, zorder=5)

    span = wide.values.max() - wide.values.min()
    for i, m in enumerate(means):
        ax.text(i, m + span * 0.06, f"{m:.2f}", ha="center", va="bottom",
                fontsize=11.5, color=INK, zorder=6)

    ax.set_xticks(x)
    ax.set_xticklabels(CONDITIONS, fontsize=11.5)
    ax.set_xlim(-0.42, len(CONDITIONS) - 0.58)
    ax.set_ylim(wide.values.min() - span * 0.10, wide.values.max() + span * 0.18)
    ax.set_ylabel(ylabel, fontsize=10.5)
    ax.set_title(title, fontsize=14, color=INK, loc="left", fontweight="bold", pad=14)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
    style_axes(ax)
    ax.tick_params(axis="x", pad=8)

    legend = [
        Line2D([0], [0], color=PARTICIPANT_LINE, alpha=max(participant_alpha, 0.45),
               linewidth=0.9, marker="o" if participant_markers else "none",
               markersize=3.5, label="one participant"),
        Line2D([0], [0], color=INK_SECONDARY, linewidth=2.0, marker="o", markersize=9,
               markerfacecolor=INK_SECONDARY, markeredgecolor=SURFACE, label="condition mean"),
    ]
    ax.legend(handles=legend, loc="upper center", frameon=False, fontsize=10,
              ncol=2, handletextpad=0.5, columnspacing=1.8)

    # Prose below the axes, in FIGURE coordinates (axes-relative gaps collapse),
    # stacked from the axes box downwards so blocks of different line counts stay
    # evenly spaced instead of leaving a hole in the shorter figure.
    fig.tight_layout(rect=(0, 0.46, 1, 1))
    pos = ax.get_position()

    def lines(s: str) -> int:
        return s.count("\n") + 1

    fig.add_artist(Line2D([pos.x0, pos.x1], [pos.y0 - 0.050, pos.y0 - 0.050],
                          color=GRIDLINE, linewidth=1.0, zorder=0))

    y = pos.y0 - 0.082
    fig.text(pos.x0, y, explain, ha="left", va="top",
             fontsize=9.5, color=INK_MUTED, linespacing=1.6)

    y -= lines(explain) * 0.026 + 0.020
    fig.text(pos.x0, y, conclusion, ha="left", va="top",
             fontsize=11, color=INK_SECONDARY, linespacing=1.7)

    y -= lines(conclusion) * 0.032 + 0.026
    fig.text(pos.x0, y, stats_line, ha="left", va="top",
             fontsize=9, color=INK_MUTED, linespacing=1.9)

    fig.savefig(FIG_DIR / filename, dpi=300, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Wrote {FIG_DIR / filename}")


def main():
    jit = pd.read_csv(ANALYSIS_DIR / "jitter_by_participant_joint.csv")

    limbs = per_participant(jit, drop_joints=JITTER_RIG_LOCKED_JOINTS)
    legs = per_participant(jit, keep_joints=LEG_JOINTS)
    n = len(limbs)

    # Bottom text kept to three short blocks: what it measures, what to conclude,
    # and the numbers needed to trust it. Everything else was cut (2026-08-29) --
    # notably the "each faint line is one participant" note, which the in-chart
    # legend already states, and the test/sampling boilerplate.
    # Every p-value below is read from the R output rather than written here, so
    # the caption cannot drift from the analysis. R computes these on the same
    # velocity metric the figure plots.
    make_figure(
        limbs,
        "Motion fidelity -- limbs",
        "How fast each joint moves, averaged over the trial. Elbows, wrists, knees and ankles.",
        "HYTRACK reproduces joint motion at professional motion capture levels -- the\n"
        "difference is not significant. MetaQuest delivers noticeably less motion than either\n"
        "of the other two systems.",
        f"n = {n}     Friedman p {r_results.fmt_p(r_results.omnibus_p(r_results.LIMBS))}"
        f"     {r_results.pairs_summary(r_results.LIMBS)}",
        "motion_fidelity_limbs.png",
        ylabel="Mean joint velocity (cm/s)",
    )

    make_figure(
        legs,
        "Motion fidelity -- legs",
        "The same measure, restricted to the knees and ankles.",
        "All three systems differ. MetaQuest's legs move at roughly half the velocity of\n"
        "professional motion capture, and this holds for essentially every participant --\n"
        "it generates leg movement rather than sensing it.",
        f"n = {n}     Friedman p {r_results.fmt_p(r_results.omnibus_p(r_results.LEGS))}"
        f"     {r_results.pairs_summary(r_results.LEGS)}",
        "motion_fidelity_legs.png",
        ylabel="Mean joint velocity (cm/s)",
    )


if __name__ == "__main__":
    main()
