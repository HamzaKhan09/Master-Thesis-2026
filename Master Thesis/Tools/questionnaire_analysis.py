"""
Scores and compares the SUS / IPQ / VEQ questionnaire data collected once per
condition, and runs the same statistical framework used for the technical data.

CONDITION MAPPING -- the part that most easily goes wrong:
The form labels the two camera-based conditions "1st HMD-based system" and
"2nd HMD-based system", which is POSITIONAL, not a system name; only OptiTrack
is unambiguous. The mapping therefore differs per participant, and across the
sample "1st HMD-based system" is HYTRACK for 10 participants and MetaQuest for 9
-- so there is no global rule and a wrong assumption would silently swap the two
systems for roughly half the sample.

Confirmed by the user (2026-08-30): the labels follow the COUNTERBALANCE
SCHEDULE's planned order, not the order actually executed. So for each
participant the two non-OptiTrack conditions are read from
counterbalance_schedule.xlsx in planned order; the first is "1st HMD-based
system", the second is "2nd". (The plan and the recorded session order disagree
for 7 of 19 participants, which is exactly why this had to be settled explicitly
rather than inferred from log timestamps.)

INSTRUMENTS as actually administered:
  SUS  -- standard 10 items, 5-point, correct alternating polarity.
  IPQ  -- the full ORIGINAL 14-item version, 7-point. Note this version has
          documented reliability problems (a revised 11-item version is the
          validated one), so Cronbach's alpha is reported per subscale and
          should be quoted honestly in the write-up rather than assumed good.
  VEQ  -- Ownership and Agency only; the "Change" subscale was not administered.
          Two extra leg-specific embodiment items were added by the study and are
          reported separately as a custom scale, NOT folded into VEQ.
  Extra -- three custom items on responsiveness, delay and smoothness. These are
          subjective, and partly recover constructs that could not be measured
          objectively (latency was unmeasurable; smoothness was not resolvable at
          the ~6 Hz logging rate).

REVERSE CODING -- the second thing that most easily goes wrong:
Several IPQ items are negatively worded, but the official igroup form prints
them with INVERTED anchor labels, so their raw values already run in the
presence direction. The official key therefore reverses only SP2, INV3 and
REAL1 -- NOT SP3 ("I did not feel present") or INV1 ("how aware were you of the
real world"), despite how those read.

The anchors actually used in this study's Google Form were checked item by item
(2026-08-30) and match the official form for SP3, INV1 and REAL1 -- with one
exception: REAL3 was entered with its anchors FLIPPED (running
"indistinguishable from real" -> "not real at all" rather than the official
direction), so REAL3 must be reversed here even though the official key does not
reverse it. That single transcription slip is what made the Realism subscale
incoherent. Item-total correlations corroborate all four decisions independently.

Reverse-coded items are declared explicitly below and VERIFIED empirically: the
script reports corrected item-total correlations and flags any item correlating
negatively with the rest of its subscale, which is the signature of a coding
error. Nothing is silently re-coded.

Produces:
  StudyData/analysis/questionnaire_scores_by_participant.csv
  StudyData/analysis/questionnaire_reliability.csv
  StudyData/analysis/questionnaire_tests.csv

Run with:  conda run -n thesis-eval python questionnaire_analysis.py
"""
from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from analyze_study_data import OUT_DIR
from stats_analysis_3way import CONDITIONS, kendalls_w, holm_adjust

FIG_DIR = OUT_DIR / "figures"
SCHEDULE = FIG_DIR / "counterbalance_schedule.xlsx"
RESPONSES = FIG_DIR / "System Evaluation (Responses).xlsx"
FINAL = FIG_DIR / "Final Questions (Responses).xlsx"

SCHEDULE_NAME = {"RGB camera tracking": "HYTRACK",
                 "Meta Quest tracking": "MetaQuest",
                 "OptiTrack tracking": "OptiTrack"}

PILOT = "P00"          # pilot participant, excluded from all analysis
LIKERT_MAX = {"VEQ": 7, "IPQ": 7, "SUS": 5, "EXTRA": 7}

# column indices in the responses sheet
COND_COL = 2
SUBSCALES = {
    # VEQ (as administered -- Ownership + Agency only)
    "VEQ Ownership":        ("VEQ", [3, 4, 5, 6], []),
    "VEQ Agency":           ("VEQ", [7, 8, 9, 10], []),
    "Leg embodiment*":      ("VEQ", [11, 12], []),
    # IPQ, original 14-item. Reverse items = SP2, INV3, REAL1, REAL3.
    # This follows the official igroup scoring (which reverses only SP2, INV3 and
    # REAL1), plus REAL3 -- see the REVERSE CODING note in the module docstring.
    "IPQ General Presence": ("IPQ", [13], []),
    "IPQ Spatial Presence": ("IPQ", [14, 15, 16, 17, 18], [15]),
    "IPQ Involvement":      ("IPQ", [19, 20, 21, 22], [21]),
    "IPQ Realism":          ("IPQ", [23, 24, 25, 26], [23, 25]),
    # custom subjective counterparts to the objective measures
    "Responsiveness*":      ("EXTRA", [37, 38], [38]),
    "Perceived smoothness*": ("EXTRA", [39], []),
}
SUS_POSITIVE = [27, 29, 31, 33, 35]
SUS_NEGATIVE = [28, 30, 32, 34, 36]


# --------------------------------------------------------------------------- #
# Condition mapping
# --------------------------------------------------------------------------- #

def build_label_map(schedule: pd.DataFrame) -> dict[tuple[str, str], str]:
    """(participant, form label) -> real system name, from the PLANNED order."""
    out = {}
    for _, r in schedule.iterrows():
        planned = [SCHEDULE_NAME[r[c]] for c in ("1st_condition", "2nd_condition", "3rd_condition")]
        hmd = [c for c in planned if c != "OptiTrack"]
        out[(r.participant, "1st HMD-based system")] = hmd[0]
        out[(r.participant, "2nd HMD-based system")] = hmd[1]
        out[(r.participant, "OptiTrack")] = "OptiTrack"
    return out


# --------------------------------------------------------------------------- #
# Reliability
# --------------------------------------------------------------------------- #

def cronbach_alpha(items: pd.DataFrame) -> float:
    k = items.shape[1]
    if k < 2:
        return np.nan
    item_var = items.var(axis=0, ddof=1).sum()
    total_var = items.sum(axis=1).var(ddof=1)
    if total_var == 0:
        return np.nan
    return float(k / (k - 1) * (1 - item_var / total_var))


def item_total_corrs(items: pd.DataFrame) -> dict[str, float]:
    """Corrected item-total correlation: each item vs the SUM OF THE OTHERS.
    A negative value means the item runs opposite to its own subscale -- almost
    always a reverse-coding mistake rather than a real finding."""
    out = {}
    for c in items.columns:
        rest = items.drop(columns=[c]).sum(axis=1)
        out[c] = np.nan if rest.std() == 0 else float(np.corrcoef(items[c], rest)[0, 1])
    return out


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #

def score(resp: pd.DataFrame, label_map: dict,
          exclude: tuple[str, ...] = ()) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = resp.columns
    resp = resp.dropna(subset=["Participant code"]).copy()
    resp = resp[resp["Participant code"] != PILOT]
    if exclude:
        resp = resp[~resp["Participant code"].isin(exclude)]
    resp["condition"] = [label_map.get((p, l)) for p, l in
                         zip(resp["Participant code"], resp[cols[COND_COL]])]
    missing = resp.condition.isna().sum()
    if missing:
        raise ValueError(f"{missing} responses could not be mapped to a condition")

    scores = resp[["Participant code", "condition"]].rename(
        columns={"Participant code": "participant_id"}).reset_index(drop=True)

    rel_rows, item_rows = [], []

    def keep_items(block: pd.DataFrame, indices, subscale: str, reverse) -> None:
        """Stash the reverse-coded item values so the R analysis can recompute
        reliability without re-deriving the condition mapping (which is the one
        step that must exist in exactly one place)."""
        for i, col in zip(indices, block.columns):
            item_rows.append(pd.DataFrame({
                "participant_id": scores.participant_id, "condition": scores.condition,
                "subscale": subscale, "item": f"i{i}", "reversed": i in reverse,
                "value": block[col].values}))

    for name, (family, idx, reverse) in SUBSCALES.items():
        mx = LIKERT_MAX[family]
        block = pd.DataFrame({
            cols[i]: (mx + 1 - pd.to_numeric(resp[cols[i]], errors="coerce"))
            if i in reverse else pd.to_numeric(resp[cols[i]], errors="coerce")
            for i in idx
        }).reset_index(drop=True)
        scores[name] = block.mean(axis=1)
        keep_items(block, idx, name, reverse)

        corrs = item_total_corrs(block) if block.shape[1] > 1 else {}
        rel_rows.append({
            "subscale": name, "n_items": len(idx),
            "cronbach_alpha": cronbach_alpha(block) if len(idx) > 1 else np.nan,
            "min_item_total_r": min(corrs.values()) if corrs else np.nan,
            "flagged_item": (min(corrs, key=corrs.get)[:60]
                             if corrs and min(corrs.values()) < 0 else ""),
        })

    # SUS: (positive - 1) + (5 - negative), summed, x2.5 -> 0-100
    pos = sum(pd.to_numeric(resp[cols[i]], errors="coerce") - 1 for i in SUS_POSITIVE)
    neg = sum(5 - pd.to_numeric(resp[cols[i]], errors="coerce") for i in SUS_NEGATIVE)
    scores["SUS (0-100)"] = ((pos + neg) * 2.5).reset_index(drop=True)

    sus_block = pd.DataFrame({
        cols[i]: (pd.to_numeric(resp[cols[i]], errors="coerce") - 1) if i in SUS_POSITIVE
        else (5 - pd.to_numeric(resp[cols[i]], errors="coerce"))
        for i in SUS_POSITIVE + SUS_NEGATIVE
    }).reset_index(drop=True)
    corrs = item_total_corrs(sus_block)
    rel_rows.append({
        "subscale": "SUS (0-100)", "n_items": 10,
        "cronbach_alpha": cronbach_alpha(sus_block),
        "min_item_total_r": min(corrs.values()),
        "flagged_item": min(corrs, key=corrs.get)[:60] if min(corrs.values()) < 0 else "",
    })
    keep_items(sus_block, SUS_POSITIVE + SUS_NEGATIVE, "SUS (0-100)", SUS_NEGATIVE)

    return scores, pd.DataFrame(rel_rows), pd.concat(item_rows, ignore_index=True)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

SHORT = {"HYTRACK": "HY", "MetaQuest": "MQ", "OptiTrack": "OT"}


def run_tests(scores: pd.DataFrame) -> pd.DataFrame:
    measures = [c for c in scores.columns if c not in ("participant_id", "condition")]
    rows = []
    for m in measures:
        wide = scores.pivot(index="participant_id", columns="condition", values=m)
        wide = wide.dropna(subset=CONDITIONS)[CONDITIONS]
        chi2, p = stats.friedmanchisquare(*[wide[c].values for c in CONDITIONS])

        raw, pairs = [], []
        for a, b in itertools.combinations(CONDITIONS, 2):
            try:
                _, pp = stats.wilcoxon(wide[a].values, wide[b].values)
            except ValueError:
                pp = np.nan
            raw.append(float(pp))
            pairs.append((a, b))

        verdict = []
        for (a, b), padj in zip(pairs, holm_adjust(raw)):
            sig = np.isfinite(padj) and padj < 0.05
            rel = "<" if wide[a].mean() < wide[b].mean() else ">"
            verdict.append(f"{SHORT[a]}{rel}{SHORT[b]}" if sig else f"{SHORT[a]}≈{SHORT[b]}")

        row = {"measure": m, "n": len(wide),
               "friedman_chi2": float(chi2), "friedman_p": float(p),
               "kendalls_w": kendalls_w(chi2, len(wide), 3),
               "significant": bool(p < 0.05), "pairwise": "  ".join(verdict)}
        for c in CONDITIONS:
            row[f"{c.lower()}_mean"] = float(wide[c].mean())
            row[f"{c.lower()}_sd"] = float(wide[c].std(ddof=1))
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exclude", nargs="*", default=[], metavar="PID",
                    help="further participant codes to drop, e.g. --exclude P20. "
                         "The pilot is always excluded regardless of this flag.")
    ap.add_argument("--suffix", default="", metavar="SFX",
                    help="suffix appended to every output filename, e.g. _n19, so "
                         "a variant run cannot overwrite the primary results.")
    args = ap.parse_args()
    exclude, sfx = tuple(args.exclude), args.suffix

    schedule = pd.read_excel(SCHEDULE)
    resp = pd.read_excel(RESPONSES)
    label_map = build_label_map(schedule)

    scores, reliability, items = score(resp, label_map, exclude)
    tests = run_tests(scores)

    scores.to_csv(OUT_DIR / f"questionnaire_scores_by_participant{sfx}.csv", index=False)
    reliability.to_csv(OUT_DIR / f"questionnaire_reliability{sfx}.csv", index=False)
    tests.to_csv(OUT_DIR / f"questionnaire_tests{sfx}.csv", index=False)
    items.to_csv(OUT_DIR / f"questionnaire_items_coded{sfx}.csv", index=False)

    n = scores.participant_id.nunique()
    also = f", {' '.join(exclude)} excluded" if exclude else ""
    print(f"Scored {len(scores)} responses from {n} participants "
          f"(pilot {PILOT} excluded{also})\n")

    print("=== Reliability (Cronbach's alpha) ===")
    print("  * = custom scale added by this study, not part of the published instrument")
    for _, r in reliability.iterrows():
        a = r.cronbach_alpha
        note = ""
        if np.isfinite(a):
            note = ("very good" if a >= 0.8 else "good" if a >= 0.7
                    else "acceptable" if a >= 0.6 else "POOR")
        flag = f"   <-- CHECK CODING: {r.flagged_item}" if r.flagged_item else ""
        print(f"  {r.subscale:<24} k={r.n_items:<3} alpha="
              f"{'n/a (single item)' if not np.isfinite(a) else f'{a:.3f}  {note}'}{flag}")

    print("\n=== Condition comparison (Friedman, Holm-corrected post-hoc) ===")
    for _, r in tests.iterrows():
        mark = "*" if r.significant else " "
        print(f"  {r.measure:<24} HY {r.hytrack_mean:6.2f}  MQ {r.metaquest_mean:6.2f}  "
              f"OT {r.optitrack_mean:6.2f}   p={r.friedman_p:.4f}{mark}  "
              f"W={r.kendalls_w:.2f}   {r.pairwise}")

    print(f"\nWrote {OUT_DIR / f'questionnaire_scores_by_participant{sfx}.csv'}")
    print(f"Wrote {OUT_DIR / f'questionnaire_reliability{sfx}.csv'}")
    print(f"Wrote {OUT_DIR / f'questionnaire_tests{sfx}.csv'}")
    print(f"Wrote {OUT_DIR / f'questionnaire_items_coded{sfx}.csv'}  (item-level input for stats in R)")


if __name__ == "__main__":
    main()
