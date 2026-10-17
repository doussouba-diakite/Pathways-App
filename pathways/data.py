"""Load the datasets built by scripts/ (see README for sources)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load_colleges(path: Path | None = None) -> pd.DataFrame:
    """College Scorecard data, plus IPEDS application fees and SAT/ACT policy when they've been built."""
    df = pd.read_csv(path or DATA / "colleges.csv")
    adm = DATA / "admissions.csv"
    if path is None and adm.exists():
        extra = pd.read_csv(adm)
        keep = ["unitid", "app_fee", "test_policy"] + [c for c in ("active", "closed_date") if c in extra.columns]
        df = df.merge(extra[keep], on="unitid", how="left")
        if "active" in df.columns:  # drop colleges the federal directory lists as closed
            df = df[df["active"].map({False: False, "False": False}).fillna(True).astype(bool)]
    for c in ("app_fee", "test_policy"):
        if c not in df.columns:
            df[c] = pd.NA
    return df


def load_careers(path: Path | None = None) -> pd.DataFrame:
    """Real O*NET data if it has been built, otherwise the small test sample."""
    p = path or DATA / "careers.csv"
    if not p.exists():
        p = ROOT / "tests" / "fixtures" / "careers_sample.csv"
    return pd.read_csv(p)


def careers_are_sample(path: Path | None = None) -> bool:
    return not (path or DATA / "careers.csv").exists()
