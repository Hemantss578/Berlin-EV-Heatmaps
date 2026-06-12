"""
core/methods.py
---------------
Data input, preprocessing, geospatial processing and visualisation
generation for the Berlin EV Charging Heatmaps project.
"""

import os

import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import HeatMap
from shapely import wkt
import branca.colormap as cm

import config


# ===========================================================================
# 1. Data input
# ===========================================================================

def load_geodata() -> gpd.GeoDataFrame:
    """Load Berlin postal-code polygons (PLZ; WKT geometry) into a GeoDataFrame."""
    df = pd.read_csv(config.FILE_GEODATA, sep=";", dtype={"PLZ": str})

    # Geometry column may be called 'geometry' or similar WKT text
    geom_col = "geometry" if "geometry" in df.columns else df.columns[-1]
    df["geometry"] = df[geom_col].apply(wkt.loads)

    gdf = gpd.GeoDataFrame(df[["PLZ", "geometry"]], geometry="geometry", crs="EPSG:4326")
    gdf["PLZ"] = gdf["PLZ"].astype(str).str.strip()

    # Geometry validation: drop invalid / empty geometries
    gdf = gdf[gdf.geometry.notna() & gdf.geometry.is_valid & ~gdf.geometry.is_empty]
    return gdf


def load_residents() -> pd.DataFrame:
    """Load resident counts per postal code and filter to Berlin."""
    df = pd.read_csv(config.FILE_RESIDENTS, dtype={"plz": str})

    # Normalise column names (file usually has: plz, einwohner [, lat, lon])
    df.columns = [c.strip().lower() for c in df.columns]
    plz_col = "plz"
    pop_col = "einwohner" if "einwohner" in df.columns else df.columns[1]

    df = df[[plz_col, pop_col]].rename(columns={plz_col: "PLZ", pop_col: "Einwohner"})
    df["PLZ"] = df["PLZ"].astype(str).str.strip()

    # Cleaning: drop invalid/missing entries
    df["Einwohner"] = pd.to_numeric(df["Einwohner"], errors="coerce")
    df = df.dropna(subset=["PLZ", "Einwohner"])
    df = df[df["Einwohner"] >= 0]

    # Filter for Berlin postal codes
    plz_num = pd.to_numeric(df["PLZ"], errors="coerce")
    df = df[(plz_num >= config.BERLIN_PLZ_MIN) & (plz_num < config.BERLIN_PLZ_MAX)]
    return df.reset_index(drop=True)


def _to_float(series: pd.Series) -> pd.Series:
    """Convert German-formatted numbers ('52,5213') to floats."""
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    cleaned = series.astype(str).str.strip()
    has_comma = cleaned.str.contains(",", na=False)
    # Only treat dots as thousands separators when a decimal comma is present
    german = cleaned.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    cleaned = german.where(has_comma, cleaned)
    return pd.to_numeric(cleaned, errors="coerce")


def _read_charging_csv(path: str) -> pd.DataFrame:
    """
    Read the BNetzA charging-register CSV robustly.

    The file is usually Windows-1252 (not UTF-8) encoded and has a variable
    number of metadata rows before the real header, so both the encoding and
    the header row are auto-detected.
    """
    encodings = ["utf-8-sig", "cp1252", "latin-1"]
    last_err = None

    for enc in encodings:
        try:
            # Peek at the first 30 lines to locate the header row
            with open(path, "r", encoding=enc) as f:
                head = [f.readline() for _ in range(30)]
            skip = next(
                (i for i, line in enumerate(head) if "postleitzahl" in line.lower()),
                0,
            )
            return pd.read_csv(
                path, sep=";", header=skip, encoding=enc,
                low_memory=False, on_bad_lines="skip",
            )
        except (UnicodeDecodeError, UnicodeError) as e:
            last_err = e
            continue

    raise UnicodeDecodeError(
        "all", b"", 0, 1,
        f"Could not decode {path} with any of {encodings}: {last_err}",
    )


def load_charging_stations() -> pd.DataFrame:
    """
    Load the Bundesnetzagentur charging-station register and filter to Berlin.

    Returns a DataFrame with columns: PLZ, Latitude, Longitude, KW.
    Prefers the .xlsx file; falls back to the .csv if not present.
    """
    if os.path.exists(config.FILE_CHARGING_XLSX):
        # BNetzA register ships with ~10 metadata rows before the header
        raw = pd.read_excel(config.FILE_CHARGING_XLSX, header=None)
        header_row = raw.index[
            raw.apply(lambda r: r.astype(str).str.contains("Postleitzahl", case=False).any(), axis=1)
        ]
        skip = int(header_row[0]) if len(header_row) else 0
        df = pd.read_excel(config.FILE_CHARGING_XLSX, header=skip)
    elif os.path.exists(config.FILE_CHARGING_CSV):
        df = _read_charging_csv(config.FILE_CHARGING_CSV)
    else:
        raise FileNotFoundError(
            "Neither Ladesaeulenregister_SEP.xlsx nor Ladesaeulenregister.csv "
            "was found in the datasets folder."
        )

    df.columns = [str(c).strip() for c in df.columns]

    def find_col(*keywords):
        for col in df.columns:
            if all(k.lower() in col.lower() for k in keywords):
                return col
        return None

    col_plz = find_col("postleitzahl")
    col_lat = find_col("breitengrad")
    col_lon = find_col("längengrad") or find_col("laengengrad")
    col_kw = find_col("nennleistung")

    df = df[[col_plz, col_lat, col_lon, col_kw]].copy()
    df.columns = ["PLZ", "Latitude", "Longitude", "KW"]

    # Standardise coordinates and power, clean invalid rows
    df["PLZ"] = df["PLZ"].astype(str).str.extract(r"(\d{5})")[0]
    df["Latitude"] = _to_float(df["Latitude"])
    df["Longitude"] = _to_float(df["Longitude"])
    df["KW"] = _to_float(df["KW"])
    df = df.dropna(subset=["PLZ", "Latitude", "Longitude"])

    # Filter for Berlin (by PLZ range and a coordinate sanity bound)
    plz_num = pd.to_numeric(df["PLZ"], errors="coerce")
    df = df[(plz_num >= config.BERLIN_PLZ_MIN) & (plz_num < config.BERLIN_PLZ_MAX)]
    df = df[df["Latitude"].between(52.3, 52.7) & df["Longitude"].between(13.0, 13.8)]
    return df.reset_index(drop=True)


# ===========================================================================
# 2. Geospatial processing
# ===========================================================================

def make_residents_gdf(gdf_geo: gpd.GeoDataFrame, df_res: pd.DataFrame) -> gpd.GeoDataFrame:
    """Merge population data with postal-code polygons."""
    gdf = gdf_geo.merge(df_res, on="PLZ", how="left")
    gdf["Einwohner"] = gdf["Einwohner"].fillna(0)
    return gdf


def make_stations_gdf(gdf_geo: gpd.GeoDataFrame, df_st: pd.DataFrame) -> gpd.GeoDataFrame:
    """Aggregate station counts per postal code and merge with polygons."""
    agg = (
        df_st.groupby("PLZ")
        .agg(Stationen=("PLZ", "size"), KW_gesamt=("KW", "sum"))
        .reset_index()
    )
    gdf = gdf_geo.merge(agg, on="PLZ", how="left")
    gdf["Stationen"] = gdf["Stationen"].fillna(0)
    gdf["KW_gesamt"] = gdf["KW_gesamt"].fillna(0)
    return gdf


# ===========================================================================
# 3. Visualisation generation
# ===========================================================================

def _base_map() -> folium.Map:
    return folium.Map(
        location=config.BERLIN_CENTER,
        zoom_start=config.DEFAULT_ZOOM,
        tiles="cartodbpositron",
    )


def map_residents(gdf: gpd.GeoDataFrame) -> folium.Map:
    """Choropleth of population density per PLZ (yellow → red)."""
    m = _base_map()

    colormap = cm.LinearColormap(
        colors=["#ffffcc", "#fd8d3c", "#bd0026"],
        vmin=gdf["Einwohner"].min(),
        vmax=gdf["Einwohner"].max(),
        caption="Residents per postal code",
    )

    folium.GeoJson(
        gdf,
        style_function=lambda f: {
            "fillColor": colormap(f["properties"]["Einwohner"]),
            "color": "#555",
            "weight": 0.7,
            "fillOpacity": 0.75,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["PLZ", "Einwohner"],
            aliases=["Postal code:", "Residents:"],
            localize=True,
        ),
        name="Residents",
    ).add_to(m)

    colormap.add_to(m)
    return m


def map_stations_choropleth(gdf: gpd.GeoDataFrame) -> folium.Map:
    """Choropleth of charging-station counts per PLZ."""
    m = _base_map()

    colormap = cm.LinearColormap(
        colors=["#e8f4f8", "#41b6c4", "#0c2c84"],
        vmin=gdf["Stationen"].min(),
        vmax=gdf["Stationen"].max(),
        caption="Charging stations per postal code",
    )

    folium.GeoJson(
        gdf,
        style_function=lambda f: {
            "fillColor": colormap(f["properties"]["Stationen"]),
            "color": "#555",
            "weight": 0.7,
            "fillOpacity": 0.75,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["PLZ", "Stationen", "KW_gesamt"],
            aliases=["Postal code:", "Charging stations:", "Total nominal power (kW):"],
            localize=True,
        ),
        name="Charging stations",
    ).add_to(m)

    colormap.add_to(m)
    return m


def map_stations_heatmap(df_st: pd.DataFrame) -> folium.Map:
    """Point-density heatmap of station locations, weighted by nominal power."""
    m = _base_map()
    weights = df_st["KW"].fillna(df_st["KW"].median()).clip(lower=1)
    heat_data = list(zip(df_st["Latitude"], df_st["Longitude"], weights))
    HeatMap(
        heat_data,
        radius=14,
        blur=18,
        max_zoom=14,
        gradient={"0.2": "yellow", "0.5": "orange", "0.8": "red", "1.0": "darkred"},
        name="Station density (kW-weighted)",
    ).add_to(m)
    return m


def map_stations_by_power(df_st: pd.DataFrame) -> folium.Map:
    """Layered heatmaps: one toggleable layer per nominal-power class."""
    m = _base_map()

    for label, lo, hi in config.POWER_BINS:
        subset = df_st[(df_st["KW"] > lo) & (df_st["KW"] <= hi)]
        if subset.empty:
            continue
        layer = folium.FeatureGroup(name=f"{label} — {len(subset)} stations")
        HeatMap(
            list(zip(subset["Latitude"], subset["Longitude"])),
            radius=13,
            blur=16,
            max_zoom=14,
        ).add_to(layer)
        layer.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m
