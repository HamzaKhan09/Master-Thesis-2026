"""
Leg-only version of plot_scorecard_full.py -- same 3-system comparison, restricted
to the leg joints (left/right knee + ankle).

Only Accuracy and Smoothness are shown: MPJPE and Jitter are logged per-joint, so
they can be restricted to legs, but tracking dropout / robustness is logged once
per participant per session (frame-delivery timing), not per-joint -- there is no
real "legs-only dropout" number, so that panel is replaced with a text note rather
than a fabricated bar. Same reasoning as leaving Latency off scorecard_full.png.

Produces: StudyData/analysis/figures/scorecard_legs_comparison.png

Run with:  MPLBACKEND=Agg conda run -n thesis-eval python plot_scorecard_legs.py
"""
from __future__ import annotations

import pandas as pd
import matplotlib.pyplot as plt

from plot_study_data_simple import ANALYSIS_DIR, FIG_DIR, INK, INK_MUTED, whole_body_wide
from plot_scorecard_full import plot_metric_row

LEG_JOINTS = {"left_knee", "right_knee", "left_ankle", "right_ankle"}


def make_scorecard(mpjpe: pd.DataFrame, jitter: pd.DataFrame):
    fig, axes = plt.subplots(2, 1, figsize=(7.5, 9.0))

    mpjpe_legs = mpjpe[mpjpe.joint.isin(LEG_JOINTS)]
    plot_metric_row(
        axes[0], whole_body_wide(mpjpe_legs, "mpjpe_m"),
        "Accuracy -- legs", "Position error vs. OptiTrack ground truth (m)",
        "knees + ankles only, vs. OptiTrack -- lower is better",
        "{:.3f} m", show_opti=False,
    )

    jitter_legs = jitter[jitter.joint.isin(LEG_JOINTS)]
    plot_metric_row(
        axes[1], whole_body_wide(jitter_legs, "jitter_rms_m"),
        "Smoothness -- legs", "Jitter, knees + ankles only (m)",
        "frame-to-frame stability, legs only -- lower is better",
        "{:.3f} m", show_opti=False,
    )

    fig.suptitle("HYTRACK vs MetaQuest vs OptiTrack -- legs only", fontsize=14, color=INK,
                 x=0.02, ha="left", y=0.995)
    fig.text(0.02, 0.955,
              "Robustness (dropout) and Latency are not shown: both are logged once per session, "
              "not per joint, so there is no legs-only\nnumber to compute -- see the whole-body "
              "scorecard for those two metrics.",
              fontsize=8.5, color=INK_MUTED, ha="left", va="top")

    fig.tight_layout(rect=(0, 0.0, 1, 0.89), h_pad=6.0)
    fig.savefig(FIG_DIR / "scorecard_legs_comparison.png", dpi=300, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    mpjpe = pd.read_csv(ANALYSIS_DIR / "mpjpe_by_participant_joint.csv")
    jitter = pd.read_csv(ANALYSIS_DIR / "jitter_by_participant_joint.csv")

    make_scorecard(mpjpe, jitter)
    print(f"Wrote {FIG_DIR / 'scorecard_legs_comparison.png'}")


if __name__ == "__main__":
    main()
