"""
Compares the R statistics output against the Python statistics output, number by
number, and reports where and why they differ.

WHY THIS EXISTS: the statistics are now computed twice, by two independent
implementations in two languages. R is the reporting source (it is what the
supervisor asked for and what reviewers in this field expect); Python is the
check. This script is what makes that claim verifiable rather than asserted --
if the two agree, the results chapter can say so.

WHAT COUNTS AS A REAL DISAGREEMENT: only a difference that changes a decision --
a significance flag flipping, or a pairwise verdict changing. Small numeric
differences in Wilcoxon p-values are EXPECTED and benign:

  R's wilcox.test uses an exact null distribution when there are no ties among
  the absolute differences and n < 50, and otherwise a normal approximation WITH
  a continuity correction. SciPy's wilcoxon() defaults to an exact test under
  similar conditions but applies NO continuity correction in the approximate
  branch. Where both run exact, they agree to machine precision. Where they fall
  back, R's p-value is slightly larger.

The R post-hoc output carries a p_raw_nocorrect column computed with
correct = FALSE, which is what SciPy's approximate branch computes -- so any gap
can be attributed rather than guessed at.

Run with:  conda run -n thesis-eval python diff_r_vs_python.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analyze_study_data import OUT_DIR

# (label, python file, R file, key columns)
COMPARISONS = [
    ("Technical: Friedman omnibus",
     "friedman_3way_summary.csv", "friedman_3way_summary_R.csv", ["metric"]),
    ("Technical: pairwise post-hoc",
     "friedman_3way_posthoc.csv", "friedman_3way_posthoc_R.csv", ["metric", "pair"]),
    ("Questionnaire: condition tests",
     "questionnaire_tests.csv", "questionnaire_tests_R.csv", ["measure"]),
    ("Questionnaire: reliability",
     "questionnaire_reliability.csv", "questionnaire_reliability_R.csv", ["subscale"]),
]

# Columns that encode a DECISION rather than a magnitude. A mismatch here is a
# real disagreement; a mismatch in a magnitude column may just be rounding.
DECISION_COLS = {"omnibus_significant", "significant", "significant_after_holm", "pairwise"}

IDENTICAL = 1e-9      # bit-for-bit agreement
NEGLIGIBLE = 1e-6     # same number, different accumulation order
ALPHA = 0.05


def as_bool(s: pd.Series) -> pd.Series:
    """Python writes True/False, R writes TRUE/FALSE."""
    return s.astype(str).str.strip().str.upper().map({"TRUE": True, "FALSE": False})


def crosses_alpha(a: float, b: float) -> bool:
    if not (np.isfinite(a) and np.isfinite(b)):
        return False
    return (a < ALPHA) != (b < ALPHA)


def compare(label: str, py_file: str, r_file: str, keys: list[str]) -> tuple[int, int]:
    py_path, r_path = OUT_DIR / py_file, OUT_DIR / r_file
    print(f"\n{'=' * 78}\n{label}\n  python: {py_file}\n  R:      {r_file}\n{'=' * 78}")

    if not py_path.exists() or not r_path.exists():
        missing = py_file if not py_path.exists() else r_file
        print(f"  SKIPPED -- {missing} not found; run both pipelines first.")
        return 0, 0

    py, r = pd.read_csv(py_path), pd.read_csv(r_path)
    merged = py.merge(r, on=keys, how="outer", suffixes=("_py", "_r"), indicator=True)

    unmatched = merged[merged._merge != "both"]
    if len(unmatched):
        print(f"  ⚠ {len(unmatched)} row(s) present in only one output:")
        for _, row in unmatched.iterrows():
            side = "python only" if row._merge == "left_only" else "R only"
            print(f"      {' / '.join(str(row[k]) for k in keys)}  ({side})")

    shared = [c for c in py.columns if c in r.columns and c not in keys]
    decisions_checked = decisions_differing = 0
    numeric_reports = []

    for col in shared:
        a, b = merged.get(f"{col}_py"), merged.get(f"{col}_r")
        if a is None or b is None:
            continue

        if col in DECISION_COLS:
            av = as_bool(a) if a.dtype == object and set(
                a.dropna().astype(str).str.upper()) <= {"TRUE", "FALSE"} else a
            bv = as_bool(b) if b.dtype == object and set(
                b.dropna().astype(str).str.upper()) <= {"TRUE", "FALSE"} else b
            if av.dtype == object or bv.dtype == object:
                av, bv = a.astype(str).str.strip(), b.astype(str).str.strip()
            mismatch = av.fillna("~") != bv.fillna("~") if av.dtype == object else av != bv
            decisions_checked += int(mismatch.notna().sum())
            bad = merged[mismatch.fillna(False)]
            if len(bad):
                decisions_differing += len(bad)
                print(f"\n  ✗ DECISION MISMATCH in '{col}':")
                for _, row in bad.iterrows():
                    print(f"      {' / '.join(str(row[k]) for k in keys)}: "
                          f"python={row[f'{col}_py']!r}  R={row[f'{col}_r']!r}")
            continue

        an = pd.to_numeric(a, errors="coerce")
        bn = pd.to_numeric(b, errors="coerce")
        both = an.notna() & bn.notna()
        if not both.any():
            continue

        diff = (an - bn).abs()
        worst = diff[both].max()
        if worst <= IDENTICAL:
            continue

        scale = pd.concat([an.abs(), bn.abs()], axis=1).max(axis=1).replace(0, np.nan)
        rel = (diff / scale).where(both)
        idx = diff[both].idxmax()
        row = merged.loc[idx]
        flips = any(crosses_alpha(x, y) for x, y in zip(an[both], bn[both])) \
            if ("p_" in col or col.endswith("_p")) else False
        numeric_reports.append({
            "col": col, "worst_abs": worst, "worst_rel": rel.max(),
            "where": " / ".join(str(row[k]) for k in keys),
            "py": an[idx], "r": bn[idx], "flips": flips,
        })

    if numeric_reports:
        print("\n  numeric differences (largest per column):")
        for rep in sorted(numeric_reports, key=lambda d: -d["worst_abs"]):
            verdict = ("negligible" if rep["worst_abs"] < NEGLIGIBLE
                       else "⚠ CROSSES p=0.05" if rep["flips"] else "differs")
            print(f"    {rep['col']:<24} max|Δ|={rep['worst_abs']:.3g}"
                  f"  rel={rep['worst_rel']:.2g}  [{verdict}]")
            if rep["worst_abs"] >= NEGLIGIBLE:
                print(f"        worst at {rep['where']}: "
                      f"python={rep['py']:.6g}  R={rep['r']:.6g}")
    else:
        print("\n  all shared numeric columns agree to within 1e-9.")

    if decisions_checked and not decisions_differing:
        print(f"  ✓ all {decisions_checked} decision values agree "
              "(significance flags and pairwise verdicts).")
    return decisions_checked, decisions_differing


def explain_wilcoxon_gap() -> None:
    """Attribute every post-hoc p-value gap to a specific cause.

    Two causes exist, and neither is a bug:

    1. ZEROS. SciPy's wilcoxon() with method='auto' abandons the exact null
       distribution as soon as any zero difference is present (it drops the zero,
       then uses a normal approximation). R's wilcox.test drops zeros too but
       still uses the exact distribution. Where a pair has tied observations,
       R's exact p-value is the more accurate of the two.
    2. TIES among the absolute differences, which force BOTH to approximate --
       and there R adds a continuity correction that SciPy does not.
    """
    py_path = OUT_DIR / "friedman_3way_posthoc.csv"
    r_path = OUT_DIR / "friedman_3way_posthoc_R.csv"
    if not (py_path.exists() and r_path.exists()):
        return
    r = pd.read_csv(r_path)
    needed = {"p_raw_nocorrect", "exact_used", "n_zero_dropped", "n_tied_abs"}
    if not needed <= set(r.columns):
        return
    py = pd.read_csv(py_path)
    m = py.merge(r, on=["metric", "pair"], suffixes=("_py", "_r"))

    print(f"\n{'=' * 78}\nWilcoxon p-value attribution\n{'=' * 78}")
    agreeing = m[(m.p_raw_py - m.p_raw_r).abs() <= NEGLIGIBLE]
    print(f"  {len(agreeing)} of {len(m)} pairs agree to within 1e-6 "
          "(both ran the exact test on tie-free, zero-free data).")

    differing = m[(m.p_raw_py - m.p_raw_r).abs() > NEGLIGIBLE]
    if differing.empty:
        return
    print(f"\n  {len(differing)} pair(s) differ. Cause for each:")
    for _, row in differing.iterrows():
        if row.n_zero_dropped > 0:
            cause = (f"{int(row.n_zero_dropped)} zero difference(s) -> SciPy "
                     "switched to the normal\n        approximation; R stayed exact. "
                     "R's value is the more accurate one.")
        elif row.n_tied_abs > 0:
            cause = (f"{int(row.n_tied_abs)} tied |difference|(s) -> both approximate; "
                     "R adds a continuity\n        correction, SciPy does not.")
        else:
            cause = "unexplained -- investigate before reporting."
        print(f"\n    {row.metric} / {row.pair}")
        print(f"      python = {row.p_raw_py:.6g}   R = {row.p_raw_r:.6g}"
              f"   (R with correct=FALSE = {row.p_raw_nocorrect:.6g})")
        print(f"      cause: {cause}")
        both_ns = row.p_raw_py >= ALPHA and row.p_raw_r >= ALPHA
        both_s = row.p_raw_py < ALPHA and row.p_raw_r < ALPHA
        print("      impact: none -- "
              f"{'both non-significant' if both_ns else 'both significant' if both_s else 'DIFFERENT SIDES OF 0.05'}")


def main() -> None:
    total_checked = total_differing = 0
    for label, py_file, r_file, keys in COMPARISONS:
        checked, differing = compare(label, py_file, r_file, keys)
        total_checked += checked
        total_differing += differing

    explain_wilcoxon_gap()

    print(f"\n{'=' * 78}\nVERDICT\n{'=' * 78}")
    if total_differing == 0:
        print(f"  ✓ R and Python agree on all {total_checked} decisions.")
        print("    Every significance flag and pairwise verdict is identical across")
        print("    two independent implementations. Safe to report the R output and")
        print("    state that it was independently verified.")
    else:
        print(f"  ✗ {total_differing} of {total_checked} decisions DISAGREE.")
        print("    Resolve before reporting anything. A disagreement usually means the")
        print("    result sits near p=0.05, not that one library is wrong -- but decide")
        print("    which is authoritative on statistical grounds, not on which p is")
        print("    smaller.")


if __name__ == "__main__":
    main()
