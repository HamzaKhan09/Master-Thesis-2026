"""
Accuracy analysis that does NOT require simultaneous capture.

WHY THIS EXISTS: per-frame MPJPE against OptiTrack is invalid for this study --
OptiTrack was a separate counterbalanced condition, recorded in its own block
(0 of 38 condition trials overlap with their OptiTrack trial in wall-clock time;
see project memory project_mpjpe_invalid_no_simultaneous_capture). There is no
frame correspondence to recover, so any per-frame error measure is meaningless.

Everything computed here is invariant to when a frame was captured, so all three
conditions stay comparable despite being recorded minutes apart:

  1. SEGMENT LENGTH ACCURACY -- a person's bones do not change length, so the
     limb lengths a system reports can be compared against OptiTrack's
     marker-based values without aligning a single frame. This is the direct
     replacement for MPJPE, and its units (cm of limb-length error) are
     interpretable in a way root-relative MPJPE never was.

  2. SEGMENT LENGTH CONSISTENCY -- within one trial a real bone length is
     constant, so any within-trial variation is tracking error by definition.
     Reported as coefficient of variation (SD / mean), which is unit-free and
     therefore fair across limbs of different sizes. This is a standard validity
     check in the markerless motion-capture literature.

  3. JOINT ANGLE RANGE OF MOTION -- angles are scale-invariant, so they sidestep
     the skeleton-size mismatch entirely. Because all three conditions ran the
     same movement battery, the range of motion each system reports is
     comparable even though the actual repetitions differ.

This also matches field practice: validation of markerless against marker-based
systems is normally reported with joint-angle error and agreement statistics
rather than raw position error.

Produces:
  StudyData/analysis/segment_lengths_by_participant.csv
  StudyData/analysis/joint_angles_by_participant.csv
  StudyData/analysis/accuracy_vs_optitrack_summary.csv   (error vs OptiTrack)
  StudyData/analysis/accuracy_consistency_summary.csv    (3-way CV comparison)

Run with:  conda run -n thesis-eval python stats_analysis_accuracy.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from analyze_study_data import (
    OUT_DIR, load_all, candidate_windows, select_best_windows,
    extract_trial_long, hip_relative_wide,
)
from stats_analysis_3way import CONDITIONS, run_metric as friedman_metric

AXES = ["x", "y", "z"]

# Bone segments whose length is anatomically fixed. Left/right kept separate so a
# one-sided tracking failure is visible rather than averaged away.
SEGMENTS = {
    "Thigh (L)": ("left_hip", "left_knee"),
    "Thigh (R)": ("right_hip", "right_knee"),
    "Shank (L)": ("left_knee", "left_ankle"),
    "Shank (R)": ("right_knee", "right_ankle"),
    "Upper arm (L)": ("left_shoulder", "left_elbow"),
    "Upper arm (R)": ("right_shoulder", "right_elbow"),
    "Forearm (L)": ("left_elbow", "left_wrist"),
    "Forearm (R)": ("right_elbow", "right_wrist"),
    "Shoulder width": ("left_shoulder", "right_shoulder"),
}

# Interior angle at the middle joint: 180 deg = fully extended.
ANGLES = {
    "Knee (L)": ("left_hip", "left_knee", "left_ankle"),
    "Knee (R)": ("right_hip", "right_knee", "right_ankle"),
    "Elbow (L)": ("left_shoulder", "left_elbow", "left_wrist"),
    "Elbow (R)": ("right_shoulder", "right_elbow", "right_wrist"),
}

MIN_FRAMES = 10


# --------------------------------------------------------------------------- #
# Per-frame geometry
# --------------------------------------------------------------------------- #

def _has(wide: pd.DataFrame, *joints: str) -> bool:
    return all(j in wide["x"].columns for j in joints)


def segment_length(wide: pd.DataFrame, a: str, b: str) -> pd.Series:
    """Euclidean distance per frame. Hip-centring is a per-frame translation, so
    distances between joints inside a frame are unaffected by it."""
    return np.sqrt(sum((wide[ax][a] - wide[ax][b]) ** 2 for ax in AXES)).dropna()


def joint_angle_deg(wide: pd.DataFrame, a: str, mid: str, c: str) -> pd.Series:
    """Interior angle at `mid`, in degrees (180 = straight)."""
    va = np.stack([(wide[ax][a] - wide[ax][mid]).values for ax in AXES], axis=1)
    vc = np.stack([(wide[ax][c] - wide[ax][mid]).values for ax in AXES], axis=1)
    na = np.linalg.norm(va, axis=1)
    nc = np.linalg.norm(vc, axis=1)
    ok = (na > 1e-6) & (nc > 1e-6)
    cos = np.full(len(va), np.nan)
    cos[ok] = np.sum(va[ok] * vc[ok], axis=1) / (na[ok] * nc[ok])
    return pd.Series(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))).dropna()


def measure_trial(participant_id: str, condition: str, wide: pd.DataFrame):
    seg_rows, ang_rows = [], []

    for name, (a, b) in SEGMENTS.items():
        if not _has(wide, a, b):
            continue
        L = segment_length(wide, a, b)
        if len(L) < MIN_FRAMES:
            continue
        mean = float(L.mean())
        sd = float(L.std(ddof=1))
        seg_rows.append({
            "participant_id": participant_id, "condition": condition, "segment": name,
            "n_frames": int(len(L)), "length_mean_m": mean, "length_sd_m": sd,
            "length_cv_pct": 100.0 * sd / mean if mean > 0 else np.nan,
        })

    for name, (a, mid, c) in ANGLES.items():
        if not _has(wide, a, mid, c):
            continue
        ang = joint_angle_deg(wide, a, mid, c)
        if len(ang) < MIN_FRAMES:
            continue
        p5, p95 = np.percentile(ang, [5, 95])
        ang_rows.append({
            "participant_id": participant_id, "condition": condition, "joint": name,
            "n_frames": int(len(ang)),
            "angle_mean_deg": float(ang.mean()),
            "angle_min_deg": float(ang.min()),
            # robust range: 5th-95th percentile, so a single bad frame cannot define ROM
            "rom_deg": float(p95 - p5),
        })

    return seg_rows, ang_rows


# --------------------------------------------------------------------------- #
# Comparison against OptiTrack (no frame alignment needed)
# --------------------------------------------------------------------------- #

def error_vs_optitrack(df: pd.DataFrame, key: str, value_col: str) -> pd.DataFrame:
    """Signed difference from the same participant's OptiTrack value."""
    wide = df.pivot_table(index=["participant_id", key], columns="condition", values=value_col)
    wide = wide.dropna(subset=CONDITIONS)
    out = []
    for cond in ["HYTRACK", "MetaQuest"]:
        e = (wide[cond] - wide["OptiTrack"]).reset_index()
        e.columns = ["participant_id", key, "error"]
        e["condition"] = cond
        out.append(e)
    return pd.concat(out, ignore_index=True)


def summarise_error(err: pd.DataFrame, key: str, unit: str) -> pd.DataFrame:
    rows = []
    for name, g in err.groupby(key):
        w = g.pivot(index="participant_id", columns="condition", values="error").dropna()
        if len(w) < 3:
            continue
        h, m = w["HYTRACK"].values, w["MetaQuest"].values
        # tested on ABSOLUTE error: the question is which system is closer to
        # OptiTrack, not which one is biased in which direction
        try:
            stat, p = stats.wilcoxon(np.abs(h), np.abs(m))
            stat, p = float(stat), float(p)
        except ValueError:
            stat, p = np.nan, np.nan
        rows.append({
            key: name, "n": len(w), "unit": unit,
            "hytrack_signed_mean": float(h.mean()), "hytrack_signed_sd": float(h.std(ddof=1)),
            "metaquest_signed_mean": float(m.mean()), "metaquest_signed_sd": float(m.std(ddof=1)),
            "hytrack_abs_mean": float(np.abs(h).mean()), "hytrack_abs_sd": float(np.abs(h).std(ddof=1)),
            "metaquest_abs_mean": float(np.abs(m).mean()), "metaquest_abs_sd": float(np.abs(m).std(ddof=1)),
            "wilcoxon_stat_abs_err": stat, "p_abs_err": p,
            "closer_system": ("HYTRACK" if np.abs(h).mean() < np.abs(m).mean() else "MetaQuest")
                              if np.isfinite(p) and p < 0.05 else "no reliable difference",
        })
    return pd.DataFrame(rows)


def main():
    joints, joints_opti, events, events_opti, _ = load_all()
    best = select_best_windows(candidate_windows(events))
    best_opti = select_best_windows(candidate_windows(events_opti))

    seg_rows, ang_rows = [], []
    for source, windows, forced in ((joints, best, None), (joints_opti, best_opti, "OptiTrack")):
        for _, w in windows.iterrows():
            wide = hip_relative_wide(extract_trial_long(source, w))
            if wide is None:
                continue
            s, a = measure_trial(w.participant_id, forced or w.condition, wide)
            seg_rows += s
            ang_rows += a

    seg = pd.DataFrame(seg_rows)
    ang = pd.DataFrame(ang_rows)
    seg.to_csv(OUT_DIR / "segment_lengths_by_participant.csv", index=False)
    ang.to_csv(OUT_DIR / "joint_angles_by_participant.csv", index=False)

    # ---- 1. accuracy: distance from OptiTrack ---- #
    seg_err = summarise_error(
        error_vs_optitrack(seg, "segment", "length_mean_m"), "segment", "m")
    ang_err = summarise_error(
        error_vs_optitrack(ang, "joint", "rom_deg"), "joint", "deg")
    seg_err.insert(0, "measure", "Segment length")
    ang_err.insert(0, "measure", "Joint range of motion")
    seg_err = seg_err.rename(columns={"segment": "item"})
    ang_err = ang_err.rename(columns={"joint": "item"})
    acc = pd.concat([seg_err, ang_err], ignore_index=True)
    acc.to_csv(OUT_DIR / "accuracy_vs_optitrack_summary.csv", index=False)

    print("=== 1. Accuracy: difference from OptiTrack (no frame alignment needed) ===")
    print("    signed mean +/- SD, then |error|, then Wilcoxon on |error| (HYTRACK vs MetaQuest)\n")
    for _, r in acc.iterrows():
        u = r["unit"]
        scale, us = (100.0, "cm") if u == "m" else (1.0, "deg")
        print(f"  {r['measure']:<22} {r['item']:<16} n={r['n']:<3} "
              f"HYTRACK {r.hytrack_signed_mean*scale:+6.2f}{us} (|{r.hytrack_abs_mean*scale:.2f}|)   "
              f"MetaQuest {r.metaquest_signed_mean*scale:+6.2f}{us} (|{r.metaquest_abs_mean*scale:.2f}|)   "
              f"p={r.p_abs_err:.4f}  -> {r.closer_system}")

    # ---- 2. consistency: within-trial length variation, all three conditions ---- #
    cons_rows, post_rows = [], []
    for name, g in seg.groupby("segment"):
        wide = g.pivot_table(index="participant_id", columns="condition",
                             values="length_cv_pct").dropna(subset=CONDITIONS)[CONDITIONS]
        if len(wide) < 3:
            continue
        s, ph = friedman_metric(f"Length consistency -- {name} (CV %)", wide)
        cons_rows.append(s)
        post_rows += ph
    cons = pd.DataFrame(cons_rows)
    cons.to_csv(OUT_DIR / "accuracy_consistency_summary.csv", index=False)
    pd.DataFrame(post_rows).to_csv(OUT_DIR / "accuracy_consistency_posthoc.csv", index=False)

    print("\n=== 2. Bone-length consistency within a trial (CV %, lower = steadier) ===")
    print("    a real bone cannot change length, so all variation here is tracking error\n")
    for _, r in cons.iterrows():
        print(f"  {r['metric']:<44} HYTRACK {r.hytrack_mean:5.2f}%   "
              f"MetaQuest {r.metaquest_mean:5.2f}%   OptiTrack {r.optitrack_mean:5.2f}%   "
              f"Friedman p={r.friedman_p:.2g}")

    # ---- 3. does the system adapt limb length to the person? ---- #
    print("\n=== 3. Between-participant variation in reported limb length (m) ===")
    print("    near zero => the same skeleton is used for everyone, not scaled to the individual\n")
    spread = seg.groupby(["segment", "condition"]).length_mean_m.std().unstack()[CONDITIONS]
    print(spread.round(4).to_string())

    print(f"\nWrote {OUT_DIR / 'segment_lengths_by_participant.csv'}")
    print(f"Wrote {OUT_DIR / 'joint_angles_by_participant.csv'}")
    print(f"Wrote {OUT_DIR / 'accuracy_vs_optitrack_summary.csv'}")
    print(f"Wrote {OUT_DIR / 'accuracy_consistency_summary.csv'}")


if __name__ == "__main__":
    main()
