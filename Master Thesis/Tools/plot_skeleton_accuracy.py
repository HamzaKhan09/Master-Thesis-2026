"""
Accuracy without ground truth -- the figure for the accuracy section.

Sized and weighted for a SLIDE: landscape, large type, two panels, every bar
labelled with its value so nothing depends on reading a gridline.

Panel A -- skeleton consistency. A bone cannot change length, so within-trial
variation is measurement error. Read the LEGS-vs-ARMS contrast within each
system, not just the heights across systems: arms come from the same Quest
tracking in both HMD conditions and therefore act as a control.
  HYTRACK   legs 2.3x noisier than its own arms -> honest per-frame estimation error
  MetaQuest legs 6.7x MORE rigid than its own arms -> impossible for a real sensor,
            the signature of a leg synthesised from a kinematic model
  OptiTrack legs == arms -> a genuine reference system, equally precise on both

  A log axis is used because the values span three orders of magnitude; on a
  linear axis four of the six bars would be invisible and the MetaQuest
  inversion -- the most informative feature -- would disappear.

Panel B -- physical plausibility. A knee or ankle cannot teleport, so a
frame-to-frame speed above a conservative screening threshold means a tracking
failure rather than movement. Complements robustness: robustness asks whether
frames ARRIVED, this asks whether they contained a plausible pose.

Produces: StudyData/analysis/figures/accuracy_skeleton_consistency.png

Run with:  conda run -n thesis-eval python stats_analysis_skeleton.py   (first)
           conda run -n r-thesis Rscript skeleton.R                     (then)
           MPLBACKEND=Agg conda run -n thesis-eval python plot_skeleton_accuracy.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from plot_study_data_simple import (
    ANALYSIS_DIR, FIG_DIR, INK, INK_SECONDARY, INK_MUTED, GRIDLINE, BASELINE,
    BLUE, ORANGE,
)
from stats_analysis_3way import CONDITIONS
from stats_analysis_skeleton import SPEED_THRESHOLD_MS

OPTI = "#5b8a72"
COLOR = {"HYTRACK": BLUE, "MetaQuest": ORANGE, "OptiTrack": OPTI}
GROUPS = ["Legs", "Arms"]

# type sizes tuned for projection, not for a page
FS_TITLE, FS_LABEL, FS_TICK, FS_VALUE, FS_NOTE = 15, 13.5, 13, 11.5, 10.4


def fmt_cm(v: float) -> str:
    return f"{v:.2f}" if v >= 0.1 else f"{v:.3f}"


def panel_consistency(ax, cons: pd.DataFrame, tests: pd.DataFrame | None):
    piv = cons.pivot_table(index="condition", columns="group", values="sd_cm")
    piv = piv.reindex(CONDITIONS)

    x = np.arange(len(CONDITIONS))
    width = 0.34
    for k, group in enumerate(GROUPS):
        offset = (k - 0.5) * width * 1.06
        vals = piv[group].values
        for xi, cond, v in zip(x + offset, CONDITIONS, vals):
            ax.bar(xi, v, width=width, color=COLOR[cond],
                   alpha=1.0 if group == "Legs" else 0.42,
                   edgecolor="none", zorder=3)
            ax.text(xi, v * 1.13, fmt_cm(v), ha="center", va="bottom",
                    fontsize=FS_VALUE, color=INK, zorder=4)

    ax.set_yscale("log")
    # headroom below the smallest bar so the per-system contrast note can sit
    # under the OptiTrack bars rather than on top of them
    ax.set_ylim(0.0014, 4.6)
    ax.set_xticks(x)
    ax.set_xticklabels(CONDITIONS, fontsize=FS_TICK, color=INK)
    ax.set_ylabel("Bone-length variation within a trial\n(cm, log scale)",
                  fontsize=FS_LABEL, color=INK)
    ax.set_title("Skeleton consistency  —  a bone cannot change length",
                 fontsize=FS_TITLE, color=INK, pad=14, loc="left")
    ax.tick_params(axis="y", labelsize=FS_TICK - 1, colors=INK_SECONDARY)
    ax.tick_params(axis="x", length=0)
    ax.grid(axis="y", color=GRIDLINE, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)

    # legend: solid = legs, faded = arms
    handles = [plt.Rectangle((0, 0), 1, 1, color=INK_SECONDARY, alpha=a)
               for a in (1.0, 0.42)]
    ax.legend(handles, ["Legs  (the manipulation)", "Arms  (control — same Quest tracking)"],
              fontsize=FS_NOTE + 0.6, frameon=False, loc="upper right",
              handlelength=1.5, borderaxespad=0.2)

    # the within-system contrast, stated on the axes where it is read
    if tests is not None:
        for xi, cond in zip(x, CONDITIONS):
            row = tests[tests.condition == cond]
            if row.empty:
                continue
            r = row.iloc[0]
            if not bool(r.significant):
                txt = "legs = arms"
            elif r.ratio_legs_over_arms > 1:
                txt = f"legs {r.ratio_legs_over_arms:.1f}× noisier"
            else:
                txt = f"legs {1 / r.ratio_legs_over_arms:.1f}× more rigid"
            ax.text(xi, 0.00165, txt, ha="center", va="bottom",
                    fontsize=FS_NOTE, color=INK_SECONDARY, style="italic")


def panel_plausibility(ax, plaus: pd.DataFrame):
    rng = np.random.default_rng(0)
    for i, cond in enumerate(CONDITIONS):
        v = plaus[plaus.condition == cond].max_speed_ms.values
        ax.scatter(i + rng.uniform(-0.13, 0.13, len(v)), v, s=42,
                   color=COLOR[cond], alpha=0.65, edgecolor="none", zorder=3)
        ax.plot([i - 0.26, i + 0.26], [v.mean()] * 2, color=COLOR[cond],
                linewidth=2.6, zorder=4)

    ax.axhline(SPEED_THRESHOLD_MS, color=INK_SECONDARY, linewidth=1.4,
               linestyle=(0, (5, 4)), zorder=2)
    ax.text(len(CONDITIONS) - 0.5, SPEED_THRESHOLD_MS + 0.12,
            f"screening threshold  {SPEED_THRESHOLD_MS:.0f} m/s",
            ha="right", va="bottom", fontsize=FS_NOTE, color=INK_SECONDARY)

    ax.set_xticks(np.arange(len(CONDITIONS)))
    ax.set_xticklabels(CONDITIONS, fontsize=FS_TICK, color=INK)
    ax.set_xlim(-0.55, len(CONDITIONS) - 0.45)
    ax.set_ylim(0, 6.4)
    ax.set_ylabel("Fastest leg-joint speed observed (m/s)",
                  fontsize=FS_LABEL, color=INK)
    ax.set_title("Physical plausibility  —  a joint cannot teleport",
                 fontsize=FS_TITLE, color=INK, pad=14, loc="left")
    ax.tick_params(axis="y", labelsize=FS_TICK - 1, colors=INK_SECONDARY)
    ax.tick_params(axis="x", length=0)
    ax.grid(axis="y", color=GRIDLINE, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)


def main():
    cons = pd.read_csv(ANALYSIS_DIR / "skeleton_consistency_by_participant.csv")
    plaus = pd.read_csv(ANALYSIS_DIR / "plausibility_by_participant.csv")
    tests_path = ANALYSIS_DIR / "skeleton_consistency_tests_R.csv"
    tests = pd.read_csv(tests_path) if tests_path.exists() else None
    if tests is None:
        print("  note: skeleton_consistency_tests_R.csv not found -- run "
              "'Rscript skeleton.R' for the within-system contrasts.")

    fig, (ax_l, ax_r) = plt.subplots(
        1, 2, figsize=(13.2, 6.5), gridspec_kw={"width_ratios": [1.58, 1]})
    panel_consistency(ax_l, cons, tests)
    panel_plausibility(ax_r, plaus)

    fig.tight_layout(rect=(0, 0.235, 1, 1))

    mq = tests[tests.condition == "MetaQuest"].iloc[0] if tests is not None else None
    line2 = ("MetaQuest's legs vary {:.0f}× LESS than its own arms — a tracker cannot be "
             "more precise on a limb it never sees. That is the signature of\n"
             "synthesised legs, not measurement. HYTRACK's legs are {:.1f}× noisier than "
             "its arms: real estimation error, about {:.1f} cm per frame."
             ).format(1 / mq.ratio_legs_over_arms,
                      tests[tests.condition == "HYTRACK"].iloc[0].ratio_legs_over_arms,
                      cons[(cons.condition == "HYTRACK") &
                           (cons.group == "Legs")].sd_cm.mean()) if mq is not None else ""

    # Stack the footer explicitly in FIGURE coordinates, tracking how many lines
    # each block occupies -- placing these relative to the axes collapses them
    # into each other.
    x0 = ax_l.get_position().x0
    line_h, gap = 0.042, 0.016
    y = 0.190

    def block(text: str, size: float, color: str) -> float:
        fig.text(x0, y, text, fontsize=size, color=color, ha="left", va="top",
                 linespacing=1.55)
        return y - (text.count("\n") + 1) * line_h - gap

    y = block("A bone cannot change length, so any variation within a trial is "
              "measurement error — this needs no synchronisation with OptiTrack.",
              FS_NOTE + 0.5, INK)
    if line2:
        y = block(line2, FS_NOTE + 0.5, INK_SECONDARY)
    block("n = 20 (19 for OptiTrack).    Paired Wilcoxon signed-rank, legs vs arms "
          "within each system, Holm-corrected.    No condition exceeded the speed "
          "threshold except OptiTrack, in 0.004% of frames.",
          FS_NOTE, INK_MUTED)

    out = FIG_DIR / "accuracy_skeleton_consistency.png"
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
