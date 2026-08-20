"""\
Streamlit App — Berlin Smart Canopy

Pages:
1) Urban Canopy Dashboard
   - Choropleth: emissions by PLZ
   - Tree layer: heatmap or clustered points
2) ML Planting Simulator
   - Select a high-priority PLZ
   - Add virtual plantings by species
   - Predict 2050 annual absorption; show net footprint curve

Run:
    streamlit run berlin_smart_canopy/app.py

Prerequisites:
    python berlin_smart_canopy/data_generator.py
    python berlin_smart_canopy/ml_engine.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import geopandas as gpd
import joblib

import streamlit as st
import folium
from folium.plugins import MarkerCluster, HeatMap
from streamlit_folium import st_folium
import altair as alt


# ---------------------------------------------------------------------------
# Streamlit configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Berlin Smart Canopy",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Paths (relative to this app file)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "data" / "models"

RAW_TREES_CSV = DATA_RAW / "baumbestand_berlin.csv"
RAW_EMISSIONS_CSV = DATA_RAW / "berlin_emissions_plz.csv"
RAW_PLZ_GEOJSON = DATA_RAW / "berlin_plz.geojson"

PLZ_FEATURES_GEOJSON = DATA_PROCESSED / "plz_features.geojson"
TREES_ENRICHED_PARQUET = DATA_PROCESSED / "trees_enriched.parquet"

KMEANS_PIPELINE_PATH = MODELS_DIR / "kmeans_plz_pipeline.joblib"
RF_PIPELINE_PATH = MODELS_DIR / "rf_2050_pipeline.joblib"
METADATA_PATH = MODELS_DIR / "model_metadata.joblib"


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _missing_artifacts() -> list[str]:
    required = [
        RAW_TREES_CSV,
        RAW_EMISSIONS_CSV,
        RAW_PLZ_GEOJSON,
        PLZ_FEATURES_GEOJSON,
        TREES_ENRICHED_PARQUET,
        KMEANS_PIPELINE_PATH,
        RF_PIPELINE_PATH,
        METADATA_PATH,
    ]
    return [str(p) for p in required if not p.exists()]


def _fmt_tons(x: float) -> str:
    return f"{x:,.0f} t"


def _fmt_tons_precise(x: float) -> str:
    return f"{x:,.2f} t"


# ---------------------------------------------------------------------------
# Cached loaders
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_plz_features_geo() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(PLZ_FEATURES_GEOJSON)
    # Enforce EPSG:4326
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326", allow_override=True)
    else:
        gdf = gdf.to_crs("EPSG:4326")
    gdf["PLZ"] = gdf["PLZ"].astype(str)
    return gdf


@st.cache_data(show_spinner=False)
def load_trees_enriched() -> pd.DataFrame:
    df = pd.read_parquet(TREES_ENRICHED_PARQUET)
    df["PLZ"] = df["PLZ"].astype(str)
    return df


@st.cache_resource(show_spinner=False)
def load_models() -> Tuple[object, object, dict]:
    kmeans_pipeline = joblib.load(KMEANS_PIPELINE_PATH)
    rf_pipeline = joblib.load(RF_PIPELINE_PATH)
    metadata = joblib.load(METADATA_PATH)
    return kmeans_pipeline, rf_pipeline, metadata


# ---------------------------------------------------------------------------
# Simulator helpers
# ---------------------------------------------------------------------------

def build_scenario_features(plz_row: pd.Series, plantings: Dict[str, int], metadata: dict) -> pd.DataFrame:
    """Build a single-row feature matrix matching training schema."""
    rf_cols = list(metadata["rf_feature_cols"])
    species_cols = list(metadata["species_cols"])

    row: Dict[str, float] = {}

    # Base features
    for c in rf_cols:
        if c.startswith("plant_"):
            continue
        v = plz_row.get(c, 0.0)
        try:
            row[c] = float(v)
        except Exception:
            row[c] = 0.0

    # Plantings
    for sp in species_cols:
        row[f"plant_{sp}"] = float(max(int(plantings.get(sp, 0)), 0))

    # Ensure exact column order + numeric
    return pd.DataFrame([{c: float(row.get(c, 0.0)) for c in rf_cols}])


def make_projection_curve(
    current_year: int,
    current_absorption_tons: float,
    predicted_2050_absorption_tons: float,
    horizon_year: int = 2050,
) -> pd.DataFrame:
    """Visualization-only curve between current and 2050 (saturating interpolation)."""
    years = np.arange(current_year, horizon_year + 1)
    t = (years - current_year) / max(horizon_year - current_year, 1)

    curve = (1 - np.exp(-3.2 * t)) / (1 - np.exp(-3.2))
    absorption = current_absorption_tons + curve * (predicted_2050_absorption_tons - current_absorption_tons)

    return pd.DataFrame({"year": years, "absorption_tons": absorption})


# ---------------------------------------------------------------------------
# App shell
# ---------------------------------------------------------------------------

st.title("Berlin Smart Canopy: Urban Carbon Sequestration & ML Optimization")
st.caption(
    "Demo implementation using synthetic Berlin-like datasets (EPSG:4326). "
    "Replace synthetic inputs with Berlin Open Data exports when ready."
)

missing = _missing_artifacts()
if missing:
    st.error("Required data/model artifacts are missing.")
    st.code(
        "python berlin_smart_canopy/data_generator.py\n"
        "python berlin_smart_canopy/ml_engine.py\n"
        "streamlit run berlin_smart_canopy/app.py\n",
        language="bash",
    )
    with st.expander("Missing files"):
        st.write(missing)
    st.stop()

plz_gdf = load_plz_features_geo()
trees_df = load_trees_enriched()
_, rf_pipeline, metadata = load_models()

current_year = int(metadata.get("current_year", pd.Timestamp.today().year))


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.header("Berlin Smart Canopy")
page = st.sidebar.radio(
    "Navigate",
    options=["Urban Canopy Dashboard", "ML Planting Simulator"],
    index=0,
)

st.sidebar.divider()

st.sidebar.subheader("Map rendering")
tree_render_mode = st.sidebar.selectbox(
    "Tree layer style",
    ["Heatmap (fast)", "Clustered points (slower)"],
    index=0,
)

max_tree_points = st.sidebar.slider(
    "Max trees to render (sampling for performance)",
    min_value=500,
    max_value=30000,
    value=8000,
    step=500,
)

# Sample only for map layers (metrics use full dataset)
trees_render = trees_df
if len(trees_render) > max_tree_points:
    trees_render = trees_render.sample(max_tree_points, random_state=42)


# ---------------------------------------------------------------------------
# Page 1: Dashboard
# ---------------------------------------------------------------------------

if page == "Urban Canopy Dashboard":
    st.subheader("Urban Canopy Dashboard")

    total_emissions = float(plz_gdf["total_co2_tons"].fillna(0).sum())
    total_absorption = float(plz_gdf["total_canopy_co2_absorption_tons"].fillna(0).sum())
    net = total_emissions - total_absorption

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Annual emissions (sum PLZ)", _fmt_tons(total_emissions))
    c2.metric("Annual canopy absorption (proxy)", _fmt_tons_precise(total_absorption))
    c3.metric("Net annual footprint", _fmt_tons_precise(net))
    c4.metric("Trees in inventory", f"{len(trees_df):,}")

    st.divider()

    # Map
    berlin_center = [52.5200, 13.4050]
    m = folium.Map(location=berlin_center, zoom_start=10.6, tiles="CartoDB positron", control_scale=True)

    # Emissions choropleth
    folium.Choropleth(
        geo_data=plz_gdf.to_json(),
        name="CO₂ emissions (tons/year)",
        data=plz_gdf[["PLZ", "total_co2_tons"]],
        columns=["PLZ", "total_co2_tons"],
        key_on="feature.properties.PLZ",
        fill_color="YlOrRd",
        fill_opacity=0.75,
        line_opacity=0.25,
        nan_fill_opacity=0.1,
        legend_name="Total CO₂ emissions (tons/year)",
    ).add_to(m)

    # PLZ outline + tooltip
    folium.GeoJson(
        plz_gdf,
        name="PLZ boundaries",
        style_function=lambda _: {"color": "#2f2f2f", "weight": 1, "fillOpacity": 0},
        tooltip=folium.GeoJsonTooltip(
            fields=[
                "PLZ",
                "total_co2_tons",
                "sealed_surface_ratio",
                "total_canopy_co2_absorption_tons",
                "priority_rank",
            ],
            aliases=[
                "PLZ",
                "Emissions (t/yr)",
                "Sealed surface ratio",
                "Canopy absorption (t/yr)",
                "Priority rank",
            ],
            localize=True,
            sticky=False,
        ),
    ).add_to(m)

    # Tree layer
    if tree_render_mode.startswith("Heatmap"):
        weights = trees_render["annual_sequestration_kg"].clip(0.2, 50.0).to_numpy()
        heat_data = [
            [float(lat), float(lon), float(w)]
            for lat, lon, w in zip(trees_render["latitude"], trees_render["longitude"], weights)
        ]
        HeatMap(heat_data, name="Trees (heatmap)", radius=12, blur=14, min_opacity=0.25).add_to(m)
    else:
        cluster = MarkerCluster(name="Trees (clustered points)")
        for _, r in trees_render.iterrows():
            folium.CircleMarker(
                location=[float(r["latitude"]), float(r["longitude"])],
                radius=2,
                weight=0,
                fill=True,
                fill_opacity=0.75,
                color="#2E7D32",
                popup=folium.Popup(
                    f"Species: {r['species']}<br>"
                    f"Age: {int(r['tree_age_years'])} years<br>"
                    f"Annual: {float(r['annual_sequestration_kg']):.2f} kg/yr<br>"
                    f"PLZ: {r['PLZ']}",
                    max_width=320,
                ),
            ).add_to(cluster)
        cluster.add_to(m)

    folium.LayerControl(collapsed=True).add_to(m)

    st.markdown("#### Interactive map")
    st_folium(m, height=640, use_container_width=True)

    st.markdown("#### High-Priority Planting Zones (Top 10)")
    top = (
        plz_gdf.drop(columns="geometry")
        .sort_values(["priority_rank", "PLZ"])
        .head(10)[
            [
                "PLZ",
                "priority_rank",
                "cluster_label",
                "total_co2_tons",
                "sealed_surface_ratio",
                "total_canopy_co2_absorption_tons",
                "tree_count",
            ]
        ]
    )
    st.dataframe(top, use_container_width=True, hide_index=True)

    with st.expander("Interpretation notes"):
        st.write(
            "- Priority rank is a composite indicator: high emissions + high sealing − high canopy absorption.\n"
            "- Tree sequestration is computed via proxy allometric equations (replace with validated city forestry models for real policy use)."
        )


# ---------------------------------------------------------------------------
# Page 2: Simulator
# ---------------------------------------------------------------------------

else:
    st.subheader("ML Planting Simulator")
    st.write(
        "Select a PLZ and simulate new tree plantings. The model predicts **2050 annual canopy absorption** "
        "under your planting scenario and visualizes how the district net footprint could change over time."
    )

    plz_table = plz_gdf.drop(columns="geometry").copy().sort_values(["priority_rank", "PLZ"])

    left, right = st.columns([0.38, 0.62], vertical_alignment="top")

    with left:
        st.markdown("### 1) Select target district")
        selected_plz = st.selectbox("PLZ", options=plz_table["PLZ"].astype(str).tolist(), index=0)

        sel = plz_table.loc[plz_table["PLZ"].astype(str) == str(selected_plz)].iloc[0]

        st.markdown("### 2) Current snapshot")
        a, b = st.columns(2)
        a.metric("Priority rank", int(sel["priority_rank"]))
        b.metric("Cluster", int(sel["cluster_label"]))

        c, d = st.columns(2)
        c.metric("Emissions (t/yr)", _fmt_tons(float(sel["total_co2_tons"])))
        d.metric("Absorption (t/yr)", _fmt_tons_precise(float(sel["total_canopy_co2_absorption_tons"])))

        e, f = st.columns(2)
        e.metric("Sealed ratio", f"{float(sel['sealed_surface_ratio']):.2f}")
        f.metric("Tree count", f"{int(sel['tree_count']):,}")

        st.divider()
        st.markdown("### 3) Virtual planting plan")

        plantings: Dict[str, int] = {}
        for sp in metadata["species_cols"]:
            plantings[sp] = st.slider(
                f"Plant {sp}",
                min_value=0,
                max_value=12000,
                value=0,
                step=250,
            )

        st.caption("This is a demo planning tool. For production, enforce area/soil/utility constraints per PLZ.")

    with right:
        st.markdown("### 2050 prediction and trajectory")

        try:
            X = build_scenario_features(sel, plantings, metadata)
            pred_2050_abs = float(rf_pipeline.predict(X)[0])
        except Exception as ex:
            st.error("Prediction failed (schema mismatch or corrupted model artifacts).")
            st.exception(ex)
            st.stop()

        current_abs = float(sel["total_canopy_co2_absorption_tons"])
        emissions = float(sel["total_co2_tons"])

        proj = make_projection_curve(
            current_year=current_year,
            current_absorption_tons=current_abs,
            predicted_2050_absorption_tons=pred_2050_abs,
            horizon_year=2050,
        )
        proj["emissions_tons"] = emissions
        proj["net_footprint_tons"] = proj["emissions_tons"] - proj["absorption_tons"]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Absorption now", _fmt_tons_precise(current_abs))
        m2.metric("Predicted absorption (2050)", _fmt_tons_precise(pred_2050_abs))
        m3.metric("Net now", _fmt_tons_precise(emissions - current_abs))
        m4.metric("Net (2050)", _fmt_tons_precise(emissions - pred_2050_abs))

        st.markdown("#### Net footprint (tons/year) = emissions − canopy absorption")
        chart_net = (
            alt.Chart(proj)
            .mark_line(strokeWidth=3)
            .encode(
                x=alt.X("year:Q", title="Year"),
                y=alt.Y("net_footprint_tons:Q", title="Net footprint (tons/year)"),
                tooltip=[
                    "year:Q",
                    alt.Tooltip("absorption_tons:Q", format=",.2f"),
                    alt.Tooltip("net_footprint_tons:Q", format=",.2f"),
                ],
            )
            .properties(height=300)
        )
        st.altair_chart(chart_net, use_container_width=True)

        st.markdown("#### Canopy absorption trajectory (tons/year)")
        chart_abs = (
            alt.Chart(proj)
            .mark_area(opacity=0.25)
            .encode(
                x=alt.X("year:Q", title="Year"),
                y=alt.Y("absorption_tons:Q", title="Canopy absorption (tons/year)"),
                tooltip=["year:Q", alt.Tooltip("absorption_tons:Q", format=",.2f")],
            )
            .properties(height=260)
        )
        st.altair_chart(chart_abs, use_container_width=True)

        with st.expander("Modeling notes"):
            st.write(
                "- The RandomForest predicts **2050 annual absorption** for the given planting plan.\n"
                "- Intermediate years are interpolated for visualization (not a second model).\n"
                "- Emissions are held constant here; add an emissions scenario model to project decarbonization pathways."
            )

        with st.expander("Debug: model input features"):
            st.dataframe(X, use_container_width=True, hide_index=True)
