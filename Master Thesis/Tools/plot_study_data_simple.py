"""
Plain-language companion to plot_study_data.py -- same underlying numbers, but
built for a reader without a stats background: no dz/p/Holm jargon on the chart
face, 13 joints collapsed to 3 body regions, and one plain-English verdict per
chart. Exact statistics are kept in a small caption line for anyone who wants
to trace a chart back to the numbers, and in the console/CSV outputs.

Produces (StudyData/analysis/figures/, 300dpi PNG):
  simple1_overall_comparison.png  - two big bars per metric (whole-body means)
                                     with a plain-English verdict + % difference
  simple2_by_body_region.png      - joints collapsed to Head / Arms / Legs
  simple3_confidence_gauge.png    - "how likely were we to catch a real
                                     difference" as a 0-100% gauge per metric

Run with:  conda run -n thesis-eval python plot_study_data_simple.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = ROOT / "StudyData" / "analysis"
FIG_DIR = ANALYSIS_DIR / "figures"
FIG_DIR.mkdir(exist_ok=True)

BLUE = "#2a78d6"     # HYTRACK
ORANGE = "#eb6834"   # MetaQuest
GOOD_GREEN = "#0ca30c"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
SURFACE = "#fcfcfb"

CONDITION_COLOR = {"HYTRACK": BLUE, "MetaQuest": ORANGE}
CONDITION_HATCH = {"HYTRACK": "", "MetaQuest": "///"}

# Hips excluded: positions are expressed relative to the hip midpoint, so hip
# error/jitter is ~0 by construction, not a real result.
REGIONS = {
    "Head": ["head"],
    "Arms": ["left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
             "left_wrist", "right_wrist"],
    "Legs": ["left_knee", "right_knee", "left_ankle", "right_ankle"],
}

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 11,
    "text.color": INK,
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": INK_SECONDARY,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "figure.facecolor": "#f9f9f7",
    "axes.facecolor": SURFACE,
})


def style_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.yaxis.grid(True, color=GRIDLINE, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def whole_body_wide(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    wb = df.groupby(["participant_id", "condition"])[value_col].mean().reset_index()
    wide = wb.pivot(index="participant_id", columns="condition", values=value_col)
    return wide.dropna(subset=["HYTRACK", "MetaQuest"])


def verdict(wide: pd.DataFrame) -> dict:
    diff = wide["HYTRACK"] - wide["MetaQuest"]
    dz = diff.mean() / diff.std(ddof=1) if diff.std(ddof=1) > 0 else np.nan
    _, p = stats.ttest_rel(wide["HYTRACK"], wide["MetaQuest"])
    h_mean, m_mean = wide["HYTRACK"].mean(), wide["MetaQuest"].mean()
    pct = (m_mean - h_mean) / h_mean * 100
    return dict(n=len(wide), dz=dz, p=p, h_mean=h_mean, m_mean=m_mean, pct=pct,
                significant=p < 0.05)


# --------------------------------------------------------------------------- #
# Figure 1: overall comparison, plain language
# --------------------------------------------------------------------------- #

def make_figure1(mpjpe: pd.DataFrame, jitter: pd.DataFrame):
    specs = [
        ("Tracking accuracy", "Average position error (m) -- lower is better",
         whole_body_wide(mpjpe, "mpjpe_m")),
        ("Tracking smoothness", "Frame-to-frame jitter (m) -- lower is better",
         whole_body_wide(jitter, "jitter_rms_m")),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(9, 5))

    for ax, (title, ylabel, wide) in zip(axes, specs):
        v = verdict(wide)
        bars = ax.bar(["HYTRACK", "MetaQuest"], [v["h_mean"], v["m_mean"]],
                       width=0.55,
                       color=[CONDITION_COLOR["HYTRACK"], CONDITION_COLOR["MetaQuest"]],
                       hatch=[CONDITION_HATCH["HYTRACK"], CONDITION_HATCH["MetaQuest"]],
                       edgecolor=INK, linewidth=0.6, zorder=3)
        for bar, val in zip(bars, [v["h_mean"], v["m_mean"]]):
            ax.text(bar.get_x() + bar.get_width() / 2, val, f"{val:.3f}",
                    ha="center", va="bottom", fontsize=10, color=INK)

        if v["significant"]:
            verdict_text = f"MetaQuest was {abs(v['pct']):.0f}% " \
                            f"{'lower' if v['pct'] < 0 else 'higher'} -- a real difference"
            color = GOOD_GREEN
        else:
            verdict_text = "No reliable difference between the two systems"
            color = INK_MUTED
        ax.text(0.5, -0.22, verdict_text, transform=ax.transAxes, ha="center", va="top",
                fontsize=10.5, color=color, fontweight="bold", wrap=True)
        ax.text(0.5, -0.30, f"(n={v['n']} participants, p={v['p']:.3f})",
                transform=ax.transAxes, ha="center", va="top",
                fontsize=8, color=INK_MUTED)

        ax.set_title(title, fontsize=13, color=INK, loc="center", pad=10)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_ylim(0, max(v["h_mean"], v["m_mean"]) * 1.25)
        style_axes(ax)

    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(FIG_DIR / "simple1_overall_comparison.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Figure 2: by body region (Head / Arms / Legs)
# --------------------------------------------------------------------------- #

def region_wide(df: pd.DataFrame, value_col: str, joints: list[str]) -> pd.DataFrame:
    sub = df[df.joint.isin(joints)]
    return whole_body_wide(sub, value_col)


def plot_region_panel(ax, df: pd.DataFrame, value_col: str, ylabel: str, title: str):
    region_names = list(REGIONS.keys())
    x = np.arange(len(region_names))
    width = 0.36
    h_vals, m_vals, sig_flags = [], [], []

    for region in region_names:
        wide = region_wide(df, value_col, REGIONS[region])
        v = verdict(wide)
        h_vals.append(v["h_mean"])
        m_vals.append(v["m_mean"])
        sig_flags.append(v["significant"])

    ax.bar(x - width / 2, h_vals, width=width * 0.92, color=CONDITION_COLOR["HYTRACK"],
           edgecolor=INK, linewidth=0.5, label="HYTRACK", zorder=3)
    ax.bar(x + width / 2, m_vals, width=width * 0.92, color=CONDITION_COLOR["MetaQuest"],
           hatch=CONDITION_HATCH["MetaQuest"], edgecolor=INK, linewidth=0.5,
           label="MetaQuest", zorder=3)

    ymax = max(h_vals + m_vals)
    for xi, sig, hv, mv in zip(x, sig_flags, h_vals, m_vals):
        label = "meaningful\ndifference" if sig else "no clear\ndifference"
        color = GOOD_GREEN if sig else INK_MUTED
        marker = "✓" if sig else "–"
        bar_top = max(hv, mv)
        ax.text(xi, bar_top + ymax * 0.06, f"{marker} {label}", ha="center", va="bottom",
                fontsize=8.5, color=color, linespacing=1.3)

    ax.set_xticks(x)
    ax.set_xticklabels(region_names, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=12, color=INK, loc="left")
    ax.set_ylim(0, ymax * 1.38)
    style_axes(ax)


def make_figure2(mpjpe: pd.DataFrame, jitter: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.8))
    plot_region_panel(axes[0], mpjpe, "mpjpe_m", "Position error (m)", "Accuracy")
    plot_region_panel(axes[1], jitter, "jitter_rms_m", "Jitter (m)", "Smoothness")

    handles = [
        mpatches.Patch(facecolor=CONDITION_COLOR["HYTRACK"], edgecolor=INK,
                        linewidth=0.5, label="HYTRACK"),
        mpatches.Patch(facecolor=CONDITION_COLOR["MetaQuest"], edgecolor=INK,
                        linewidth=0.5, hatch=CONDITION_HATCH["MetaQuest"], label="MetaQuest"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, 1.1), fontsize=10)
    fig.text(0.5, -0.02, "Hips are excluded -- they define the body's reference "
                         "point, so their error is always ~0 by construction.",
             ha="center", fontsize=8, color=INK_MUTED)
    fig.tight_layout(rect=(0, 0.02, 1, 0.9))
    fig.savefig(FIG_DIR / "simple2_by_body_region.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Figure 3: confidence gauge (plain-language power)
# --------------------------------------------------------------------------- #

def paired_power(dz: float, n: int, alpha: float = 0.05) -> float:
    df = n - 1
    t_crit = stats.t.ppf(1 - alpha / 2, df)
    ncp = dz * np.sqrt(n)
    lower = stats.nct.cdf(-t_crit, df, ncp)
    lower = 0.0 if not np.isfinite(lower) else lower
    return float(np.clip(stats.nct.sf(t_crit, df, ncp) + lower, 0.0, 1.0))


def make_figure3(mpjpe_wide: pd.DataFrame, jitter_wide: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8, 3.2))

    rows = []
    for name, wide in [("Accuracy test\n(MPJPE)", mpjpe_wide),
                        ("Smoothness test\n(jitter)", jitter_wide)]:
        v = verdict(wide)
        power = paired_power(v["dz"], v["n"]) * 100
        rows.append((name, power, v["n"]))

    y = np.arange(len(rows))
    for yi, (name, power, n) in zip(y, rows):
        ax.barh(yi, 100, height=0.5, color=GRIDLINE, zorder=2)
        color = GOOD_GREEN if power >= 80 else "#eda100" if power >= 50 else INK_MUTED
        ax.barh(yi, power, height=0.5, color=color, zorder=3)
        ax.text(power + 2, yi, f"{power:.0f}%", va="center", fontsize=11,
                color=INK, fontweight="bold")

    ax.axvline(80, color=INK, linewidth=1.0, linestyle="--", zorder=4)
    ax.text(80, len(rows) - 0.25, " commonly-used\n \"reliable\" threshold",
            fontsize=8, color=INK_SECONDARY, va="bottom")

    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=10.5)
    ax.set_xlim(0, 115)
    ax.set_xlabel("Chance this sample size could have detected a real difference, if one exists",
                  fontsize=9)
    ax.set_title("How much can we trust each 'no difference' / 'difference found' result?",
                 fontsize=12, color=INK, loc="left")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    ax.set_xticks([])

    fig.tight_layout()
    fig.savefig(FIG_DIR / "simple3_confidence_gauge.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    mpjpe = pd.read_csv(ANALYSIS_DIR / "mpjpe_by_participant_joint.csv")
    jitter = pd.read_csv(ANALYSIS_DIR / "jitter_by_participant_joint.csv")

    make_figure1(mpjpe, jitter)
    make_figure2(mpjpe, jitter)
    make_figure3(whole_body_wide(mpjpe, "mpjpe_m"), whole_body_wide(jitter, "jitter_rms_m"))

    print(f"Wrote plain-language figures to {FIG_DIR}:")
    for f in sorted(FIG_DIR.glob("simple*.png")):
        print(f"  {f.name}")


if __name__ == "__main__":
    main()
