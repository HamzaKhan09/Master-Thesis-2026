"""
Frame-level re-analysis of HYTRACK vs MetaQuest, as a genuinely different
(not just re-run-in-a-different-library) look at the same raw data behind
stats_analysis.py.

The paired t-test/Wilcoxon in stats_analysis.py first collapses every frame in
a session down to ONE mean value per participant per condition, then tests
n=19/20 paired numbers. That throws away all of the within-session frame-level
variability. This script instead keeps every individual frame as its own
observation (~20-30k frames per metric) and estimates the HYTRACK-vs-MetaQuest
difference via a **participant-level cluster bootstrap**: resample participants
with replacement (not frames), pool all of each resampled participant's frames,
recompute the condition-mean difference, repeat 3000x, take the 2.5/97.5
percentiles as the CI. Resampling participants (not frames) is what keeps this
honest -- frames from the same person are correlated, so treating them as 3000
independent observations would understate uncertainty and manufacture
significance out of nothing.

(An earlier version of this script used a linear mixed-effects model --
value ~ condition + (1 | participant_id) via statsmodels -- instead of the
bootstrap. Dropped after the model's random-intercept variance kept hitting a
convergence boundary and its p-value for Accuracy disagreed with this bootstrap
check: see project_stats_analysis_results memory for the comparison. The
bootstrap doesn't depend on that variance estimate at all, so it's the one
being kept and reported.)

Re-derives per-frame values from the same raw logs analyze_study_data.py reads
(StudyData/joint_positions.csv, Optitrack_joint_positions.csv, trial_events.csv)
using its own window-resolution / temporal-alignment functions, so the frames
are built exactly the same way as the numbers already in the thesis -- only the
statistical test at the end differs.

Run with:  conda run -n thesis-eval python stats_analysis_mixed.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analyze_study_data import (
    OUT_DIR, JOINTS, RESAMPLE_DT, MIN_TRIAL_S,
    load_all, candidate_windows, select_best_windows,
    extract_trial_long, hip_relative_wide, raw_hip_y,
    best_lag_seconds, resample_wide,
)
from stats_analysis_legs import LEG_JOINTS
from stats_analysis import JITTER_RIG_LOCKED_JOINTS


def mpjpe_frames(participant_id, condition, cond_wide_shifted, opti_wide, joints=JOINTS):
    t0 = max(cond_wide_shifted.index.min(), opti_wide.index.min())
    t1 = min(cond_wide_shifted.index.max(), opti_wide.index.max())
    if t1 - t0 < MIN_TRIAL_S:
        return []
    grid = np.arange(t0, t1, RESAMPLE_DT)
    cond_r = resample_wide(cond_wide_shifted, grid)
    opti_r = resample_wide(opti_wide, grid)

    per_joint = []
    for joint in joints:
        if joint not in cond_r["x"].columns or joint not in opti_r["x"].columns:
            continue
        dx = cond_r["x"][joint] - opti_r["x"][joint]
        dy = cond_r["y"][joint] - opti_r["y"][joint]
        dz = cond_r["z"][joint] - opti_r["z"][joint]
        per_joint.append(np.sqrt(dx**2 + dy**2 + dz**2))
    if not per_joint:
        return []
    whole_body = pd.concat(per_joint, axis=1).mean(axis=1, skipna=True).dropna()
    return [{"participant_id": participant_id, "condition": condition, "value": float(v)}
            for v in whole_body.values]


def jitter_frames(participant_id, condition, wide, exclude_joints=frozenset()):
    t = wide.index.values
    if len(t) < 3:
        return []
    disp_per_joint = []
    for joint in JOINTS:
        if joint in exclude_joints or joint not in wide["x"].columns:
            continue
        x = wide["x"][joint].values
        y = wide["y"][joint].values
        z = wide["z"][joint].values
        disp_per_joint.append(np.sqrt(np.diff(x) ** 2 + np.diff(y) ** 2 + np.diff(z) ** 2))
    if not disp_per_joint:
        return []
    whole = np.nanmean(np.vstack(disp_per_joint), axis=0)
    valid = np.isfinite(whole)
    return [{"participant_id": participant_id, "condition": condition, "value": float(v)}
            for v in whole[valid]]


def cluster_bootstrap(df: pd.DataFrame, n_boot: int = 3000, seed: int = 0):
    """Participant-level (not frame-level) bootstrap CI for the MetaQuest-minus-HYTRACK
    frame-pooled mean difference. Doesn't rely on the mixed model's normal-random-effects
    assumption, so it's a useful independent check when statsmodels flags a convergence
    warning on the random-intercept variance -- if this CI agrees with the mixed model's,
    the p-value can be trusted despite the warning; if it disagrees (includes 0 when the
    mixed model didn't, or vice versa), the mixed model's result is suspect."""
    rng = np.random.default_rng(seed)
    df = df[df.condition.isin(["HYTRACK", "MetaQuest"])]
    participants = df.participant_id.unique()
    groups = {
        p: {c: df[(df.participant_id == p) & (df.condition == c)].value.values
            for c in ["HYTRACK", "MetaQuest"]}
        for p in participants
    }
    diffs = np.empty(n_boot)
    for b in range(n_boot):
        sample = rng.choice(participants, size=len(participants), replace=True)
        h_vals = np.concatenate([groups[p]["HYTRACK"] for p in sample if groups[p]["HYTRACK"].size])
        m_vals = np.concatenate([groups[p]["MetaQuest"] for p in sample if groups[p]["MetaQuest"].size])
        diffs[b] = m_vals.mean() - h_vals.mean()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return float(lo), float(hi), float(diffs.mean())


def run_frame_level_bootstrap(df: pd.DataFrame, label: str):
    df = df[df.condition.isin(["HYTRACK", "MetaQuest"])].copy()

    n_frames = len(df)
    n_participants = df.participant_id.nunique()
    hytrack_mean = df[df.condition == "HYTRACK"].value.mean()
    metaquest_mean = df[df.condition == "MetaQuest"].value.mean()

    boot_lo, boot_hi, boot_mean = cluster_bootstrap(df, seed=0)
    significant = not (boot_lo <= 0 <= boot_hi)

    print(f"\n=== Frame-level cluster bootstrap -- {label} ===")
    print(f"  n_frames={n_frames}  n_participants={n_participants}")
    print(f"  HYTRACK frame mean={hytrack_mean:.4f}   MetaQuest frame mean={metaquest_mean:.4f}")
    print(f"  diff (MetaQuest - HYTRACK) = {boot_mean:.5f}   95% CI = [{boot_lo:.5f}, {boot_hi:.5f}]")
    print(f"  -> {'real difference (CI excludes 0)' if significant else 'no reliable difference (CI includes 0)'}")

    return {
        "metric": label, "n_frames": n_frames, "n_participants": n_participants,
        "hytrack_frame_mean": hytrack_mean, "metaquest_frame_mean": metaquest_mean,
        "bootstrap_diff": boot_mean, "bootstrap_ci_lo": boot_lo, "bootstrap_ci_hi": boot_hi,
        "significant": significant,
    }


def main():
    joints, joints_opti, events, events_opti, latency = load_all()

    cand = candidate_windows(events)
    cand_opti = candidate_windows(events_opti)
    best = select_best_windows(cand)
    best_opti = select_best_windows(cand_opti)
    opti_by_participant = {r.participant_id: r for _, r in best_opti.iterrows()}

    mpjpe_frame_rows, mpjpe_legs_frame_rows, jitter_frame_rows, jitter_legs_frame_rows = [], [], [], []

    for _, w in best.iterrows():
        sub = extract_trial_long(joints, w)
        wide = hip_relative_wide(sub)
        if wide is None:
            continue

        jitter_frame_rows.extend(
            jitter_frames(w.participant_id, w.condition, wide, JITTER_RIG_LOCKED_JOINTS))
        jitter_legs_frame_rows.extend(
            jitter_frames(w.participant_id, w.condition, wide,
                           exclude_joints=set(JOINTS) - LEG_JOINTS))

        wo = opti_by_participant.get(w.participant_id)
        if wo is None:
            continue

        sub_opti = extract_trial_long(joints_opti, wo)
        wide_opti = hip_relative_wide(sub_opti)
        if wide_opti is None:
            continue

        ref_t, ref_y = raw_hip_y(sub_opti).index.values, raw_hip_y(sub_opti).values
        tgt_t, tgt_y = raw_hip_y(sub).index.values, raw_hip_y(sub).values
        if len(ref_t) < 10 or len(tgt_t) < 10:
            continue
        lag_s, _ = best_lag_seconds(ref_t, ref_y, tgt_t, tgt_y)

        wide_shifted = wide.copy()
        wide_shifted.index = wide_shifted.index + lag_s

        mpjpe_frame_rows.extend(mpjpe_frames(w.participant_id, w.condition, wide_shifted, wide_opti))
        mpjpe_legs_frame_rows.extend(
            mpjpe_frames(w.participant_id, w.condition, wide_shifted, wide_opti, joints=LEG_JOINTS))

    results = []
    results.append(run_frame_level_bootstrap(pd.DataFrame(mpjpe_frame_rows), "MPJPE, whole-body (m)"))
    results.append(run_frame_level_bootstrap(pd.DataFrame(mpjpe_legs_frame_rows), "MPJPE, legs (m)"))
    results.append(run_frame_level_bootstrap(pd.DataFrame(jitter_frame_rows), "Jitter, limb joints (m)"))
    results.append(run_frame_level_bootstrap(pd.DataFrame(jitter_legs_frame_rows), "Jitter, legs (m)"))

    out = pd.DataFrame(results)
    out.to_csv(OUT_DIR / "frame_bootstrap_summary.csv", index=False)
    print(f"\nWrote {OUT_DIR / 'frame_bootstrap_summary.csv'}")


if __name__ == "__main__":
    main()
