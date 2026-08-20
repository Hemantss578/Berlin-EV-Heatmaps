"""
One-time data-prep script: trims the national Bundesnetzagentur charging-
station register down to just the Berlin rows.

Why this exists: datasets/Ladesaeulenregister.csv as downloaded from BNetzA
covers all of Germany (~130k+ rows, tens of MB). core/methods.py already
filters this down to Berlin in memory on every app run -- but that means the
*full* national file has to exist on disk first, which is too large to
comfortably commit to a public GitHub repo (close to GitHub's 100MB
per-file limit) and is required for a hosted deploy, since Streamlit
Community Cloud only has whatever files are in the repo -- there's no
separate file-upload step at deploy time.

This script does the same Berlin filtering once, offline, and overwrites
the CSV with just the rows the app actually uses. It keeps the exact same
column names/format as the original register, so core/methods.py needs no
code changes -- it can't tell the difference between the full file and the
trimmed one.

Run once, from the project root (after `pip install -r requirements.txt`):
    python scripts/prepare_berlin_data.py

Then commit the (now much smaller) datasets/Ladesaeulenregister.csv.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
from core.methods import _read_charging_csv, _to_float


def main():
    src = config.FILE_CHARGING_CSV
    if not Path(src).exists():
        raise SystemExit(
            f"{src} not found. Download it first (see README -> Setup) "
            "before running this script."
        )

    print(f"Reading {src} ...")
    df = _read_charging_csv(src)
    df.columns = [str(c).strip() for c in df.columns]
    before = len(df)

    def find_col(*keywords):
        for col in df.columns:
            if all(k.lower() in col.lower() for k in keywords):
                return col
        return None

    col_plz = find_col("postleitzahl")
    col_lat = find_col("breitengrad")
    col_lon = find_col("längengrad") or find_col("laengengrad")
    if not col_plz or not col_lat or not col_lon:
        raise SystemExit(
            "Could not locate the Postleitzahl/Breitengrad/Längengrad "
            "columns -- the register's column names may have changed "
            "upstream. Aborting without touching the file."
        )

    plz_num = pd.to_numeric(
        df[col_plz].astype(str).str.extract(r"(\d{5})")[0], errors="coerce"
    )
    lat = _to_float(df[col_lat])
    lon = _to_float(df[col_lon])

    # Same Berlin filter core/methods.py applies at load time (PLZ range +
    # a coordinate sanity bound), just run once here instead of every load.
    mask = (
        (plz_num >= config.BERLIN_PLZ_MIN)
        & (plz_num < config.BERLIN_PLZ_MAX)
        & lat.between(52.3, 52.7)
        & lon.between(13.0, 13.8)
    )
    berlin = df[mask]

    if berlin.empty:
        raise SystemExit(
            "Filtering produced 0 Berlin rows -- something's off (column "
            "detection or filter bounds). Aborting without touching the file."
        )

    print(f"Filtered {before:,} national rows -> {len(berlin):,} Berlin rows.")
    berlin.to_csv(src, sep=";", index=False, encoding="utf-8-sig")
    print(f"Overwrote {src} with the Berlin-only subset.")
    print("Next: git add datasets/Ladesaeulenregister.csv, commit, and push.")


if __name__ == "__main__":
    main()
