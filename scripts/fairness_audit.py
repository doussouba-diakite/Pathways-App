"""Fairness check: does anything other than academics change a student's admissions labels?

Method: hold academics fixed, change ONE thing (income, immigration status, household size),
and compare the Safety / Match / Reach labels across every college in the dataset.
Admissions labels should depend only on GPA and test scores. Price and aid SHOULD change.

Usage: python scripts/fairness_audit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from pathways import aid  # noqa: E402
from pathways.colleges import Student, match_colleges  # noqa: E402
from pathways.data import load_colleges  # noqa: E402

ACADEMICS = [Student(gpa=2.8), Student(gpa=3.4, sat=1150), Student(gpa=3.9, act=31)]
INCOMES = [15_000, 40_000, 65_000, 95_000, 150_000]
STATUSES = ["Citizen or permanent resident", "DACA", "Undocumented"]


def main() -> None:
    colleges = load_colleges()
    rows, problems = [], 0
    for s in ACADEMICS:
        label = f"GPA {s.gpa}" + (f", SAT {s.sat}" if s.sat else "") + (f", ACT {s.act}" if s.act else "")
        base = match_colleges(colleges, s, income=INCOMES[0], n=0).set_index("unitid")["fit"]
        for inc in INCOMES[1:]:
            other = match_colleges(colleges, s, income=inc, n=0).set_index("unitid")["fit"]
            changed = int((base != other.reindex(base.index)).sum())
            problems += changed
            rows.append({"student": label, "changed": f"income $15k -> ${inc // 1000}k",
                         "labels that moved": changed, "schools checked": len(base)})
        mid = match_colleges(colleges, s, income=40_000, n=0)
        rows.append({"student": label, "changed": "net price, $15k vs $150k income",
                     "labels that moved": "n/a (price should change)",
                     "schools checked": f"median ${mid['net_price_0_30k'].median():,.0f} vs "
                                        f"${mid['net_price_110k_plus'].median():,.0f}"})

    print("## Admissions labels vs. income\n")
    print(pd.DataFrame(rows).to_markdown(index=False))

    print("\n## Aid by immigration status (income $30k, household 4, NY)\n")
    aid_rows = []
    for st in STATUSES:
        r = aid.screen(aid.AidInput(income=30_000, status=st))
        aid_rows.append({"status": st, "Pell": r.pell, "TAP": r.tap, "Dream Act": r.dream_act,
                         "Opportunity programs": r.opportunity_programs})
    print(pd.DataFrame(aid_rows).to_markdown(index=False))
    print("\nResult:", "PASS: income never changes admissions labels." if problems == 0
          else f"FAIL: {problems} labels changed with income.")


if __name__ == "__main__":
    main()
