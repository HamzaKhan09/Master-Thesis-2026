"""
Professor-facing scorecard: HYTRACK vs MetaQuest vs OptiTrack, all three
systems shown on every panel where that's not circular.

Differs from plot_scorecard.py (the 2-bar HYTRACK-vs-MetaQuest version kept
for the plain-language/thesis-body use case -- see feedback_layman_figures):
  - Accuracy:    still 2 bars only (HYTRACK, MetaQuest). OptiTrack IS the
                 ground truth MPJPE is measured against, so an "OptiTrack
                 accuracy" bar would be 0 by definition -- shown as a caption
                 note instead of a bar.
  - Smoothness:  2 bars (HYTRACK, MetaQuest). OptiTrack's own jitter is genuine,
                 non-circular data -- but showing it as a 3rd bar reads as "least
                 accurate" to a reader, since OptiTrack (labeled ground truth)
                 ends up with the tallest bar. It's raw, unsmoothed per-frame
                 sensor noise, not lower tracking quality -- true, but a bar
                 chart can't carry that nuance, so it's back to 2 bars (2026-08-27).
                 OptiTrack's jitter number stays documented in stats_table.png
                 and in project memory, just not on this chart.
  - Robustness:  3 bars (HYTRACK, MetaQuest, OptiTrack) -- OptiTrack scoring
                 lowest/best here matches intuition, so no confusion risk.
  - Latency:     left out entirely (not just off the chart -- there is no
                 usable number). latency_log.csv's input_time_ms is empty in
                 100% of rows; report this as a data-collection limitation in
                 the write-up text, not on this figure.

The HYTRACK-vs-MetaQuest significance verdict (paired t-test/Wilcoxon) is
unchanged from plot_scorecard.py. OptiTrack's bar is descriptive context, not
a third arm of that statistical test -- it did not go through the same paired
comparison, so no significance claim is attached to it.

Produces: StudyData/analysis/figures/scorecard_full_comparison.png

Run with:  MPLBACKEND=Agg conda run -n thesis-eval python plot_scorecard_full.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from scipy import stats as sstats

from plot_study_data_simple import (
    ANALYSIS_DIR, FIG_DIR,
    CONDITION_COLOR, CONDITION_HATCH, GOOD_GREEN, INK, INK_MUTED,
    style_axes, whole_body_wide, verdict,
)
from stats_analysis import JITTER_RIG_LOCKED_JOINTS

OPTI_COLOR = "#6b6f76"
OPTI_HATCH = ".."
OPTI_LABEL = "OptiTrack"


def ci95_halfwidth(values: pd.Series) -> float:
    """95% CI half-width via the t-distribution (appropriate for n<30)."""
    v = values.dropna()
    n = len(v)
    if n < 2:
        return 0.0
    sd = v.std(ddof=1)
    return float(sstats.t.ppf(0.975, n - 1) * sd / np.sqrt(n))


def plot_metric_row(ax, wide: pd.DataFrame, title: str, ylabel: str, caption: str,
                     unit_fmt: str, lower_is_better: bool = True, show_opti: bool = True):
    v = verdict(wide)
    has_opti = show_opti and "OptiTrack" in wide.columns and wide["OptiTrack"].notna().any()

    cols = ["HYTRACK", "MetaQuest"] + (["OptiTrack"] if has_opti else [])
    labels = list(cols)
    vals = [wide[c].dropna().mean() for c in cols]
    errs = [ci95_halfwidth(wide[c]) for c in cols]
    colors = [CONDITION_COLOR["HYTRACK"], CONDITION_COLOR["MetaQuest"]] + ([OPTI_COLOR] if has_opti else [])
    hatches = [CONDITION_HATCH["HYTRACK"], CONDITION_HATCH["MetaQuest"]] + ([OPTI_HATCH] if has_opti else [])
    width = 0.45 if not has_opti else 0.55

    bars = ax.bar(range(len(labels)), vals, width=width, color=colors, hatch=hatches,
                   edgecolor=INK, linewidth=0.6, zorder=3,
                   yerr=errs, capsize=5,
                   error_kw=dict(ecolor=INK, elinewidth=1.1, capthick=1.1, zorder=4))
    for bar, val, err in zip(bars, vals, errs):
        ax.text(bar.get_x() + bar.get_width() / 2, val + err, unit_fmt.format(val),
                ha="center", va="bottom", fontsize=10, color=INK)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels([OPTI_LABEL if l == "OptiTrack" else l for l in labels], fontsize=9.5)

    direction = "lower" if lower_is_better else "higher"
    if v["significant"]:
        winner = "MetaQuest" if (v["m_mean"] < v["h_mean"]) == lower_is_better else "HYTRACK"
        verdict_text = f"{winner} wins -- {abs(v['pct']):.0f}% {direction}, a real difference"
        color = GOOD_GREEN
    else:
        verdict_text = "No reliable difference -- neither system wins here"
        color = INK_MUTED

    ax.set_ylim(0, max(v + e for v, e in zip(vals, errs)) * 1.35)
    ax.set_title(title, fontsize=13, color=INK, loc="left", fontweight="bold")
    ax.set_ylabel(ylabel, fontsize=9)
    style_axes(ax)

    ax.text(0.5, -0.22, verdict_text, transform=ax.transAxes, ha="center", va="top",
            fontsize=10.5, color=color, fontweight="bold")
    caption_suffix = "  (verdict is HYTRACK vs MetaQuest only -- OptiTrack is context, not a tested arm)" if has_opti else ""
    ax.text(0.5, -0.32, f"{caption}  (n={v['n']}, p={v['p']:.3f}, error bars = 95% CI){caption_suffix}",
            transform=ax.transAxes, ha="center", va="top", fontsize=7.5, color=INK_MUTED)


def make_scorecard(mpjpe: pd.DataFrame, jitter: pd.DataFrame, continuity: pd.DataFrame):
    fig, axes = plt.subplots(3, 1, figsize=(7.5, 14))

    plot_metric_row(
        axes[0], whole_body_wide(mpjpe, "mpjpe_m"),
        "Accuracy", "Position error vs. OptiTrack ground truth (m)",
        "OptiTrack IS the ground truth here (its own error is 0 by definition) -- lower is better",
        "{:.3f} m", show_opti=False,
    )

    jitter_limbs = jitter[~jitter.joint.isin(JITTER_RIG_LOCKED_JOINTS)]
    plot_metric_row(
        axes[1], whole_body_wide(jitter_limbs, "jitter_rms_m"),
        "Smoothness", "Jitter, limb joints only (m)",
        "frame-to-frame stability (elbows/wrists/knees/ankles) -- lower is better",
        "{:.3f} m", show_opti=False,
    )

    plot_metric_row(
        axes[2], whole_body_wide(continuity, "pct_gaps_over_1_5x_expected"),
        "Robustness", "Frames with timing gaps (%)",
        "tracking dropout rate -- lower is better",
        "{:.3f}%",
    )

    fig.suptitle("HYTRACK vs MetaQuest vs OptiTrack -- results by metric", fontsize=14, color=INK,
                 x=0.02, ha="left", y=0.995)
    fig.text(0.02, 0.955, "Latency is not shown: the logging data needed to compute it "
                          "was empty for every recorded trial (see write-up).",
             fontsize=8.5, color=INK_MUTED, ha="left", va="top")

    fig.tight_layout(rect=(0, 0.0, 1, 0.90), h_pad=8.0)
    fig.savefig(FIG_DIR / "scorecard_full_comparison.png", dpi=300, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    mpjpe = pd.read_csv(ANALYSIS_DIR / "mpjpe_by_participant_joint.csv")
    jitter = pd.read_csv(ANALYSIS_DIR / "jitter_by_participant_joint.csv")
    continuity = pd.read_csv(ANALYSIS_DIR / "tracking_continuity_by_participant.csv")

    make_scorecard(mpjpe, jitter, continuity)
    print(f"Wrote {FIG_DIR / 'scorecard_full_comparison.png'}")


if __name__ == "__main__":
    main()
