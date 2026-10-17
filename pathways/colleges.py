"""College matching: filter, classify (Safety / Match / Reach), rank, balance.

Every classification comes with a plain-English reason, so a student or
counselor can see *why* a school landed where it did.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .distance import add_miles
from .majors import cip_families_for

SAFETY, MATCH, REACH, UNKNOWN = "Safety", "Match", "Reach", "Unknown"
FIT_ORDER = {SAFETY: 0, MATCH: 1, REACH: 2, UNKNOWN: 3}

SIZE_BANDS = {  # undergraduate enrollment
    "Any": (0, 10**9),
    "Small (under 5k)": (0, 5_000),
    "Medium (5k-15k)": (5_000, 15_000),
    "Large (15k+)": (15_000, 10**9),
}


@dataclass
class Student:
    gpa: float | None = None          # unweighted, 4.0 scale
    sat: int | None = None            # total, 400-1600
    act: int | None = None            # composite, 1-36
    states: list[str] = field(default_factory=list)   # empty = anywhere
    size: str = "Any"
    control: str = "Any"              # Any | Public | Private
    years: str = "4-year"             # 4-year | 2-year | Any
    hbcu_only: bool = False
    womens_only: bool = False
    major: str = ""
    max_cost: float | None = None     # yearly budget after aid, optional
    home: tuple[float, float] | None = None   # (lat, lon) from the student's ZIP code
    max_miles: float | None = None    # only schools within this distance (combined with states, if any)
    major_families: list[str] | None = None   # CIP codes already resolved (e.g. by the AI fallback)


def classify(student: Student, school: pd.Series) -> tuple[str, str]:
    """Return (fit, reason). Uses the strongest evidence available, in order:
    SAT percentiles -> ACT percentiles -> acceptance rate + GPA -> unknown."""
    sat25, sat75 = school.get("sat_25"), school.get("sat_75")
    if student.sat and pd.notna(sat25) and pd.notna(sat75):
        if student.sat >= sat75:
            return SAFETY, f"Your SAT {student.sat} is at or above this school's 75th percentile ({int(sat75)})."
        if student.sat >= sat25:
            return MATCH, f"Your SAT {student.sat} is inside the middle 50% ({int(sat25)}-{int(sat75)})."
        return REACH, f"Your SAT {student.sat} is below the 25th percentile ({int(sat25)})."

    act25, act75 = school.get("act_25"), school.get("act_75")
    if student.act and pd.notna(act25) and pd.notna(act75):
        if student.act >= act75:
            return SAFETY, f"Your ACT {student.act} is at or above the 75th percentile ({int(act75)})."
        if student.act >= act25:
            return MATCH, f"Your ACT {student.act} is inside the middle 50% ({int(act25)}-{int(act75)})."
        return REACH, f"Your ACT {student.act} is below the 25th percentile ({int(act25)})."

    rate = school.get("admit_rate")
    if pd.notna(rate):
        pct = rate * 100
        gpa = student.gpa or 0
        # Without test scores we know less, so we stay conservative: only near-open
        # schools are Safety unless the GPA is very strong.
        if pct >= 85 or school.get("two_year") == 1:
            fit = SAFETY
        elif pct >= 70:
            fit = SAFETY if gpa >= 3.0 else MATCH
        elif pct >= 50:
            fit = SAFETY if gpa >= 3.7 else MATCH if gpa >= 2.8 else REACH
        elif pct >= 35:
            fit = MATCH if gpa >= 3.5 else REACH
        else:
            fit = REACH  # under 35% admitted is a reach for everyone
        basis = f"{pct:.0f}% of applicants are admitted"
        return fit, f"No test scores to compare, so this uses the acceptance rate ({basis}) and your GPA."

    if school.get("two_year") == 1:
        return SAFETY, "Open-admission community college."
    return UNKNOWN, "This school doesn't publish admissions data. Check its website."


def yearly_cost(school: pd.Series) -> float | None:
    """Sticker price: in-state tuition plus on-campus room and board when known."""
    tuition = school.get("tuition_in")
    if pd.isna(tuition):
        return None
    rb = school.get("room_board")
    return float(tuition) + (float(rb) if pd.notna(rb) else 0.0)


def filter_colleges(colleges: pd.DataFrame, s: Student) -> pd.DataFrame:
    df = colleges
    df = df[df["control"].isin([1, 2])]  # leave out for-profit schools
    if s.home and s.max_miles:
        df = add_miles(df, s.home)
        df = df[df["miles"] <= s.max_miles]
    if s.states:  # with a distance too: schools in these states AND within range
        df = df[df["state"].isin(s.states)]
    lo, hi = SIZE_BANDS.get(s.size, SIZE_BANDS["Any"])
    if s.size != "Any":
        df = df[df["size"].between(lo, hi, inclusive="left")]
    if s.control == "Public":
        df = df[df["control"] == 1]
    elif s.control == "Private":
        df = df[df["control"] == 2]
    if s.years == "4-year":
        df = df[df["two_year"] == 0]
    elif s.years == "2-year":
        df = df[df["two_year"] == 1]
    if s.hbcu_only:
        df = df[df["hbcu"] == 1]
    if s.womens_only:
        df = df[df["womens"] == 1]
    if s.major or s.major_families:
        fams = s.major_families or cip_families_for(s.major)
        cols = [f"pcip_{f}" for f in fams if f"pcip_{f}" in df.columns]
        if cols:
            df = df[df[cols].fillna(0).sum(axis=1) > 0]
    return df


def income_bracket(income: float) -> str:
    """College Scorecard reports average net price in five family-income brackets."""
    for limit, label in [(30_000, "0_30k"), (48_000, "30_48k"), (75_000, "48_75k"), (110_000, "75_110k")]:
        if income <= limit:
            return label
    return "110k_plus"


def match_colleges(colleges: pd.DataFrame, s: Student, income: float | None = None, n: int = 12) -> pd.DataFrame:
    """Filter, classify, rank, and return a balanced list of n schools.

    n=0 returns every matching school (for the map and charts)."""
    df = filter_colleges(colleges, s).copy()
    if df.empty:
        return df
    if "miles" not in df.columns:
        df = add_miles(df, s.home)

    fits = df.apply(lambda r: classify(s, r), axis=1)
    df["fit"] = [f for f, _ in fits]
    df["why"] = [w for _, w in fits]
    df["sticker"] = df.apply(yearly_cost, axis=1)
    # Real average price paid by families in the student's income bracket (after grants).
    col = f"net_price_{income_bracket(income)}" if income is not None else None
    df["net_cost"] = df[col] if col in df.columns else df["sticker"]
    if s.max_cost:
        df = df[df["net_cost"].isna() | (df["net_cost"] <= s.max_cost)]

    fams = s.major_families or (cip_families_for(s.major) if s.major else [])
    cols = [f"pcip_{f}" for f in fams if f"pcip_{f}" in df.columns]
    df["major_share"] = df[cols].fillna(0).sum(axis=1) if cols else 0.0

    # Rank inside each bucket: strongest program, then graduation rate, then cheapest.
    df = df.sort_values(["major_share", "grad_rate", "net_cost"], ascending=[False, False, True],
                        na_position="last")

    if n == 0:
        return df

    # Balanced list: about 25% safety, 45% match, 30% reach.
    want = {SAFETY: max(2, round(n * 0.25)), MATCH: max(3, round(n * 0.45)), REACH: max(2, round(n * 0.30))}
    picked = [df[df["fit"] == f].head(k) for f, k in want.items()]
    out = pd.concat(picked)
    if len(out) < n:  # a bucket ran short: fill with the next best of anything
        rest = df.drop(out.index)
        out = pd.concat([out, rest.head(n - len(out))])
    out = out.head(n)
    return out.sort_values("fit", key=lambda c: c.map(FIT_ORDER), kind="stable")
