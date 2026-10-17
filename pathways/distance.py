"""Distance from home: ZIP code -> coordinates -> miles to each college.

ZIP coordinates come from the `zipcodes` package, which ships the data offline
(no API calls, nothing about the student leaves the app). College coordinates
come from the College Scorecard (LATITUDE / LONGITUDE).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

EARTH_MILES = 3958.8


def zip_location(zip_code: str) -> tuple[float, float, str] | None:
    """(lat, lon, 'City, ST') for a 5-digit US ZIP, or None if unknown."""
    z = (zip_code or "").strip()[:5]
    if len(z) != 5 or not z.isdigit():
        return None
    import zipcodes
    hits = zipcodes.matching(z)
    if not hits:
        return None
    h = hits[0]
    return float(h["lat"]), float(h["long"]), f"{h['city'].title()}, {h['state']}"


def miles(lat: float, lon: float, lats, lons) -> np.ndarray:
    """Great-circle distance in miles from one point to many (haversine)."""
    p1, p2 = math.radians(lat), np.radians(np.asarray(lats, dtype=float))
    dphi = p2 - p1
    dl = np.radians(np.asarray(lons, dtype=float)) - math.radians(lon)
    a = np.sin(dphi / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_MILES * np.arcsin(np.sqrt(a))


def add_miles(df: pd.DataFrame, home: tuple[float, float] | None) -> pd.DataFrame:
    out = df.copy()
    out["miles"] = miles(home[0], home[1], out["lat"], out["lon"]).round(1) if home else np.nan
    return out
