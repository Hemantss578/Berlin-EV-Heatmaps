"""
core/reports.py
---------------
Crowdsourcing layer: users can report malfunctioning charging stations
or suggest locations for new ones. Reports are persisted to a CSV file
(datasets/user_reports.csv) so they survive app restarts.
"""

import os
import uuid
from datetime import datetime, timezone

import pandas as pd
import folium

import config

REPORT_COLUMNS = [
    "id", "timestamp", "type", "plz", "latitude", "longitude",
    "description", "reporter", "status",
]

TYPE_MALFUNCTION = "malfunction"
TYPE_SUGGESTION = "suggestion"


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def load_reports() -> pd.DataFrame:
    """Load all user reports; returns an empty frame if none exist yet."""
    if not os.path.exists(config.FILE_REPORTS):
        return pd.DataFrame(columns=REPORT_COLUMNS)
    df = pd.read_csv(config.FILE_REPORTS, dtype={"plz": str})
    # Guard against manually edited / older files missing columns
    for col in REPORT_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[REPORT_COLUMNS]


def add_report(
    report_type: str,
    latitude: float,
    longitude: float,
    description: str,
    plz: str = "",
    reporter: str = "",
) -> dict:
    """Append a new report to the CSV store and return it as a dict."""
    if report_type not in (TYPE_MALFUNCTION, TYPE_SUGGESTION):
        raise ValueError(f"Unknown report type: {report_type}")
    if not description or not description.strip():
        raise ValueError("Description must not be empty.")
    if not (52.3 <= latitude <= 52.7 and 13.0 <= longitude <= 13.8):
        raise ValueError("Location must be within Berlin.")

    record = {
        "id": uuid.uuid4().hex[:8],
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "type": report_type,
        "plz": str(plz).strip(),
        "latitude": round(float(latitude), 6),
        "longitude": round(float(longitude), 6),
        "description": description.strip(),
        "reporter": reporter.strip() or "anonymous",
        "status": "open",
    }

    df = load_reports()
    df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
    os.makedirs(os.path.dirname(config.FILE_REPORTS), exist_ok=True)
    df.to_csv(config.FILE_REPORTS, index=False)
    return record


def report_counts_by_plz(df_reports: pd.DataFrame) -> pd.DataFrame:
    """Aggregate report counts per postal code and type (for gap analysis)."""
    if df_reports.empty:
        return pd.DataFrame(columns=["PLZ", "Malfunctions", "Suggestions"])
    pivot = (
        df_reports.pivot_table(
            index="plz", columns="type", values="id", aggfunc="count", fill_value=0
        )
        .reset_index()
        .rename(columns={
            "plz": "PLZ",
            TYPE_MALFUNCTION: "Malfunctions",
            TYPE_SUGGESTION: "Suggestions",
        })
    )
    for col in ("Malfunctions", "Suggestions"):
        if col not in pivot.columns:
            pivot[col] = 0
    return pivot


# ---------------------------------------------------------------------------
# Map layer
# ---------------------------------------------------------------------------

def add_reports_layer(fmap: folium.Map, df_reports: pd.DataFrame) -> folium.Map:
    """Add user reports as coloured markers: red = malfunction, green = suggestion."""
    if df_reports.empty:
        return fmap

    group = folium.FeatureGroup(name="Community reports")
    for _, r in df_reports.iterrows():
        is_malfunction = r["type"] == TYPE_MALFUNCTION
        folium.Marker(
            location=[r["latitude"], r["longitude"]],
            icon=folium.Icon(
                color="red" if is_malfunction else "green",
                icon="wrench" if is_malfunction else "plus",
                prefix="fa",
            ),
            popup=folium.Popup(
                f"<b>{'⚠️ Malfunction' if is_malfunction else '💡 New station suggestion'}</b><br>"
                f"{r['description']}<br>"
                f"<i>{r['timestamp']} · {r['reporter']} · status: {r['status']}</i>",
                max_width=300,
            ),
            tooltip="Malfunction report" if is_malfunction else "Station suggestion",
        ).add_to(group)
    group.add_to(fmap)
    return fmap
