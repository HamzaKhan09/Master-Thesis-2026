"""
Figures for the HYTRACK-vs-MetaQuest comparison, built on top of analyze_study_data.py
and stats_analysis.py outputs (StudyData/analysis/*.csv).

Produces (StudyData/analysis/figures/, 300dpi PNG):
  fig1_paired_wholebody.png   - paired per-participant MPJPE + jitter, HYTRACK vs MetaQuest
  fig2_per_joint_bars.png     - mean +/- SD per joint per condition, MPJPE + jitter,
                                 significance markers from the Holm-corrected per-joint tests
  fig3_power_sensitivity.png  - power-vs-effect-size curves for n=19 (MPJPE) and n=20 (jitter),
                                 observed dz and the power=0.80 target marked

Run with:  conda run -n thesis-eval python plot_study_data.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from pathlib import Path
from scipy import stats

from stats_analysis import JITTER_RIG_LOCKED_JOINTS

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = ROOT / "StudyData" / "analysis"
FIG_DIR = ANALYSIS_DIR / "figures"
FIG_DIR.mkdir(exist_ok=True)

# --- palette (dataviz skill reference palette, categorical slots 1 & 2) ---
BLUE = "#2a78d6"     # HYTRACK
ORANGE = "#eb6834"   # MetaQuest
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
SURFACE = "#fcfcfb"

CONDITION_COLOR = {"HYTRACK": BLUE, "MetaQuest": ORANGE}
CONDITION_MARKER = {"HYTRACK": "o", "MetaQuest": "s"}
CONDITION_HATCH = {"HYTRACK": "", "MetaQuest": "///"}

JOINT_ORDER = [
    "head",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle",
]

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 9,
    "text.color": INK,
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": INK_SECONDARY,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "figure.facecolor": "#f9f9f7",
    "axes.facecolor": SURFACE,
})


def style_axes(ax, ygrid=True):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    if ygrid:
        ax.yaxis.grid(True, color=GRIDLINE, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


# --------------------------------------------------------------------------- #
# Figure 1: paired per-participant, whole-body
# --------------------------------------------------------------------------- #

def whole_body_wide(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    wb = df.groupby(["participant_id", "condition"])[value_col].mean().reset_index()
    wide = wb.pivot(index="participant_id", columns="condition", values=value_col)
    return wide.dropna(subset=["HYTRACK", "MetaQuest"])


def plot_paired_panel(ax, wide: pd.DataFrame, ylabel: str, title: str):
    x_h, x_m = 0, 1
    for pid, row in wide.iterrows():
        ax.plot([x_h, x_m], [row["HYTRACK"], row["MetaQuest"]],
                color=INK_MUTED, alpha=0.35, linewidth=1.0, zorder=1)
    ax.scatter([x_h] * len(wide), wide["HYTRACK"], marker=CONDITION_MARKER["HYTRACK"],
               s=34, color=CONDITION_COLOR["HYTRACK"], edgecolor=SURFACE, linewidth=0.6,
               zorder=3, label="HYTRACK")
    ax.scatter([x_m] * len(wide), wide["MetaQuest"], marker=CONDITION_MARKER["MetaQuest"],
               s=34, color=CONDITION_COLOR["MetaQuest"], edgecolor=SURFACE, linewidth=0.6,
               zorder=3, label="MetaQuest")

    for x, col in [(x_h, "HYTRACK"), (x_m, "MetaQuest")]:
        mean = wide[col].mean()
        ax.plot([x - 0.12, x + 0.12], [mean, mean], color=INK, linewidth=2.0, zorder=4)

    ax.set_xlim(-0.5, 1.5)
    ax.set_xticks([x_h, x_m])
    ax.set_xticklabels(["HYTRACK", "MetaQuest"])
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10, color=INK, loc="left")
    style_axes(ax)

    diff = wide["HYTRACK"] - wide["MetaQuest"]
    dz = diff.mean() / diff.std(ddof=1) if diff.std(ddof=1) > 0 else np.nan
    _, p = stats.ttest_rel(wide["HYTRACK"], wide["MetaQuest"])
    ax.text(0.98, 0.02, f"n={len(wide)}, dz={dz:.2f}, p={p:.3f}",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=8, color=INK_SECONDARY)


def make_figure1(mpjpe: pd.DataFrame, jitter: pd.DataFrame):
    # Jitter panel excludes head/shoulders/hips: in both rigs these move almost
    # rigidly with the hip (near-zero relative displacement -- a construction
    # artifact, not real smoothness; see JITTER_RIG_LOCKED_JOINTS). MPJPE is a
    # static offset, not a frame-to-frame delta, so it isn't affected and keeps
    # all 13 joints.
    jitter_limbs = jitter[~jitter.joint.isin(JITTER_RIG_LOCKED_JOINTS)]

    fig, axes = plt.subplots(1, 2, figsize=(8, 4.2))
    plot_paired_panel(axes[0], whole_body_wide(mpjpe, "mpjpe_m"),
                       "MPJPE (m)", "Whole-body accuracy")
    plot_paired_panel(axes[1], whole_body_wide(jitter_limbs, "jitter_rms_m"),
                       "Jitter RMS (m)", "Whole-body smoothness (limb joints only)")
    handles = [
        Line2D([0], [0], marker=CONDITION_MARKER["HYTRACK"], color=CONDITION_COLOR["HYTRACK"],
               linestyle="", markersize=6, label="HYTRACK"),
        Line2D([0], [0], marker=CONDITION_MARKER["MetaQuest"], color=CONDITION_COLOR["MetaQuest"],
               linestyle="", markersize=6, label="MetaQuest"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, 1.1), fontsize=9)
    axes[0].text(0.0, -0.14, "Thin line = one participant (HYTRACK -> MetaQuest); "
                              "bold tick = condition mean.",
                 transform=axes[0].transAxes, ha="left", va="top",
                 fontsize=7.5, color=INK_MUTED)
    axes[1].text(0.0, -0.14, "Head/shoulders/hips excluded: near-rigid relative to the\n"
                              "hip in both rigs (construction artifact), not real smoothness.",
                 transform=axes[1].transAxes, ha="left", va="top",
                 fontsize=7.5, color=INK_MUTED)
    fig.tight_layout(rect=(0, 0.06, 1, 0.92))
    fig.savefig(FIG_DIR / "fig1_paired_wholebody.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Figure 2: per-joint grouped bars
# --------------------------------------------------------------------------- #

def plot_joint_bars(ax, df: pd.DataFrame, value_col: str, sig_df: pd.DataFrame,
                     ylabel: str, title: str):
    summary = (
        df.groupby(["joint", "condition"])[value_col]
        .agg(["mean", "std"]).reset_index()
    )
    joints = [j for j in JOINT_ORDER if j in summary.joint.unique()]
    x = np.arange(len(joints))
    width = 0.36

    for i, cond in enumerate(["HYTRACK", "MetaQuest"]):
        sub = summary[summary.condition == cond].set_index("joint").reindex(joints)
        offset = (i - 0.5) * width
        ax.bar(x + offset, sub["mean"], width=width * 0.92,
               color=CONDITION_COLOR[cond], hatch=CONDITION_HATCH[cond],
               edgecolor=INK, linewidth=0.5, label=cond, zorder=3)
        ax.errorbar(x + offset, sub["mean"], yerr=sub["std"], fmt="none",
                     ecolor=INK_SECONDARY, elinewidth=0.8, capsize=2, zorder=4)

    sig_lookup = sig_df.set_index("joint")["significant_after_holm"].to_dict()
    ymax = (summary["mean"] + summary["std"]).max()
    for xi, j in zip(x, joints):
        if sig_lookup.get(j):
            ax.text(xi, ymax * 1.06, "*", ha="center", va="bottom",
                    fontsize=13, color=INK)

    ax.set_xticks(x)
    ax.set_xticklabels([j.replace("_", " ") for j in joints], rotation=45, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10, color=INK, loc="left")
    ax.set_ylim(0, ymax * 1.18)
    style_axes(ax)


def make_figure2(mpjpe: pd.DataFrame, jitter: pd.DataFrame,
                  mpjpe_sig: pd.DataFrame, jitter_sig: pd.DataFrame):
    fig, axes = plt.subplots(2, 1, figsize=(8.5, 8))
    plot_joint_bars(axes[0], mpjpe, "mpjpe_m", mpjpe_sig,
                     "MPJPE (m)", "Accuracy by joint  (* = significant after Holm correction)")
    plot_joint_bars(axes[1], jitter, "jitter_rms_m", jitter_sig,
                     "Jitter RMS (m)", "Smoothness by joint  (* = significant after Holm correction)")
    handles = [
        plt.Rectangle((0, 0), 1, 1, facecolor=CONDITION_COLOR["HYTRACK"], edgecolor=INK,
                       linewidth=0.5, label="HYTRACK"),
        plt.Rectangle((0, 0), 1, 1, facecolor=CONDITION_COLOR["MetaQuest"], edgecolor=INK,
                       linewidth=0.5, hatch=CONDITION_HATCH["MetaQuest"], label="MetaQuest"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, 1.015))
    fig.text(0.5, -0.01, "Note (smoothness panel): head/shoulders/hips read near-zero because "
                         "they move almost rigidly with the hip in both rigs (a construction "
                         "artifact, not superior tracking) -- excluded from the whole-body jitter "
                         "figure/stats for this reason; see fig1 and stats_analysis.py.",
             ha="center", fontsize=7.5, color=INK_MUTED, wrap=True)
    fig.tight_layout(rect=(0, 0.025, 1, 1))
    fig.savefig(FIG_DIR / "fig2_per_joint_bars.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Figure 3: power / sensitivity curves
# --------------------------------------------------------------------------- #

def paired_power(dz: float, n: int, alpha: float = 0.05) -> float:
    df = n - 1
    t_crit = stats.t.ppf(1 - alpha / 2, df)
    ncp = dz * np.sqrt(n)
    lower = stats.nct.cdf(-t_crit, df, ncp)
    lower = 0.0 if not np.isfinite(lower) else lower
    return float(np.clip(stats.nct.sf(t_crit, df, ncp) + lower, 0.0, 1.0))


def make_figure3(mpjpe_dz: float, jitter_dz: float, n_mpjpe: int, n_jitter: int):
    fig, ax = plt.subplots(figsize=(7, 4.5))
    dz_grid = np.linspace(0.01, 2.0, 300)

    for n, dz_obs, color, label in [
        (n_mpjpe, mpjpe_dz, BLUE, f"MPJPE (n={n_mpjpe})"),
        (n_jitter, jitter_dz, ORANGE, f"Jitter, limb joints only (n={n_jitter})"),
    ]:
        power_curve = [paired_power(dz, n) for dz in dz_grid]
        ax.plot(dz_grid, power_curve, color=color, linewidth=2.0, label=label, zorder=3)
        ax.scatter([dz_obs], [paired_power(dz_obs, n)], color=color, s=40,
                   edgecolor=SURFACE, linewidth=0.8, zorder=4)
        ax.annotate(f"observed dz={dz_obs:.2f}", xy=(dz_obs, paired_power(dz_obs, n)),
                    xytext=(6, -4 if color == BLUE else 10), textcoords="offset points",
                    fontsize=8, color=INK_SECONDARY)

    ax.axhline(0.80, color=INK_MUTED, linewidth=1.0, linestyle="--", zorder=2)
    ax.text(0.02, 0.815, "power = 0.80 target", transform=ax.get_yaxis_transform(),
            fontsize=8, color=INK_MUTED)

    ax.set_xlabel("Effect size (Cohen's dz)")
    ax.set_ylabel("Statistical power (1-β)")
    ax.set_title("Power sensitivity: HYTRACK vs MetaQuest paired t-test, α=0.05",
                 fontsize=10, color=INK, loc="left")
    ax.set_xlim(0, 2.0)
    ax.set_ylim(0, 1.05)
    style_axes(ax)
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig3_power_sensitivity.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    mpjpe = pd.read_csv(ANALYSIS_DIR / "mpjpe_by_participant_joint.csv")
    jitter = pd.read_csv(ANALYSIS_DIR / "jitter_by_participant_joint.csv")
    per_joint = pd.read_csv(ANALYSIS_DIR / "paired_test_per_joint.csv")
    wholebody = pd.read_csv(ANALYSIS_DIR / "paired_test_wholebody_summary.csv")

    mpjpe_sig = per_joint[per_joint.metric == "MPJPE (m)"]
    jitter_sig = per_joint[per_joint.metric == "Jitter RMS (m)"]

    make_figure1(mpjpe, jitter)
    make_figure2(mpjpe, jitter, mpjpe_sig, jitter_sig)

    mpjpe_row = wholebody[wholebody.metric == "MPJPE (whole-body, m)"].iloc[0]
    jitter_row = wholebody[wholebody.metric == "Jitter (whole-body, limb joints only, RMS m)"].iloc[0]
    make_figure3(mpjpe_row.cohens_dz, jitter_row.cohens_dz,
                 int(mpjpe_row.n), int(jitter_row.n))

    print(f"Wrote figures to {FIG_DIR}:")
    for f in sorted(FIG_DIR.glob("*.png")):
        print(f"  {f.name}")


if __name__ == "__main__":
    main()
