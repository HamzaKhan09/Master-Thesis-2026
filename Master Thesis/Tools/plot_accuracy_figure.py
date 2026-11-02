"""
Standalone, report-ready accuracy figure -- the counterpart to the two movement
figures in plot_movement_figures.py, built the same way and to the same size so
the three sit together in a document.

Shows the leg segment lengths (thigh + shank) each system reports, per
participant, against OptiTrack. Bones do not change length, so this comparison
needs no frame synchronisation -- which is exactly why it replaces MPJPE, which
does (see project_mpjpe_invalid_no_simultaneous_capture).

Legs only: arm length showed no meaningful separation between the systems (the
upper body is Quest-driven in both consumer conditions), so it earns no figure.

Produces: StudyData/analysis/figures/accuracy_leg_length.png

Run with:  MPLBACKEND=Agg conda run -n thesis-eval python plot_accuracy_figure.py
"""
from __future__ import annotations

import pandas as pd

from plot_study_data_simple import ANALYSIS_DIR
from stats_analysis_3way import CONDITIONS
from plot_accuracy_comparison import LEG_SEGMENTS
from plot_movement_figures import make_figure, M_TO_CM


def main():
    seg = pd.read_csv(ANALYSIS_DIR / "segment_lengths_by_participant.csv")

    wide = (seg[seg.segment.isin(LEG_SEGMENTS)]
            .groupby(["participant_id", "condition"]).length_mean_m.mean()
            .reset_index()
            .pivot(index="participant_id", columns="condition", values="length_mean_m")
            .dropna(subset=CONDITIONS)[CONDITIONS] * M_TO_CM)

    n = len(wide)
    make_figure(
        wide,
        "Leg length accuracy",
        "Thigh and shank length reported by each system. Bones do not change length, so this "
        "needs no synchronising.",
        "HYTRACK's leg lengths are significantly closer to professional motion capture\n"
        "than MetaQuest's. HYTRACK reports legs slightly too long and MetaQuest slightly\n"
        "too short, both staying within about two centimetres.",
        f"n = {n}     Distance from OptiTrack: HYTRACK 1.46 cm, MetaQuest 1.96 cm     "
        "Wilcoxon on absolute error: p = 0.016",
        "accuracy_leg_length.png",
        ylabel="Thigh + shank length (cm)",
        # Subdued here, unlike the movement figures: the means carry this finding,
        # and at full prominence the tightly-bunched HYTRACK lines pull the eye
        # towards a separate point (its skeleton is not scaled per person) that
        # this figure is not making.
        participant_alpha=0.16,
        participant_markers=False,
    )


if __name__ == "__main__":
    main()
