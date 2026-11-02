"""
Paired HYTRACK-vs-MetaQuest statistical comparison + power/sensitivity analysis,
run on top of analyze_study_data.py's outputs (StudyData/analysis/*.csv).

For each metric (whole-body MPJPE, whole-body jitter):
  1. Collapse per-joint rows to one whole-body number per participant per condition
     (mean across joints).
  2. Pivot to paired participant rows (HYTRACK, MetaQuest), keep only participants
     with both.
  3. Shapiro-Wilk on the paired differences -> pick paired t-test vs Wilcoxon.
  4. Report both tests, Cohen's dz, achieved power at the actual N, and the
     minimum effect size that N could detect at power=0.80 (sensitivity) --
     this is the number for the G*Power write-up.
Also runs the same pipeline per-joint (13 joints) with Holm-Bonferroni correction,
as a secondary/exploratory breakdown.

Run with:  conda run -n thesis-eval python stats_analysis.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = ROOT / "StudyData" / "analysis"
ALPHA = 0.05
TARGET_POWER = 0.80

# Jitter only: in both HYTRACK's and MetaQuest's rigs, head+shoulders move almost
# rigidly with the hip (near-zero frame-to-frame displacement relative to the hip
# midpoint: ~0.002 m vs OptiTrack's genuinely-sensed ~0.02 m for the same joints --
# a 10x gap, same pattern for both consumer systems). That's a rig-construction
# artifact, not real smoothness, same logic as excluding hips (~0.0004-0.005 m,
# smallest of all joints by 1-2 orders of magnitude). Excluded from whole-body
# JITTER only -- MPJPE (a static offset, not a frame-to-frame delta) isn't subject
# to this artifact and keeps all 13 joints.
JITTER_RIG_LOCKED_JOINTS = {"left_hip", "right_hip", "head", "left_shoulder", "right_shoulder"}


# --------------------------------------------------------------------------- #
# Power / sensitivity (paired t-test, two-tailed, via noncentral t)
# --------------------------------------------------------------------------- #

def paired_power(dz: float, n: int, alpha: float = ALPHA) -> float:
    """Achieved power of a paired t-test given Cohen's dz and sample size n."""
    df = n - 1
    t_crit = stats.t.ppf(1 - alpha / 2, df)
    ncp = dz * np.sqrt(n)
    lower_tail = stats.nct.cdf(-t_crit, df, ncp)
    lower_tail = 0.0 if not np.isfinite(lower_tail) else lower_tail  # underflows to NaN, not 0, for large ncp
    power = stats.nct.sf(t_crit, df, ncp) + lower_tail
    return float(np.clip(power, 0.0, 1.0))


def min_detectable_dz(n: int, alpha: float = ALPHA, target_power: float = TARGET_POWER) -> float:
    """Smallest |dz| this N can detect at target_power (sensitivity analysis)."""
    f = lambda dz: paired_power(dz, n, alpha) - target_power
    return float(brentq(f, 1e-4, 2.0))


# --------------------------------------------------------------------------- #
# Core paired analysis
# --------------------------------------------------------------------------- #

def paired_test(hytrack: np.ndarray, metaquest: np.ndarray) -> dict:
    diff = hytrack - metaquest
    n = len(diff)

    shapiro_stat, shapiro_p = stats.shapiro(diff)
    normal = shapiro_p > 0.05

    t_stat, t_p = stats.ttest_rel(hytrack, metaquest)
    try:
        w_stat, w_p = stats.wilcoxon(hytrack, metaquest)
    except ValueError:
        w_stat, w_p = np.nan, np.nan

    dz = float(diff.mean() / diff.std(ddof=1)) if diff.std(ddof=1) > 0 else np.nan
    power_achieved = paired_power(dz, n) if np.isfinite(dz) else np.nan
    sens_dz = min_detectable_dz(n)

    return {
        "n": n,
        "hytrack_mean": float(hytrack.mean()), "hytrack_std": float(hytrack.std(ddof=1)),
        "metaquest_mean": float(metaquest.mean()), "metaquest_std": float(metaquest.std(ddof=1)),
        "diff_mean": float(diff.mean()), "diff_std": float(diff.std(ddof=1)),
        "shapiro_p": float(shapiro_p), "diff_normal": normal,
        "recommended_test": "paired t-test" if normal else "Wilcoxon signed-rank",
        "t_stat": float(t_stat), "t_p": float(t_p),
        "wilcoxon_stat": float(w_stat) if np.isfinite(w_stat) else np.nan,
        "wilcoxon_p": float(w_p) if np.isfinite(w_p) else np.nan,
        "cohens_dz": dz,
        "power_achieved_at_n": power_achieved,
        "min_detectable_dz_at_power80": sens_dz,
    }


def whole_body(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """Per-joint metric table -> one whole-body value per participant per condition
    (mean across joints)."""
    return (
        df.groupby(["participant_id", "condition"])[value_col]
        .mean()
        .reset_index()
    )


def run_metric(name: str, df: pd.DataFrame, value_col: str) -> tuple[dict, pd.DataFrame]:
    wb = whole_body(df, value_col)
    wide = wb.pivot(index="participant_id", columns="condition", values=value_col)
    wide = wide.dropna(subset=["HYTRACK", "MetaQuest"])
    result = paired_test(wide["HYTRACK"].values, wide["MetaQuest"].values)
    result["metric"] = name
    result["excluded_participants"] = sorted(
        set(wb.participant_id.unique()) - set(wide.index)
    )
    return result, wide


def run_per_joint(name: str, df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    rows = []
    for joint, g in df.groupby("joint"):
        wide = g.pivot(index="participant_id", columns="condition", values=value_col)
        wide = wide.dropna(subset=["HYTRACK", "MetaQuest"])
        if len(wide) < 3:
            continue
        r = paired_test(wide["HYTRACK"].values, wide["MetaQuest"].values)
        r["metric"] = name
        r["joint"] = joint
        rows.append(r)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Holm-Bonferroni across joints, using whichever test each row's normality check recommends
    out["p_for_correction"] = np.where(out.diff_normal, out.t_p, out.wilcoxon_p)
    order = np.argsort(out["p_for_correction"].values)
    m = len(out)
    holm_p = np.empty(m)
    running_max = 0.0
    sorted_p = out["p_for_correction"].values[order]
    for i, p in enumerate(sorted_p):
        adj = (m - i) * p
        running_max = max(running_max, adj)
        holm_p[order[i]] = min(running_max, 1.0)
    out["holm_adjusted_p"] = holm_p
    out["significant_after_holm"] = out["holm_adjusted_p"] < ALPHA
    return out


def print_summary(result: dict):
    print(f"\n=== {result['metric']}: HYTRACK vs MetaQuest (paired, n={result['n']}) ===")
    if result["excluded_participants"]:
        print(f"  excluded (missing one condition): {result['excluded_participants']}")
    print(f"  HYTRACK   : mean={result['hytrack_mean']:.4f}  sd={result['hytrack_std']:.4f}")
    print(f"  MetaQuest : mean={result['metaquest_mean']:.4f}  sd={result['metaquest_std']:.4f}")
    print(f"  diff (H-M): mean={result['diff_mean']:.4f}  sd={result['diff_std']:.4f}")
    print(f"  Shapiro-Wilk on diff: p={result['shapiro_p']:.4f} "
          f"({'normal' if result['diff_normal'] else 'NOT normal'}) "
          f"-> recommended test: {result['recommended_test']}")
    print(f"  paired t-test : t={result['t_stat']:.3f}, p={result['t_p']:.4f}")
    print(f"  Wilcoxon      : W={result['wilcoxon_stat']:.1f}, p={result['wilcoxon_p']:.4f}")
    print(f"  Cohen's dz    : {result['cohens_dz']:.3f}")
    print(f"  achieved power at n={result['n']}, alpha=0.05 : {result['power_achieved_at_n']:.3f}")
    print(f"  min |dz| this n can detect at power=0.80       : {result['min_detectable_dz_at_power80']:.3f}")


def main():
    mpjpe = pd.read_csv(ANALYSIS_DIR / "mpjpe_by_participant_joint.csv")
    jitter = pd.read_csv(ANALYSIS_DIR / "jitter_by_participant_joint.csv")
    continuity = pd.read_csv(ANALYSIS_DIR / "tracking_continuity_by_participant.csv")

    summary_rows = []

    r_mpjpe, _ = run_metric("MPJPE (whole-body, m)", mpjpe, "mpjpe_m")
    print_summary(r_mpjpe)
    summary_rows.append(r_mpjpe)

    jitter_wb = jitter[~jitter.joint.isin(JITTER_RIG_LOCKED_JOINTS)]
    r_jitter, _ = run_metric("Jitter (whole-body, limb joints only, RMS m)", jitter_wb, "jitter_rms_m")
    print_summary(r_jitter)
    summary_rows.append(r_jitter)

    r_dropout, _ = run_metric("Tracking dropout (%, frame gaps > 1.5x expected)",
                               continuity, "pct_gaps_over_1_5x_expected")
    print_summary(r_dropout)
    summary_rows.append(r_dropout)

    summary_df = pd.DataFrame(summary_rows).drop(columns=["excluded_participants"])
    summary_df.to_csv(ANALYSIS_DIR / "paired_test_wholebody_summary.csv", index=False)

    mpjpe_joint = run_per_joint("MPJPE (m)", mpjpe, "mpjpe_m")
    jitter_joint = run_per_joint("Jitter RMS (m)", jitter, "jitter_rms_m")
    per_joint = pd.concat([mpjpe_joint, jitter_joint], ignore_index=True)
    per_joint.to_csv(ANALYSIS_DIR / "paired_test_per_joint.csv", index=False)

    print(f"\n=== Per-joint breakdown (Holm-Bonferroni corrected) ===")
    print(per_joint[["metric", "joint", "n", "t_p", "wilcoxon_p",
                      "holm_adjusted_p", "significant_after_holm"]]
          .to_string(index=False))

    print(f"\nWrote:")
    print(f"  {ANALYSIS_DIR / 'paired_test_wholebody_summary.csv'}")
    print(f"  {ANALYSIS_DIR / 'paired_test_per_joint.csv'}")


if __name__ == "__main__":
    main()
