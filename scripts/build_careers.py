"""Build data/careers.csv from the O*NET database (public, CC BY 4.0).

Downloads the O*NET text release and joins three files:
  Occupation Data.txt   title + description
  Interests.txt         RIASEC scores (scale "OI", 1-7)
  Job Zones.txt         preparation level (1 little, 5 extensive)

Usage: python scripts/build_careers.py            (tries the newest release first)
       python scripts/build_careers.py db_30_3_text.zip
"""
import io
import sys
import urllib.request
import zipfile

import pandas as pd

VERSIONS = ["30_3", "30_2", "30_1", "30_0", "29_3", "29_2", "29_1", "29_0"]
URL = "https://www.onetcenter.org/dl_files/database/db_{v}_text.zip"
LETTER = {"Realistic": "R", "Investigative": "I", "Artistic": "A",
          "Social": "S", "Enterprising": "E", "Conventional": "C"}
ZONE = {1: "Little or no preparation", 2: "High school, some training", 3: "Training or associate degree",
        4: "Bachelor's degree", 5: "Graduate degree"}


HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/126.0 Safari/537.36 pathways-app-data-build",
           "Accept": "application/zip,*/*"}


def report(msg: str) -> None:
    """Print, and also surface as a GitHub Actions annotation when running in CI."""
    print(msg)
    print(f"::warning::{msg}")


def download() -> tuple[bytes, str]:
    for v in VERSIONS:
        try:
            req = urllib.request.Request(URL.format(v=v), headers=HEADERS)
            with urllib.request.urlopen(req, timeout=120) as r:
                blob = r.read()
            if not blob.startswith(b"PK"):
                report(f"O*NET {v}: response was not a zip ({blob[:80]!r})")
                continue
            return blob, v
        except Exception as e:  # try the next older release
            report(f"O*NET {v}: {type(e).__name__}: {e}")
    raise SystemExit("::error::Could not download any O*NET release.")


def read(z: zipfile.ZipFile, name: str) -> pd.DataFrame:
    path = next(n for n in z.namelist() if n.endswith("/" + name))
    return pd.read_csv(z.open(path), sep="\t", dtype=str)


def build(blob: bytes) -> pd.DataFrame:
    z = zipfile.ZipFile(io.BytesIO(blob))
    occ = read(z, "Occupation Data.txt")
    interests = read(z, "Interests.txt")
    zones = read(z, "Job Zones.txt")

    oi = interests[interests["Scale ID"] == "OI"].copy()
    oi["letter"] = oi["Element Name"].map(LETTER)
    oi["Data Value"] = pd.to_numeric(oi["Data Value"])
    riasec = oi.pivot_table(index="O*NET-SOC Code", columns="letter", values="Data Value")

    df = occ.set_index("O*NET-SOC Code")[["Title", "Description"]].join(riasec, how="inner")
    zones["Job Zone"] = pd.to_numeric(zones["Job Zone"])
    df = df.join(zones.set_index("O*NET-SOC Code")["Job Zone"])
    df = df.dropna(subset=list("RIASEC")).reset_index()
    df.columns = ["soc_code", "title", "description", *df.columns[3:]]
    df = df.rename(columns={"Job Zone": "job_zone"})
    df["preparation"] = df["job_zone"].map(ZONE)
    df["onet_url"] = "https://www.onetonline.org/link/summary/" + df["soc_code"]
    return df[["soc_code", "title", "description", *"RIASEC", "job_zone", "preparation", "onet_url"]]


if __name__ == "__main__":
    if len(sys.argv) > 1:
        blob, version = open(sys.argv[1], "rb").read(), sys.argv[1]
    else:
        blob, version = download()
    try:
        out = build(blob)
    except Exception as e:
        z = zipfile.ZipFile(io.BytesIO(blob))
        report(f"build failed: {type(e).__name__}: {e}; first files: {z.namelist()[:8]}")
        raise
    out.to_csv("data/careers.csv", index=False)
    print(f"wrote data/careers.csv: {len(out):,} careers from O*NET {version}")
