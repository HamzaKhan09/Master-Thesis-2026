"""
Processes StudyData/*.csv (20 participants, HYTRACK / MetaQuest / OptiTrack) into
tidy metrics tables for the thesis report: root-relative MPJPE + per-axis error
(vs OptiTrack ground truth), frame-to-frame jitter, latency, and tracking
continuity. Does not produce plots — see plot_study_data.py for figures.

Run with:  conda run -n thesis-eval python analyze_study_data.py

Data-quality context this script works around (see memory project_study_data_analysis
for the full writeup):
- OptiTrack ground truth only exists for 16/20 participants; accuracy metrics are
  computed only for those, everything else runs on all 20.
- The `confidence` column in the joint CSVs is a constant 1.0 (not a real per-frame
  signal), so tracking continuity is derived from timestamp gaps instead.
- trial_events.csv / OptiTrack_trial_events.csv contain multiple recording sessions
  for several participants (retries after crashes) plus an orphaned TRIAL_START with
  no TRIAL_END. Trial windows are resolved by pairing each TRIAL_START with the next
  TRIAL_END in the same (session_id, condition) group, then keeping the
  longest-duration candidate per (participant_id, condition) as the presumed-complete
  run. Every candidate window is written to trial_window_audit.csv so this heuristic
  can be checked, not just trusted.
- latency_log.csv has no participant_id column, but its session_id values are a full
  subset of joint_positions.csv's, so participant_id/condition are recovered by
  joining on session_id + falling inside the resolved trial window.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
from scipy import signal as sp_signal

ROOT = Path(__file__).resolve().parent.parent
STUDY_DATA = ROOT / "StudyData"
OUT_DIR = STUDY_DATA / "analysis"
OUT_DIR.mkdir(exist_ok=True)

JOINTS = [
    "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "head",
]
HIP_L, HIP_R = "left_hip", "right_hip"
AXES = ["x", "y", "z"]

LOG_HZ = 6.0
MIN_TRIAL_S = 5.0          # discard candidate windows shorter than this (aborted attempts)
MAX_LAG_S = 5.0            # max temporal-alignment correction searched vs OptiTrack
XCORR_DT = 0.1             # grid spacing used only for lag search
RESAMPLE_DT = 1.0 / LOG_HZ # grid spacing used for the actual MPJPE comparison
GAP_DROPOUT_FACTOR = 1.5   # a gap > this * expected_dt counts as a dropped sample


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

def load_all():
    joints = pd.read_csv(STUDY_DATA / "joint_positions.csv")
    joints_opti = pd.read_csv(STUDY_DATA / "Optitrack_joint_positions.csv")
    events = pd.read_csv(STUDY_DATA / "trial_events.csv")
    events_opti = pd.read_csv(STUDY_DATA / "OptiTrack_trial_events.csv")
    latency = pd.read_csv(STUDY_DATA / "latency_log.csv")
    return joints, joints_opti, events, events_opti, latency


# --------------------------------------------------------------------------- #
# Trial window resolution
# --------------------------------------------------------------------------- #

def candidate_windows(events: pd.DataFrame) -> pd.DataFrame:
    """Pair each TRIAL_START with the next TRIAL_END in the same
    (session_id, condition) group, ordered by time. One row per candidate window."""
    rows = []
    for (session_id, condition), g in events.groupby(["session_id", "condition"]):
        g = g.sort_values("timestamp_ms")
        starts = g[g.event_type == "TRIAL_START"]
        ends = g[g.event_type == "TRIAL_END"]
        for _, srow in starts.iterrows():
            cand_ends = ends[ends.timestamp_ms > srow.timestamp_ms]
            if cand_ends.empty:
                continue
            erow = cand_ends.iloc[0]
            rows.append({
                "participant_id": srow.participant_id,
                "condition": condition,
                "session_id": session_id,
                "trial_id": srow.trial_id,
                "start_ms": srow.timestamp_ms,
                "end_ms": erow.timestamp_ms,
                "duration_s": (erow.timestamp_ms - srow.timestamp_ms) / 1000.0,
            })
    return pd.DataFrame(rows)


def select_best_windows(windows: pd.DataFrame) -> pd.DataFrame:
    """Longest valid (>= MIN_TRIAL_S) candidate window per (participant_id, condition)."""
    valid = windows[windows.duration_s >= MIN_TRIAL_S].copy()
    valid = valid.sort_values("duration_s", ascending=False)
    best = valid.drop_duplicates(subset=["participant_id", "condition"], keep="first")
    return best.sort_values(["participant_id", "condition"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Per-trial joint data
# --------------------------------------------------------------------------- #

def extract_trial_long(joints_df: pd.DataFrame, w: pd.Series) -> pd.DataFrame:
    mask = (
        (joints_df.participant_id == w.participant_id)
        & (joints_df.condition == w.condition)
        & (joints_df.session_id == w.session_id)
        & (joints_df.timestamp_ms >= w.start_ms)
        & (joints_df.timestamp_ms <= w.end_ms)
    )
    sub = joints_df.loc[mask].copy()
    sub["t_rel"] = (sub.timestamp_ms - w.start_ms) / 1000.0
    return sub


def hip_relative_wide(sub_long: pd.DataFrame) -> pd.DataFrame | None:
    """Long (t_rel, joint, x, y, z) -> wide, columns (axis, joint), positions expressed
    relative to the per-frame hip midpoint (root-relative MPJPE convention -- sidesteps
    absolute Unity world-space offsets between separately-calibrated sessions)."""
    wide = sub_long.pivot_table(index="t_rel", columns="joint", values=AXES)
    if HIP_L not in wide["x"].columns or HIP_R not in wide["x"].columns:
        return None
    for axis in AXES:
        hip_mid = (wide[axis][HIP_L] + wide[axis][HIP_R]) / 2.0
        wide[axis] = wide[axis].sub(hip_mid, axis=0)
    return wide


def raw_hip_y(sub_long: pd.DataFrame) -> pd.Series:
    """Absolute (pre-centering) hip-midpoint Y, used only as the alignment reference
    signal -- gravity-driven motion (squat/jump) is the most temporally distinctive."""
    p = sub_long.pivot_table(index="t_rel", columns="joint", values="y")
    return ((p[HIP_L] + p[HIP_R]) / 2.0).dropna()


# --------------------------------------------------------------------------- #
# Temporal alignment (condition vs OptiTrack)
# --------------------------------------------------------------------------- #

def _zscore_resample(t: np.ndarray, y: np.ndarray, dt: float, tmax: float):
    grid = np.arange(0, tmax, dt)
    v = np.interp(grid, t, y, left=np.nan, right=np.nan)
    valid = ~np.isnan(v)
    if valid.sum() < 10:
        return grid, np.zeros_like(grid)
    mu, sd = np.nanmean(v), np.nanstd(v)
    sd = sd if sd > 1e-6 else 1.0
    z = (v - mu) / sd
    z[~valid] = 0.0
    return grid, z


def best_lag_seconds(t_ref: np.ndarray, y_ref: np.ndarray,
                      t_tgt: np.ndarray, y_tgt: np.ndarray) -> tuple[float, float]:
    """Returns (lag_s, peak_corr). Add lag_s to t_tgt to align it onto t_ref's timeline."""
    tmax = max(np.max(t_ref), np.max(t_tgt))
    _, z_ref = _zscore_resample(t_ref, y_ref, XCORR_DT, tmax)
    _, z_tgt = _zscore_resample(t_tgt, y_tgt, XCORR_DT, tmax)
    max_lag_samples = int(round(MAX_LAG_S / XCORR_DT))
    corr = sp_signal.correlate(z_ref, z_tgt, mode="full")
    lags = sp_signal.correlation_lags(len(z_ref), len(z_tgt), mode="full")
    mask = np.abs(lags) <= max_lag_samples
    corr, lags = corr[mask], lags[mask]
    best_idx = int(np.argmax(corr))
    peak_corr = corr[best_idx] / max(len(z_ref), 1)
    return lags[best_idx] * XCORR_DT, float(peak_corr)


# --------------------------------------------------------------------------- #
# Resampling + error computation
# --------------------------------------------------------------------------- #

def resample_wide(wide: pd.DataFrame, grid: np.ndarray) -> pd.DataFrame:
    out = {}
    for col in wide.columns:
        s = wide[col].dropna()
        if len(s) < 2:
            out[col] = np.full_like(grid, np.nan, dtype=float)
            continue
        out[col] = np.interp(grid, s.index.values, s.values, left=np.nan, right=np.nan)
    return pd.DataFrame(out, index=grid, columns=wide.columns)


def compute_mpjpe_rows(participant_id, condition, cond_wide_shifted, opti_wide, lag_s, peak_corr):
    t0 = max(cond_wide_shifted.index.min(), opti_wide.index.min())
    t1 = min(cond_wide_shifted.index.max(), opti_wide.index.max())
    if t1 - t0 < MIN_TRIAL_S:
        return []
    grid = np.arange(t0, t1, RESAMPLE_DT)
    cond_r = resample_wide(cond_wide_shifted, grid)
    opti_r = resample_wide(opti_wide, grid)

    rows = []
    for joint in JOINTS:
        if joint not in cond_r["x"].columns or joint not in opti_r["x"].columns:
            continue
        dx = cond_r["x"][joint] - opti_r["x"][joint]
        dy = cond_r["y"][joint] - opti_r["y"][joint]
        dz = cond_r["z"][joint] - opti_r["z"][joint]
        euclid = np.sqrt(dx**2 + dy**2 + dz**2)
        n = euclid.notna().sum()
        if n == 0:
            continue
        rows.append({
            "participant_id": participant_id,
            "condition": condition,
            "joint": joint,
            "n_frames": int(n),
            "mpjpe_m": float(euclid.mean(skipna=True)),
            "err_x_abs_mean_m": float(dx.abs().mean(skipna=True)),
            "err_y_abs_mean_m": float(dy.abs().mean(skipna=True)),
            "err_z_abs_mean_m": float(dz.abs().mean(skipna=True)),
            "err_x_signed_mean_m": float(dx.mean(skipna=True)),
            "err_y_signed_mean_m": float(dy.mean(skipna=True)),
            "err_z_signed_mean_m": float(dz.mean(skipna=True)),
            "lag_s": lag_s,
            "align_peak_corr": peak_corr,
        })
    return rows


def compute_jitter_rows(participant_id, condition, wide):
    rows = []
    t = wide.index.values
    if len(t) < 3:
        return rows
    dt = np.diff(t)
    for joint in JOINTS:
        if joint not in wide["x"].columns:
            continue
        x, y, z = wide["x"][joint].values, wide["y"][joint].values, wide["z"][joint].values
        disp = np.sqrt(np.diff(x)**2 + np.diff(y)**2 + np.diff(z)**2)
        valid = np.isfinite(disp)
        if valid.sum() < 3:
            continue
        rows.append({
            "participant_id": participant_id,
            "condition": condition,
            "joint": joint,
            "n_frames": int(valid.sum()),
            "jitter_rms_m": float(np.sqrt(np.mean(disp[valid] ** 2))),
            "mean_frame_dt_s": float(np.mean(dt)),
        })
    return rows


def compute_continuity_row(participant_id, condition, sub_long, duration_s):
    ts = np.sort(sub_long.timestamp_ms.unique())
    if len(ts) < 2:
        return None
    gaps_s = np.diff(ts) / 1000.0
    expected_dt = 1.0 / LOG_HZ
    dropout_frac = float(np.mean(gaps_s > GAP_DROPOUT_FACTOR * expected_dt))
    return {
        "participant_id": participant_id,
        "condition": condition,
        "n_samples": len(ts),
        "duration_s": duration_s,
        "achieved_hz": len(ts) / duration_s if duration_s > 0 else np.nan,
        "pct_gaps_over_1_5x_expected": dropout_frac * 100.0,
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    joints, joints_opti, events, events_opti, latency = load_all()

    cand = candidate_windows(events)
    cand_opti = candidate_windows(events_opti)
    best = select_best_windows(cand)
    best_opti = select_best_windows(cand_opti)

    audit = pd.concat([
        cand.assign(selected=False, ground_truth=False),
        cand_opti.assign(selected=False, ground_truth=True),
    ], ignore_index=True)
    sel_key = set(zip(best.participant_id, best.condition, best.session_id, best.trial_id))
    sel_key_opti = set(zip(best_opti.participant_id, best_opti.condition,
                            best_opti.session_id, best_opti.trial_id))
    audit["selected"] = audit.apply(
        lambda r: (r.participant_id, r.condition, r.session_id, r.trial_id) in sel_key
        or (r.participant_id, r.condition, r.session_id, r.trial_id) in sel_key_opti,
        axis=1,
    )
    audit.sort_values(["participant_id", "condition", "start_ms"]).to_csv(
        OUT_DIR / "trial_window_audit.csv", index=False)

    # Best OptiTrack window per participant (condition is always "OptiTrack")
    opti_by_participant = {r.participant_id: r for _, r in best_opti.iterrows()}

    mpjpe_rows, jitter_rows, continuity_rows = [], [], []

    for _, w in best.iterrows():
        sub = extract_trial_long(joints, w)
        wide = hip_relative_wide(sub)
        if wide is None:
            continue

        jitter_rows.extend(compute_jitter_rows(w.participant_id, w.condition, wide))
        cont = compute_continuity_row(w.participant_id, w.condition, sub, w.duration_s)
        if cont:
            continuity_rows.append(cont)

        wo = opti_by_participant.get(w.participant_id)
        if wo is None:
            continue  # no ground truth for this participant -- skip accuracy only

        sub_opti = extract_trial_long(joints_opti, wo)
        wide_opti = hip_relative_wide(sub_opti)
        if wide_opti is None:
            continue

        ref_t, ref_y = raw_hip_y(sub_opti).index.values, raw_hip_y(sub_opti).values
        tgt_t, tgt_y = raw_hip_y(sub).index.values, raw_hip_y(sub).values
        if len(ref_t) < 10 or len(tgt_t) < 10:
            continue
        lag_s, peak_corr = best_lag_seconds(ref_t, ref_y, tgt_t, tgt_y)

        wide_shifted = wide.copy()
        wide_shifted.index = wide_shifted.index + lag_s

        mpjpe_rows.extend(compute_mpjpe_rows(
            w.participant_id, w.condition, wide_shifted, wide_opti, lag_s, peak_corr))

    # Also record OptiTrack's own jitter/continuity (ground-truth sanity check)
    for _, wo in best_opti.iterrows():
        sub = extract_trial_long(joints_opti, wo)
        wide = hip_relative_wide(sub)
        if wide is None:
            continue
        jitter_rows.extend(compute_jitter_rows(wo.participant_id, "OptiTrack", wide))
        cont = compute_continuity_row(wo.participant_id, "OptiTrack", sub, wo.duration_s)
        if cont:
            continuity_rows.append(cont)

    mpjpe_df = pd.DataFrame(mpjpe_rows)
    jitter_df = pd.DataFrame(jitter_rows)
    continuity_df = pd.DataFrame(continuity_rows)

    mpjpe_df.to_csv(OUT_DIR / "mpjpe_by_participant_joint.csv", index=False)
    jitter_df.to_csv(OUT_DIR / "jitter_by_participant_joint.csv", index=False)
    continuity_df.to_csv(OUT_DIR / "tracking_continuity_by_participant.csv", index=False)

    if not mpjpe_df.empty:
        mpjpe_summary = (
            mpjpe_df.groupby(["condition", "joint"])
            .agg(n_participants=("participant_id", "nunique"),
                 mpjpe_mean_m=("mpjpe_m", "mean"), mpjpe_std_m=("mpjpe_m", "std"),
                 err_x_abs_mean_m=("err_x_abs_mean_m", "mean"),
                 err_y_abs_mean_m=("err_y_abs_mean_m", "mean"),
                 err_z_abs_mean_m=("err_z_abs_mean_m", "mean"))
            .reset_index()
        )
        mpjpe_summary.to_csv(OUT_DIR / "mpjpe_summary_by_condition_joint.csv", index=False)

    if not jitter_df.empty:
        jitter_summary = (
            jitter_df.groupby(["condition", "joint"])
            .agg(n_participants=("participant_id", "nunique"),
                 jitter_rms_mean_m=("jitter_rms_m", "mean"),
                 jitter_rms_std_m=("jitter_rms_m", "std"))
            .reset_index()
        )
        jitter_summary.to_csv(OUT_DIR / "jitter_summary_by_condition_joint.csv", index=False)

    # ---- Latency: recover participant_id/condition by joining on session_id + window ---- #
    all_windows = pd.concat([best, best_opti], ignore_index=True)
    latency_rows = []
    for _, w in all_windows.iterrows():
        mask = (
            (latency.session_id == w.session_id)
            & (latency.condition == w.condition)
            & (latency.timestamp_ms >= w.start_ms)
            & (latency.timestamp_ms <= w.end_ms)
        )
        sub = latency.loc[mask].dropna(subset=["delta_ms"])
        if sub.empty:
            continue
        latency_rows.append({
            "participant_id": w.participant_id,
            "condition": w.condition,
            "n_samples": len(sub),
            "latency_mean_ms": float(sub.delta_ms.mean()),
            "latency_median_ms": float(sub.delta_ms.median()),
            "latency_p95_ms": float(sub.delta_ms.quantile(0.95)),
        })
    latency_df = pd.DataFrame(latency_rows)
    latency_df.to_csv(OUT_DIR / "latency_by_participant.csv", index=False)

    # ---- Console summary ---- #
    print(f"Resolved trial windows: {len(best)} (HYTRACK/MetaQuest) + {len(best_opti)} (OptiTrack)")
    print(f"  -> full audit written to {OUT_DIR / 'trial_window_audit.csv'}")
    print(f"Participants with OptiTrack ground truth: {sorted(opti_by_participant.keys())}")
    missing = sorted(set(best.participant_id.unique()) - set(opti_by_participant.keys()))
    print(f"Participants WITHOUT ground truth (accuracy skipped): {missing}")
    if not mpjpe_df.empty:
        print(f"MPJPE rows: {len(mpjpe_df)} (participant x condition x joint)")
        print(mpjpe_df.groupby("condition").mpjpe_m.agg(["mean", "std", "count"]))
    print(f"Jitter rows: {len(jitter_df)}, continuity rows: {len(continuity_df)}, "
          f"latency rows: {len(latency_df)}")
    print(f"All outputs written to {OUT_DIR}")


if __name__ == "__main__":
    main()
