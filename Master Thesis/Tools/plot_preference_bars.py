"""
Forced-choice preference results (final questionnaire, n = 20) -- standalone
report-ready figure, same size/footer convention as the other report figures
(explain line, plain-language conclusion, stats line; see
plot_robustness_figure.py for the pattern this follows).

100%-stacked horizontal bars, one per item. The first four items asked
participants to pick one system (HYTRACK / MetaQuest / OptiTrack); the last
asked marker-based vs markerless tracking in general and does not map to a
specific system, so it gets its own two-colour pair rather than the system
colours.

PROVENANCE: renders only. Percentages come from preference_counts.csv,
p-values/winners from preference_tests_R.csv (produced by preferences.R) --
both already Holm-corrected across the five items, computed in R.

Produces: StudyData/analysis/figures/preference_results.png

Run with:  conda run -n r-thesis Rscript preferences.R      (first)
           MPLBACKEND=Agg conda run -n thesis-eval python plot_preference_bars.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from plot_study_data_simple import (
    ANALYSIS_DIR, FIG_DIR, SURFACE,
    CONDITION_COLOR, INK, INK_SECONDARY, INK_MUTED, GRIDLINE, BASELINE,
)
from plot_scorecard_full import OPTI_COLOR

R_TESTS = "preference_tests_R.csv"
R_COUNTS = "preference_counts.csv"

COLOR_OF = {
    "HYTRACK": CONDITION_COLOR["HYTRACK"],
    "MetaQuest": CONDITION_COLOR["MetaQuest"],
    "OptiTrack": OPTI_COLOR,
    "Marker-based": INK_SECONDARY,
    "Markerless": "#b8b6ac",
}
# dark-filled choices get light text, light-filled choices get dark text
LIGHT_TEXT_CHOICES = {"HYTRACK", "OptiTrack", "Marker-based"}

ITEM_ORDER = [
    "Felt most like real legs",
    "Responded fastest",
    "Preferred for regular VR use",
    "Would pick for personal use",
    "Marker-based vs markerless",
]
CHOICE_ORDER = {item: ["HYTRACK", "MetaQuest", "OptiTrack"] for item in ITEM_ORDER[:-1]}
CHOICE_ORDER["Marker-based vs markerless"] = ["Marker-based", "Markerless"]

LABEL_MIN_PCT = 15  # segments narrower than this skip their inline % label


def fmt_p(p: float) -> str:
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def load():
    counts_path = ANALYSIS_DIR / R_COUNTS
    tests_path = ANALYSIS_DIR / R_TESTS
    if not tests_path.exists():
        raise SystemExit(
            f"{R_TESTS} not found -- the statistics are computed in R.\n"
            f"Run first:  conda run -n r-thesis Rscript preferences.R")
    if counts_path.exists() and counts_path.stat().st_mtime > tests_path.stat().st_mtime:
        raise SystemExit(
            f"{R_TESTS} is older than {R_COUNTS}.\n"
            f"Re-run:  conda run -n r-thesis Rscript preferences.R")

    counts = pd.read_csv(counts_path)
    tests = pd.read_csv(tests_path).set_index("item")
    return counts, tests


def main():
    counts, tests = load()
    n_items = len(ITEM_ORDER)
    n = int(tests["n"].iloc[0])

    fig, ax = plt.subplots(figsize=(10.8, 6.2))

    for row_i, item in enumerate(ITEM_ORDER):
        y = n_items - 1 - row_i
        left = 0.0
        sub = counts[counts["item"] == item].set_index("choice")
        for choice in CHOICE_ORDER[item]:
            if choice not in sub.index:
                continue
            pct = float(sub.loc[choice, "pct"])
            ax.barh(y, pct, left=left, height=0.62, color=COLOR_OF[choice],
                    edgecolor=SURFACE, linewidth=1.2, zorder=3)
            if pct >= LABEL_MIN_PCT:
                text_color = SURFACE if choice in LIGHT_TEXT_CHOICES else INK
                ax.text(left + pct / 2, y, f"{pct:.0f}%", ha="center", va="center",
                        fontsize=10, color=text_color, fontweight="bold", zorder=4)
            left += pct

        t = tests.loc[item]
        p_str = f"p = {fmt_p(float(t['p_holm']))}"
        if not bool(t["significant"]):
            p_str += "  (n.s.)"
        ax.text(103, y, p_str, ha="left", va="center", fontsize=9.5, color=INK_MUTED)

    ax.set_yticks(range(n_items))
    ax.set_yticklabels([ITEM_ORDER[n_items - 1 - i] for i in range(n_items)], fontsize=10.5)
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"], fontsize=9.5)
    ax.set_ylim(-0.6, n_items - 0.4)
    for x in (25, 50, 75):
        ax.axvline(x, color=GRIDLINE, linewidth=0.8, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(length=0)
    ax.set_title("Forced-choice preferences", fontsize=14, color=INK, loc="left",
                 fontweight="bold", pad=14)

    handles = [Line2D([0], [0], marker="s", linestyle="none", markersize=11,
                      markerfacecolor=COLOR_OF[c], markeredgecolor="none", label=c)
               for c in ["HYTRACK", "MetaQuest", "OptiTrack"]]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.44, -0.14),
              frameon=False, fontsize=10, ncol=3, handletextpad=0.5, columnspacing=1.8)

    fig.tight_layout(rect=(0, 0.32, 1, 1))
    pos = ax.get_position()
    fig.add_artist(Line2D([pos.x0, pos.x1], [pos.y0 - 0.075, pos.y0 - 0.075],
                          color=GRIDLINE, linewidth=1.0, zorder=0))

    explain = ("Each of the first four items asked participants to pick one system after "
               "trying all three; the last asked marker-based vs markerless tracking in "
               "general (dark = marker-based, light = markerless), not tied to a system.")
    conclusion = ("OptiTrack felt most like real legs and responded fastest, but participants\n"
                  "preferred HYTRACK by the same wide margin for actual use. MetaQuest was\n"
                  "chosen in only 2 of 80 system-choice votes across the four items.")
    stats_line = (f"n = {n}     Chi-square goodness-of-fit (3-choice items) / exact binomial "
                  "(2-choice item), Holm-corrected across all five items.")

    y = pos.y0 - 0.105
    fig.text(pos.x0, y, explain, ha="left", va="top",
             fontsize=9.5, color=INK_MUTED, linespacing=1.6)
    y -= 1 * 0.026 + 0.020
    fig.text(pos.x0, y, conclusion, ha="left", va="top",
             fontsize=11, color=INK_SECONDARY, linespacing=1.7)
    y -= 3 * 0.032 + 0.026
    fig.text(pos.x0, y, stats_line, ha="left", va="top",
             fontsize=9, color=INK_MUTED, linespacing=1.9)

    fig.savefig(FIG_DIR / "preference_results.png", dpi=300, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Wrote {FIG_DIR / 'preference_results.png'}")


if __name__ == "__main__":
    main()
