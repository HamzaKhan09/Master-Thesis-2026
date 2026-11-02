"""
Read the statistics computed in R, so that no figure ever restates a number by
hand.

WHY THIS EXISTS: the motion-fidelity and robustness figures used to carry their
p-values as literal strings ("Friedman p = 0.368"). They happened to be correct,
but nothing kept them correct -- rerun the analysis on changed data and the
figure would keep printing the old number. R is the reporting source, so the
figures read R's output instead.

R writes CRLF inside quoted multi-line cells on Windows, and the measure names
contain a newline for the two-line table layout, so every key is whitespace-
normalised before matching ("Motion fidelity, legs\r\n(cm/s)" -> "Motion
fidelity, legs (cm/s)").
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from stats_analysis import ANALYSIS_DIR

ROWS_CSV = "results_table_rows_R.csv"
POSTHOC_CSV = "results_table_posthoc_R.csv"
ALPHA = 0.05

# keys, as passed by the figure scripts
LIMBS = "Motion fidelity, limbs (cm/s)"
LEGS = "Motion fidelity, legs (cm/s)"
ROBUSTNESS = "Robustness (% frames lost)"


def _norm(s: object) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


def _require(name: str) -> pd.DataFrame:
    path = ANALYSIS_DIR / name
    if not path.exists():
        raise SystemExit(
            f"{name} not found -- the statistics are computed in R.\n"
            f"Run first:  conda run -n r-thesis Rscript stats_report.R")
    return pd.read_csv(path)


def fmt_p(p: float, dp: int = 3) -> str:
    """'< 0.001' or '= 0.060'. Never invents precision R did not produce."""
    if not np.isfinite(p):
        return "not available"
    return "< 0.001" if p < 0.001 else f"= {p:.{dp}f}"


def omnibus_p(measure: str) -> float:
    rows = _require(ROWS_CSV)
    rows["_key"] = rows.measure.map(_norm)
    hit = rows[rows._key == _norm(measure)]
    if hit.empty:
        raise SystemExit(f"measure {measure!r} not found in {ROWS_CSV}; "
                         f"available: {sorted(rows._key)}")
    return float(hit.iloc[0]["p"])


def n_for(measure: str) -> int:
    rows = _require(ROWS_CSV)
    rows["_key"] = rows.measure.map(_norm)
    return int(rows[rows._key == _norm(measure)].iloc[0]["n"])


def pairs_summary(measure: str) -> str:
    """Plain-language summary of the Holm-corrected pairwise tests.

    Names only the pairs that failed to reach significance -- those are the ones
    a reader needs the number for -- and collapses the rest, which is how the
    figures were already worded before they were wired up to R.
    """
    ph = _require(POSTHOC_CSV)
    ph["_key"] = ph.metric.map(_norm)
    sub = ph[ph._key == _norm(measure)]
    if sub.empty:
        raise SystemExit(f"metric {measure!r} not found in {POSTHOC_CSV}")

    sig = sub[sub.significant_after_holm.astype(str).str.upper() == "TRUE"]
    ns = sub[sub.significant_after_holm.astype(str).str.upper() != "TRUE"]

    if ns.empty:
        return "all three pairs differ significantly (Holm-corrected)"
    if sig.empty:
        return "no pair differs significantly (Holm-corrected)"

    parts = [f"{r.pair.replace(' vs ', ' vs ')} not significant "
             f"(p {fmt_p(float(r.p_holm))})" for r in ns.itertuples()]
    worst = float(sig.p_holm.max())
    rest = ("both other pairs" if len(sig) == 2 else "the other pair")
    parts.append(f"{rest} p {fmt_p(worst)}")
    return "     ".join(parts)


def achieved_rate_hz() -> tuple[float, float]:
    """Lowest and highest per-condition mean logging rate, for the caption."""
    cont = pd.read_csv(ANALYSIS_DIR / "tracking_continuity_by_participant.csv")
    per_condition = cont.groupby("condition").achieved_hz.mean()
    return float(per_condition.min()), float(per_condition.max())
