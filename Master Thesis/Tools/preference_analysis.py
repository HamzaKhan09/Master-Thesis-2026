"""
Forced-choice preference items from the final questionnaire.

CONDITION MAPPING -- the same trap as the per-condition questionnaire: the form
labels the two camera-based systems "1st/2nd HMD-based system", which is
POSITIONAL. The mapping differs per participant and is read from the
counterbalance schedule's planned order via questionnaire_analysis.build_label_map,
so the logic exists in exactly one place.

These items are a second, independent read on the same question the rating
scales answer, and they surface a tension the ratings cannot: participants can
rate OptiTrack highest on realism while still choosing a markerless system for
actual use.

Produces:
  StudyData/analysis/preferences_by_participant.csv   (one row per participant per item)
  StudyData/analysis/preference_counts.csv            (counts per item per option)

Run with:  conda run -n thesis-eval python preference_analysis.py
"""
from __future__ import annotations

import argparse

import pandas as pd

from analyze_study_data import OUT_DIR
from questionnaire_analysis import FIG_DIR, SCHEDULE, PILOT, build_label_map

FINAL = FIG_DIR / "Final Questions (Responses).xlsx"

# column index -> short item name. Only forced-choice items; the free-text
# columns are a separate qualitative pass and are not touched here.
ITEMS = {
    2: "Felt most like real legs",
    3: "Responded fastest",
    4: "Preferred for regular VR use",
    6: "Marker-based vs markerless",
    8: "Would pick for personal use",
}
# item 6 offers a different pair of options and is analysed as a two-way choice
TWO_WAY = "Marker-based vs markerless"
TWO_WAY_LABELS = {"Markerless (HMD-based systems)": "Markerless",
                  "Marker-based (OptiTrack)": "Marker-based"}


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

    resp = pd.read_excel(FINAL)
    resp = resp.dropna(subset=["Participant code"])
    resp = resp[resp["Participant code"] != PILOT]
    if exclude:
        resp = resp[~resp["Participant code"].isin(exclude)]
    label_map = build_label_map(pd.read_excel(SCHEDULE))
    cols = resp.columns

    rows = []
    for idx, item in ITEMS.items():
        for _, r in resp.iterrows():
            answer = r[cols[idx]]
            if pd.isna(answer):
                continue
            pid = r["Participant code"]
            if item == TWO_WAY:
                choice = TWO_WAY_LABELS.get(str(answer).strip(), str(answer).strip())
            else:
                # "OptiTrack" is unambiguous; the two HMD labels are positional
                choice = label_map.get((pid, str(answer).strip()))
                if choice is None:
                    raise ValueError(
                        f"could not map answer {answer!r} for {pid} on {item!r}")
            rows.append({"participant_id": pid, "item": item, "choice": choice})

    long = pd.DataFrame(rows)
    counts = (long.groupby(["item", "choice"]).size().rename("n").reset_index())
    counts["n_responses"] = counts.groupby("item").n.transform("sum")
    counts["pct"] = counts.n / counts.n_responses * 100

    out_long = OUT_DIR / f"preferences_by_participant{sfx}.csv"
    out_counts = OUT_DIR / f"preference_counts{sfx}.csv"
    long.to_csv(out_long, index=False)
    counts.to_csv(out_counts, index=False)

    also = f", {' '.join(exclude)} excluded" if exclude else ""
    print(f"{long.participant_id.nunique()} participants "
          f"(pilot {PILOT} excluded{also})\n")
    for item in ITEMS.values():
        sub = counts[counts.item == item].sort_values("n", ascending=False)
        total = int(sub.n_responses.iloc[0])
        print(f"  {item}   (n = {total})")
        for _, r in sub.iterrows():
            print(f"      {r.choice:<14} {int(r.n):>3}  ({r.pct:.0f}%)")
        print()

    print(f"Wrote {out_long}")
    print(f"Wrote {out_counts}")


if __name__ == "__main__":
    main()
