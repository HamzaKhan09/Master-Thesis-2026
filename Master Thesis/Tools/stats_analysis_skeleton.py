"""
Two accuracy measures that need NO simultaneous ground truth, because physics
supplies the truth instead of OptiTrack.

WHY THESE EXIST: MPJPE is unavailable (OptiTrack was a separate recording block,
so no frame correspondence exists -- see project_mpjpe_invalid_no_simultaneous_capture),
and mean segment length turned out to measure body-model BIAS rather than
per-person accuracy. These two measures are immune to both problems.

  1. SKELETON CONSISTENCY (rigid-body violation)
     A bone cannot change length. Any variation in a segment's length within a
     single trial is therefore measurement error, and its standard deviation is a
     lower bound on the per-frame position error of the joints at its ends. This
     is a standard validation criterion in the markerless motion-capture
     literature and requires no reference system at all.

     Segments are split into LEGS and ARMS because that split is an internal
     control: in both HMD conditions the arms come from the same Quest tracking,
     so arm consistency should be similar across them, while the legs are the
     experimental manipulation.

  2. PHYSICAL PLAUSIBILITY
     A knee or ankle cannot teleport. Frame-to-frame joint speed above a
     conservative screening threshold indicates a tracking failure rather than
     movement. This complements robustness: robustness asks whether frames
     ARRIVED, this asks whether the frames CONTAINED a plausible pose.

INTERPRETATION WARNING carried into the figure: a low value is not automatically
good. A system that synthesises a limb from a kinematic model can report near-zero
bone-length variation for a limb it never observed. The legs-vs-arms contrast
within a single system is what separates "precise" from "not actually measuring".

Produces:
  StudyData/analysis/skeleton_consistency_by_participant.csv
  StudyData/analysis/plausibility_by_participant.csv

Run with:  conda run -n thesis-eval python stats_analysis_skeleton.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from stats_analysis import ANALYSIS_DIR
from stats_analysis_3way import CONDITIONS

ROOT = ANALYSIS_DIR.parent          # StudyData/
PILOT = "P00"
M_TO_CM = 100.0

LEG_SEGMENTS = ["Thigh (L)", "Thigh (R)", "Shank (L)", "Shank (R)"]
ARM_SEGMENTS = ["Upper arm (L)", "Upper arm (R)", "Forearm (L)", "Forearm (R)"]
# Shoulder width is deliberately excluded: OptiTrack tracks real scapular
# movement there while both HMD rigs use a fixed shoulder, so it measures a rig
# difference rather than tracking error.

LEG_JOINTS = ["left_knee", "right_knee", "left_ankle", "right_ankle"]

# Conservative screening threshold. Chosen far above anything achievable in a
# standing VR game -- the point is to detect teleporting joints, not to police
# fast movement, so the exact value is not doing any statistical work.
SPEED_THRESHOLD_MS = 5.0
# Frame intervals outside this range mean a gap or a duplicate timestamp, not a
# real inter-frame step, so they cannot yield a meaningful speed.
DT_MIN_S, DT_MAX_S = 0.05, 0.5


def skeleton_consistency() -> pd.DataFrame:
    """Per participant, condition and segment group: mean within-trial SD of
    segment length, in cm. That SD is the implied per-frame joint position error."""
    seg = pd.read_csv(ANALYSIS_DIR / "segment_lengths_by_participant.csv")
    seg = seg[seg.participant_id != PILOT].copy()

    group = {s: "Legs" for s in LEG_SEGMENTS}
    group.update({s: "Arms" for s in ARM_SEGMENTS})
    seg["group"] = seg.segment.map(group)
    seg = seg.dropna(subset=["group"])

    seg["sd_cm"] = seg.length_sd_m * M_TO_CM
    out = (seg.groupby(["participant_id", "condition", "group"])
           .agg(sd_cm=("sd_cm", "mean"),
                cv_pct=("length_cv_pct", "mean"),
                length_cm=("length_mean_m", lambda s: s.mean() * M_TO_CM),
                n_segments=("segment", "nunique"))
           .reset_index())
    return out[out.condition.isin(CONDITIONS)]


def plausibility() -> pd.DataFrame:
    """Per participant and condition: the fastest leg-joint speed observed, and
    the share of inter-frame steps that exceed the screening threshold."""
    cols = ["participant_id", "condition", "session_id", "timestamp_ms",
            "joint", "x", "y", "z"]
    jp = pd.read_csv(ROOT / "joint_positions.csv", usecols=cols)
    op = pd.read_csv(ROOT / "Optitrack_joint_positions.csv", usecols=cols)
    op["condition"] = "OptiTrack"

    raw = pd.concat([jp, op], ignore_index=True)
    raw = raw[(raw.participant_id != PILOT) & (raw.joint.isin(LEG_JOINTS))]

    rows = []
    for (pid, cond, sess, joint), g in raw.groupby(
            ["participant_id", "condition", "session_id", "joint"], sort=False):
        g = g.sort_values("timestamp_ms")
        step = np.sqrt(g.x.diff() ** 2 + g.y.diff() ** 2 + g.z.diff() ** 2)
        dt = g.timestamp_ms.diff() / 1000.0
        usable = dt.between(DT_MIN_S, DT_MAX_S)
        speed = (step / dt)[usable].dropna()
        if speed.empty:
            continue
        rows.append({"participant_id": pid, "condition": cond, "joint": joint,
                     "n_steps": int(len(speed)),
                     "max_speed_ms": float(speed.max()),
                     "p999_speed_ms": float(speed.quantile(0.999)),
                     "n_over_threshold": int((speed > SPEED_THRESHOLD_MS).sum())})

    per_joint = pd.DataFrame(rows)
    # One row per participant per condition: the worst joint, and the pooled rate.
    out = (per_joint.groupby(["participant_id", "condition"])
           .agg(max_speed_ms=("max_speed_ms", "max"),
                p999_speed_ms=("p999_speed_ms", "max"),
                n_steps=("n_steps", "sum"),
                n_over_threshold=("n_over_threshold", "sum"))
           .reset_index())
    out["pct_over_threshold"] = out.n_over_threshold / out.n_steps * 100
    return out[out.condition.isin(CONDITIONS)]


def main():
    cons = skeleton_consistency()
    plaus = plausibility()

    out_c = ANALYSIS_DIR / "skeleton_consistency_by_participant.csv"
    out_p = ANALYSIS_DIR / "plausibility_by_participant.csv"
    cons.to_csv(out_c, index=False)
    plaus.to_csv(out_p, index=False)

    print("=== Skeleton consistency: within-trial SD of segment length (cm) ===")
    piv = cons.pivot_table(index="condition", columns="group", values="sd_cm")
    print(piv.round(4).to_string())
    print("\n  A bone cannot change length, so these ARE per-frame position errors.")
    print("  Read the legs-vs-arms contrast within each system, not just across systems:")
    for c in CONDITIONS:
        if c in piv.index and piv.loc[c, "Arms"] > 0:
            ratio = piv.loc[c, "Legs"] / piv.loc[c, "Arms"]
            direction = "noisier" if ratio > 1 else "MORE rigid"
            print(f"    {c:<10} legs are {max(ratio, 1/ratio):5.1f}x {direction} than its own arms")

    print("\n=== Physical plausibility of leg-joint motion ===")
    pp = plaus.groupby("condition").agg(
        max_speed_ms=("max_speed_ms", "max"),
        mean_peak_ms=("max_speed_ms", "mean"),
        pct_over_threshold=("pct_over_threshold", "mean"))
    print(pp.round(4).to_string())
    print(f"\n  screening threshold = {SPEED_THRESHOLD_MS} m/s")
    worst = plaus.max_speed_ms.max()
    print(f"  fastest joint speed anywhere in the dataset: {worst:.2f} m/s "
          f"-> {'NO' if worst < SPEED_THRESHOLD_MS else 'SOME'} implausible motion")

    print(f"\nWrote {out_c}")
    print(f"Wrote {out_p}")


if __name__ == "__main__":
    main()
