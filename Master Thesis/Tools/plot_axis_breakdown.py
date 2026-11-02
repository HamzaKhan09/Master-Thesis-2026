"""
Per-axis (X / Y / Z) breakdown of tracking error vs. OptiTrack ground truth.
Whole-body MPJPE collapses a position error to one Euclidean number, which
hides where that error actually comes from. This figure splits it back into
its three axis components, collapsed to the same three body regions as
simple2_by_body_region.png (Head / Arms / Legs, hips excluded).

Not a HYTRACK-vs-MetaQuest comparison -- each condition gets its own panel,
because the point here is which axis is weakest, and both systems turn out
to share the same weak axis (Z / depth-from-camera), for the same underlying
reason: both are RGB-camera-based pose estimators, and depth is the axis a
single camera has the least direct information about.

Produces: StudyData/analysis/figures/axis_breakdown.png

Run with:  conda run -n thesis-eval python plot_axis_breakdown.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from plot_study_data_simple import (
    ANALYSIS_DIR, FIG_DIR, REGIONS,
    INK,
    style_axes,
)

# Fixed categorical order, X/Y/Z never re-cycled. Chosen to avoid a red/green
# adjacent pair (common CVD confusion) while still letting Z read as the
# "flagged" axis via the verdict text below the chart, not via a louder hue.
AXIS_COLOR = {"X": "#4c7a8c", "Y": "#7a5c99", "Z": "#c0392b"}
AXIS_LABEL = {"X": "X -- lateral", "Y": "Y -- vertical", "Z": "Z -- depth"}
AXES = ["X", "Y", "Z"]
COND_ORDER = ["HYTRACK", "MetaQuest"]


def region_axis_table(df: pd.DataFrame, condition: str) -> pd.DataFrame:
    region_of = {j: r for r, js in REGIONS.items() for j in js}
    sub = df[df.condition == condition].copy()
    sub["region"] = sub.joint.map(region_of)
    sub = sub.dropna(subset=["region"])
    g = (
        sub.groupby("region")[["err_x_abs_mean_m", "err_y_abs_mean_m", "err_z_abs_mean_m"]]
        .mean()
        .reindex(list(REGIONS.keys()))
    )
    g.columns = AXES
    return g


def plot_panel(ax, table: pd.DataFrame, title: str, ymax: float):
    regions = list(table.index)
    x = np.arange(len(regions))
    width = 0.24

    for i, axis in enumerate(AXES):
        offset = (i - 1) * width
        bars = ax.bar(x + offset, table[axis], width=width * 0.92,
                       color=AXIS_COLOR[axis], edgecolor=INK, linewidth=0.4, zorder=3)
        if axis == "Z":
            for bar, val in zip(bars, table[axis]):
                ax.text(bar.get_x() + bar.get_width() / 2, val, f"{val:.2f}",
                        ha="center", va="bottom", fontsize=7.5, color=INK)

    ax.set_xticks(x)
    ax.set_xticklabels(regions, fontsize=10.5)
    ax.set_ylabel("Mean absolute error per axis (m)", fontsize=9)
    ax.set_title(title, fontsize=12.5, color=INK, loc="left", fontweight="bold")
    ax.set_ylim(0, ymax)
    style_axes(ax)


def make_figure(mpjpe: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6))
    tables = {c: region_axis_table(mpjpe, c) for c in COND_ORDER}
    ymax = max(t.values.max() for t in tables.values()) * 1.28
    for ax, condition in zip(axes, COND_ORDER):
        plot_panel(ax, tables[condition], condition, ymax)

    handles = [
        mpatches.Patch(facecolor=AXIS_COLOR[a], edgecolor=INK, linewidth=0.4, label=AXIS_LABEL[a])
        for a in AXES
    ]
    fig.legend(handles=handles, loc="upper center", ncol=3, frameon=False,
               bbox_to_anchor=(0.5, 1.04), fontsize=9.5)

    fig.tight_layout(rect=(0, 0, 1, 0.90))
    fig.savefig(FIG_DIR / "axis_breakdown.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def main():
    mpjpe = pd.read_csv(ANALYSIS_DIR / "mpjpe_by_participant_joint.csv")
    make_figure(mpjpe)
    print(f"Wrote {FIG_DIR / 'axis_breakdown.png'}")


if __name__ == "__main__":
    main()
