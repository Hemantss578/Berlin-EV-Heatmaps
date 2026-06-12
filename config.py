"""Central configuration for the Berlin EV Charging Heatmaps project."""

import os

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "datasets")

FILE_GEODATA = os.path.join(DATA_DIR, "geodata_berlin_plz.csv")
FILE_CHARGING_XLSX = os.path.join(DATA_DIR, "Ladesaeulenregister_SEP.xlsx")
FILE_CHARGING_CSV = os.path.join(DATA_DIR, "Ladesaeulenregister.csv")
FILE_RESIDENTS = os.path.join(DATA_DIR, "plz_einwohner.csv")

# ---------------------------------------------------------------------------
# Map settings
# ---------------------------------------------------------------------------
BERLIN_CENTER = [52.52, 13.405]
DEFAULT_ZOOM = 10

# Berlin postal codes range from 10115 to 14199
BERLIN_PLZ_MIN = 10000
BERLIN_PLZ_MAX = 14200

# Crowdsourced user reports (malfunctions / new-station suggestions)
FILE_REPORTS = os.path.join(DATA_DIR, "user_reports.csv")

# Power bins (kW) for the layered nominal-power heatmap
POWER_BINS = [
    ("≤ 22 kW (AC normal)", 0, 22),
    ("23–49 kW (fast)", 22, 49),
    ("50–149 kW (DC fast)", 49, 149),
    ("≥ 150 kW (HPC ultra-fast)", 149, float("inf")),
]
