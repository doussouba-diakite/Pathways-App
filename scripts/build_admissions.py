"""Build data/admissions.csv from IPEDS (U.S. Department of Education, public domain).

  IC<year>.zip   Institutional Characteristics: APPLFEEU = undergraduate application fee
  ADM<year>.zip  Admissions: ADMCON7 = how SAT/ACT scores are used
                 (1 required, 2 recommended, 5 considered but not required, 3 not considered)

Runs in GitHub Actions (.github/workflows/build-admissions.yml), tries the newest year first.
Prints ::warning:: lines so problems show up as annotations on the run.
"""
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "data" / "admissions.csv"
BASE = "https://nces.ed.gov/ipeds/datacenter/data/{name}.zip"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
TEST_POLICY = {1: "Required", 2: "Recommended", 5: "Optional", 3: "Not considered"}


def fetch(prefix: str) -> tuple[pd.DataFrame, str]:
    for year in range(2025, 2018, -1):
        url = BASE.format(name=f"{prefix}{year}")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
        except Exception as e:
            print(f"::warning::{prefix}{year}: {e}")
            continue
        csvs = sorted((n for n in z.namelist() if n.lower().endswith(".csv")), key=lambda n: "_rv" not in n.lower())
        df = pd.read_csv(z.open(csvs[0]), encoding="latin-1", low_memory=False)
        df.columns = [c.strip().upper() for c in df.columns]
        print(f"::warning::using {prefix}{year} ({csvs[0]}, {len(df)} rows)")
        return df, str(year)
    sys.exit(f"::error::no {prefix} file found")


def col(df: pd.DataFrame, *names: str, contains: str = "") -> pd.Series:
    """First matching column; reports what exists if none match."""
    for n in names:
        if n in df.columns:
            return pd.to_numeric(df[n], errors="coerce")
    near = [c for c in df.columns if contains and contains in c]
    print(f"::warning::none of {names} found; similar columns: {near[:30]}")
    return pd.Series(pd.NA, index=df.index, dtype="Float64")


ic, ic_year = fetch("IC")
adm, adm_year = fetch("ADM")
fee = col(ic, "APPLFEEU", "APPLFEEUG", "APPLFEE", contains="FEE")
out = pd.DataFrame({"unitid": ic["UNITID"], "app_fee": fee.where(fee >= 0)})
pol = pd.DataFrame({"unitid": adm["UNITID"],
                    "test_policy": col(adm, "ADMCON7", "ADMCON07", contains="ADMCON").map(TEST_POLICY)})
out = out.merge(pol, on="unitid", how="outer")
out["source_years"] = f"IC{ic_year}/ADM{adm_year}"
OUT.parent.mkdir(exist_ok=True)
out.to_csv(OUT, index=False)
print(f"::warning::wrote {len(out)} rows; fee known for {out['app_fee'].notna().sum()}, "
      f"test policy known for {out['test_policy'].notna().sum()}")
