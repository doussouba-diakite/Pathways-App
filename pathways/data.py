"""Load the datasets built by scripts/ (see README for sources)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load_colleges(path: Path | None = None) -> pd.DataFrame:
    return pd.read_csv(path or DATA / "colleges.csv")


def load_careers(path: Path | None = None) -> pd.DataFrame:
    """Real O*NET data if it has been built, otherwise the small test sample."""
    p = path or DATA / "careers.csv"
    if not p.exists():
        p = ROOT / "tests" / "fixtures" / "careers_sample.csv"
    return pd.read_csv(p)


def careers_are_sample(path: Path | None = None) -> bool:
    return not (path or DATA / "careers.csv").exists()
