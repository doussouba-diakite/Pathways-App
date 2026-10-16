"""Build data/colleges.csv from the U.S. College Scorecard (public domain).

Inputs (all public domain, U.S. Department of Education):
  school.rda, scorecard.rda  tidy Scorecard tables from the CRAN package
                             collegeScorecard (github.com/cran/collegeScorecard/data)
  <year>.parquet             full Scorecard file, used for majors (PCIP fields),
                             from github.com/gadenbuie/scorecard-db/data/parquet/merged

Usage:
  python scripts/build_colleges.py school.rda scorecard.rda 2024-25.parquet
"""
import sys

import pandas as pd
import pyreadr

BRACKETS = {"0_30k": "cost_avg_income_0_30k", "30_48k": "cost_avg_income_30_48k",
            "48_75k": "cost_avg_income_48_75k", "75_110k": "cost_avg_income_75_110k",
            "110k_plus": "cost_avg_income_110k_plus"}

FIELDS = ["n_undergrads", "rate_admissions", "score_sat_verbal_p25", "score_sat_verbal_p75",
          "score_sat_math_p25", "score_sat_math_p75", "score_act_p25", "score_act_p75",
          "cost_tuition_in", "cost_tuition_out", "cost_room_board_on", "rate_completion",
          "amnt_earnings_med_10y", *BRACKETS.values()]


def latest_values(sc: pd.DataFrame) -> pd.DataFrame:
    """For each school and field, keep the most recent year that has a value."""
    sc = sc.sort_values("academic_year")
    for c in FIELDS:
        sc[c] = pd.to_numeric(sc[c], errors="coerce")
    return sc.groupby("id")[FIELDS].last()


def build(school_rda: str, scorecard_rda: str, parquet: str) -> pd.DataFrame:
    school = pyreadr.read_r(school_rda)["school"]
    stats = latest_values(pyreadr.read_r(scorecard_rda)["scorecard"])
    df = school.set_index("id").join(stats, how="inner")

    # Operating, degree-granting colleges that enroll undergrads; no for-profits.
    df = df[df["deg_predominant"].astype(str).isin(["Associate", "Bachelor"])]
    df = df[df["control"].astype(str).isin(["Public", "Nonprofit"])]
    df = df[df["n_undergrads"] > 0]

    out = pd.DataFrame({
        "unitid": df.index.astype(int),
        "name": df["name"],
        "city": df["city"],
        "state": df["state"],
        "control": df["control"].astype(str).map({"Public": 1, "Nonprofit": 2}),
        "two_year": (df["deg_predominant"].astype(str) == "Associate").astype(int),
        "size": df["n_undergrads"].astype(int),
        "hbcu": df["is_hbcu"].fillna(False).astype(bool).astype(int),
        "womens": df["is_only_women"].fillna(False).astype(bool).astype(int),
        "website": df["url"],
        "lat": df["latitude"], "lon": df["longitude"],
        "admit_rate": df["rate_admissions"],
        # SAT total = verbal + math percentiles (the standard approximation).
        "sat_25": df["score_sat_verbal_p25"] + df["score_sat_math_p25"],
        "sat_75": df["score_sat_verbal_p75"] + df["score_sat_math_p75"],
        "act_25": df["score_act_p25"], "act_75": df["score_act_p75"],
        "tuition_in": df["cost_tuition_in"], "tuition_out": df["cost_tuition_out"],
        "room_board": df["cost_room_board_on"],
        "grad_rate": df["rate_completion"],
        "earnings_10y": df["amnt_earnings_med_10y"],
    })
    for label, col in BRACKETS.items():
        out[f"net_price_{label}"] = df[col].values

    # Share of degrees awarded in each major family (CIP 2-digit), e.g. PCIP11 = computer science.
    full = pd.read_parquet(parquet)
    pcip = [c for c in full.columns if c.startswith("PCIP")]
    majors = full[["UNITID", *pcip]].copy()
    majors["UNITID"] = pd.to_numeric(majors["UNITID"], errors="coerce")
    majors = majors.dropna(subset=["UNITID"]).astype({"UNITID": int}).set_index("UNITID")
    majors = majors.apply(pd.to_numeric, errors="coerce").round(4)
    majors.columns = [f"pcip_{c[4:]}" for c in majors.columns]
    out = out.join(majors, on="unitid")
    return out.sort_values(["state", "name"]).reset_index(drop=True)


if __name__ == "__main__":
    out = build(*sys.argv[1:4])
    out.to_csv("data/colleges.csv", index=False)
    print(f"wrote data/colleges.csv: {len(out):,} colleges")
