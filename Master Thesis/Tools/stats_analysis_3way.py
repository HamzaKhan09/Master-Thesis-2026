"""
Three-condition (HYTRACK / MetaQuest / OptiTrack) within-subjects comparison.

WHY THIS REPLACES THE PAIRED HYTRACK-vs-MetaQuest TESTS IN stats_analysis.py:
OptiTrack was not a simultaneous ground-truth capture -- it was a third
counterbalanced condition, recorded in its own block (0 of 38 condition trials
overlap with their OptiTrack trial in wall-clock time; see the project memory
note project_mpjpe_invalid_no_simultaneous_capture). Every participant was
therefore measured under all three conditions, which makes this a 3-level
repeated-measures design, not a 2-arm comparison with a reference signal.

Testing only HYTRACK-vs-MetaQuest ignores a third measured arm; running three
uncorrected pairwise tests inflates the false-positive rate. The correct
structure is an omnibus test across all three conditions, and pairwise post-hoc
tests only where the omnibus is significant, with multiplicity control.

METRICS COVERED: only the ones computed *within* a single condition's own data
stream -- whole-body limb jitter, legs-only jitter, and tracking dropout. These
never compare across sessions, so the no-simultaneous-capture problem does not
touch them. MPJPE/accuracy is deliberately absent: it requires frame
correspondence between a condition and OptiTrack that does not exist.

TESTS:
  - Omnibus: Friedman test (non-parametric repeated measures). Chosen over
    repeated-measures ANOVA because dropout is heavily zero-inflated and
    strongly non-normal (Shapiro p < 0.0001 in the earlier 2-arm analysis);
    Friedman makes no distributional assumption and is the conservative choice
    at n=19. Per-condition Shapiro-Wilk is reported alongside so the choice can
    be defended in the write-up rather than asserted.
  - Omnibus effect size: Kendall's W = chi2 / (n * (k-1)), range 0-1
    (~0.1 small, ~0.3 moderate, ~0.5 large).
  - Post-hoc: pairwise Wilcoxon signed-rank across all 3 pairs, Holm-Bonferroni
    corrected within each metric (same correction already used for the 13-joint
    breakdown in stats_analysis.py).
  - Post-hoc effect size: matched-pairs rank-biserial correlation
    r = (T+ - T-) / (T+ + T-), the standard companion to Wilcoxon.

Produces:
  StudyData/analysis/friedman_3way_summary.csv   (one row per metric)
  StudyData/analysis/friedman_3way_posthoc.csv   (one row per metric x pair)

Run with:  conda run -n thesis-eval python stats_analysis_3way.py
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from scipy import stats

from stats_analysis import ANALYSIS_DIR, ALPHA, JITTER_RIG_LOCKED_JOINTS
from stats_analysis_legs import LEG_JOINTS

CONDITIONS = ["HYTRACK", "MetaQuest", "OptiTrack"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def wide_all_conditions(df: pd.DataFrame, value_col: str,
                         keep_joints: set | None = None,
                         drop_joints: set | None = None) -> pd.DataFrame:
    """Per-joint (or per-participant) metric table -> one value per participant per
    condition, keeping only participants measured under all three conditions."""
    if keep_joints is not None:
        df = df[df.joint.isin(keep_joints)]
    if drop_joints is not None:
        df = df[~df.joint.isin(drop_joints)]
    collapsed = df.groupby(["participant_id", "condition"])[value_col].mean().reset_index()
    wide = collapsed.pivot(index="participant_id", columns="condition", values=value_col)
    missing = [c for c in CONDITIONS if c not in wide.columns]
    if missing:
        raise ValueError(f"missing condition(s) {missing} for {value_col}")
    return wide[CONDITIONS].dropna()


def kendalls_w(chi2: float, n: int, k: int) -> float:
    """Friedman effect size. chi2 / (n * (k-1)), bounded 0-1."""
    return float(chi2 / (n * (k - 1)))


def rank_biserial(x: np.ndarray, y: np.ndarray) -> float:
    """Matched-pairs rank-biserial correlation for a Wilcoxon signed-rank test.
    Positive => x tends to exceed y. Zero differences are dropped, per convention."""
    d = np.asarray(x, dtype=float) - np.asarray(y, dtype=float)
    d = d[d != 0]
    if len(d) == 0:
        return np.nan
    ranks = stats.rankdata(np.abs(d))
    t_plus = ranks[d > 0].sum()
    t_minus = ranks[d < 0].sum()
    total = t_plus + t_minus
    return float((t_plus - t_minus) / total) if total > 0 else np.nan


def holm_adjust(pvals: list[float]) -> np.ndarray:
    """Holm-Bonferroni step-down adjustment. NaN p-values pass through as NaN."""
    p = np.asarray(pvals, dtype=float)
    finite = np.isfinite(p)
    adj = np.full(len(p), np.nan)
    idx = np.flatnonzero(finite)
    if idx.size == 0:
        return adj
    order = idx[np.argsort(p[idx])]
    m = idx.size
    running = 0.0
    for i, pos in enumerate(order):
        running = max(running, (m - i) * p[pos])
        adj[pos] = min(running, 1.0)
    return adj


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #

def run_metric(name: str, wide: pd.DataFrame) -> tuple[dict, list[dict]]:
    n, k = len(wide), len(CONDITIONS)

    chi2, p_omnibus = stats.friedmanchisquare(*[wide[c].values for c in CONDITIONS])
    w = kendalls_w(chi2, n, k)

    summary = {
        "metric": name, "n": n, "k_conditions": k,
        "friedman_chi2": float(chi2), "friedman_df": k - 1, "friedman_p": float(p_omnibus),
        "kendalls_w": w,
        "omnibus_significant": bool(p_omnibus < ALPHA),
    }
    for c in CONDITIONS:
        vals = wide[c]
        summary[f"{c.lower()}_mean"] = float(vals.mean())
        summary[f"{c.lower()}_sd"] = float(vals.std(ddof=1))
        # reported as context for the non-parametric choice, not used to switch tests
        summary[f"{c.lower()}_shapiro_p"] = float(stats.shapiro(vals).pvalue)

    posthoc = []
    for a, b in itertools.combinations(CONDITIONS, 2):
        x, y = wide[a].values, wide[b].values
        try:
            stat, p = stats.wilcoxon(x, y)
            stat, p = float(stat), float(p)
        except ValueError:  # all differences zero -> no test possible
            stat, p = np.nan, np.nan
        posthoc.append({
            "metric": name, "pair": f"{a} vs {b}",
            "n": n,
            f"mean_a": float(x.mean()), f"mean_b": float(y.mean()),
            "median_diff": float(np.median(x - y)),
            "wilcoxon_stat": stat, "p_raw": p,
            "rank_biserial_r": rank_biserial(x, y),
        })

    for row, p_adj in zip(posthoc, holm_adjust([r["p_raw"] for r in posthoc])):
        row["p_holm"] = float(p_adj) if np.isfinite(p_adj) else np.nan
        row["significant_after_holm"] = bool(np.isfinite(p_adj) and p_adj < ALPHA)

    return summary, posthoc


def print_metric(summary: dict, posthoc: list[dict]):
    print(f"\n=== {summary['metric']} (n={summary['n']}, all 3 conditions) ===")
    for c in CONDITIONS:
        key = c.lower()
        print(f"  {c:<10}: mean={summary[f'{key}_mean']:.5f}  sd={summary[f'{key}_sd']:.5f}"
              f"   (Shapiro p={summary[f'{key}_shapiro_p']:.4f})")
    print(f"  Friedman: chi2({summary['friedman_df']})={summary['friedman_chi2']:.3f}, "
          f"p={summary['friedman_p']:.5g}, Kendall's W={summary['kendalls_w']:.3f}"
          f"  -> {'SIGNIFICANT' if summary['omnibus_significant'] else 'not significant'}")
    if not summary["omnibus_significant"]:
        print("  (post-hoc pairs shown for completeness; omnibus was not significant, "
              "so these should not be interpreted as findings)")
    print("  post-hoc (Wilcoxon, Holm-corrected):")
    for r in posthoc:
        if np.isnan(r["p_raw"]):
            print(f"    {r['pair']:<26} no test possible (all differences zero)")
            continue
        mark = "*" if r["significant_after_holm"] else " "
        print(f"    {r['pair']:<26} p_raw={r['p_raw']:.5g}  p_holm={r['p_holm']:.5g}{mark}"
              f"   rank-biserial r={r['rank_biserial_r']:+.3f}")


def main():
    jitter = pd.read_csv(ANALYSIS_DIR / "jitter_by_participant_joint.csv")
    continuity = pd.read_csv(ANALYSIS_DIR / "tracking_continuity_by_participant.csv")

    metrics = [
        ("Jitter, limb joints (RMS m)",
         wide_all_conditions(jitter, "jitter_rms_m", drop_joints=JITTER_RIG_LOCKED_JOINTS)),
        ("Jitter, legs only (RMS m)",
         wide_all_conditions(jitter, "jitter_rms_m", keep_joints=LEG_JOINTS)),
        ("Tracking dropout (%)",
         wide_all_conditions(continuity, "pct_gaps_over_1_5x_expected")),
    ]

    summaries, posthocs = [], []
    for name, wide in metrics:
        s, ph = run_metric(name, wide)
        print_metric(s, ph)
        summaries.append(s)
        posthocs.extend(ph)

    out_s = ANALYSIS_DIR / "friedman_3way_summary.csv"
    out_p = ANALYSIS_DIR / "friedman_3way_posthoc.csv"
    pd.DataFrame(summaries).to_csv(out_s, index=False)
    pd.DataFrame(posthocs).to_csv(out_p, index=False)
    print(f"\nWrote {out_s}")
    print(f"Wrote {out_p}")


if __name__ == "__main__":
    main()
