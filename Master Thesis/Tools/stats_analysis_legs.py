"""
Same paired HYTRACK-vs-MetaQuest comparison as stats_analysis.py, restricted to
leg joints only (left/right knee + ankle -- same "Legs" region as plot_study_data_simple.py's
REGIONS, hips excluded since they're the root-relative reference joint).

Only MPJPE and Jitter are decomposable per-joint, so only those two metrics are
covered here. Tracking dropout / robustness is logged once per participant per
session (frame-delivery timing, not per-joint), so there is no "legs-only dropout"
number to compute -- see stats_table_legs.png's Robustness row for how that's stated.

Run with:  conda run -n thesis-eval python stats_analysis_legs.py
"""
from __future__ import annotations

import pandas as pd

from stats_analysis import ANALYSIS_DIR, run_metric, print_summary

LEG_JOINTS = {"left_knee", "right_knee", "left_ankle", "right_ankle"}


def main():
    mpjpe = pd.read_csv(ANALYSIS_DIR / "mpjpe_by_participant_joint.csv")
    jitter = pd.read_csv(ANALYSIS_DIR / "jitter_by_participant_joint.csv")

    mpjpe_legs = mpjpe[mpjpe.joint.isin(LEG_JOINTS)]
    jitter_legs = jitter[jitter.joint.isin(LEG_JOINTS)]

    summary_rows = []

    r_mpjpe, _ = run_metric("MPJPE (legs, m)", mpjpe_legs, "mpjpe_m")
    print_summary(r_mpjpe)
    summary_rows.append(r_mpjpe)

    r_jitter, _ = run_metric("Jitter (legs, RMS m)", jitter_legs, "jitter_rms_m")
    print_summary(r_jitter)
    summary_rows.append(r_jitter)

    summary_df = pd.DataFrame(summary_rows).drop(columns=["excluded_participants"])
    out = ANALYSIS_DIR / "paired_test_legs_summary.csv"
    summary_df.to_csv(out, index=False)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
