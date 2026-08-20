"""\
ML + feature engineering engine for "Berlin Smart Canopy".

What this script does:
1) Loads raw datasets from berlin_smart_canopy/data/raw
2) Engineers botanical proxy features:
   - tree_age_years = current_year - planting_year
   - annual_sequestration_kg (proxy allometric function using age, trunk diameter, species factor)
   - current_storage_kg (simple cumulative proxy)
3) Aggregates by PLZ and joins to emissions.
4) Trains:
   - Model A (unsupervised): KMeans on [total_co2_tons, sealed_surface_ratio, total_canopy_co2_absorption_tons]
   - Model B (supervised): RandomForest regressor predicting 2050 absorption given current conditions + a planting plan
5) Saves processed datasets and trained models.

Geospatial:
- EPSG:4326 throughout.

Usage:
    python ml_engine.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple, List
import math

import numpy as np
import pandas as pd
import geopandas as gpd
import joblib

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error


@dataclass(frozen=True)
class Paths:
    project_root: Path = Path(__file__).resolve().parent

    data_raw: Path = project_root / "data" / "raw"
    data_processed: Path = project_root / "data" / "processed"
    models_dir: Path = project_root / "data" / "models"

    trees_csv: Path = data_raw / "baumbestand_berlin.csv"
    emissions_csv: Path = data_raw / "berlin_emissions_plz.csv"
    plz_geojson: Path = data_raw / "berlin_plz.geojson"

    trees_enriched_parquet: Path = data_processed / "trees_enriched.parquet"
    plz_features_geojson: Path = data_processed / "plz_features.geojson"

    kmeans_pipeline_path: Path = models_dir / "kmeans_plz_pipeline.joblib"
    rf_pipeline_path: Path = models_dir / "rf_2050_pipeline.joblib"
    metadata_path: Path = models_dir / "model_metadata.joblib"


def _ensure_dirs(paths: Paths) -> None:
    paths.data_processed.mkdir(parents=True, exist_ok=True)
    paths.models_dir.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Botanical proxy equations
# ---------------------------------------------------------------------------
SPECIES_GROWTH_FACTOR: Dict[str, float] = {
    # Proxy idea: slower growers can still be high-storage due to biomass/wood density
    "Quercus (Eiche)": 1.25,
    "Tilia (Linde)": 1.05,
    "Acer (Ahorn)": 0.95,
    "Platanus": 1.10,
    "Betula": 0.85,
    "Fraxinus": 1.00,
}


def estimate_annual_sequestration_kg(
    species: pd.Series,
    trunk_diameter_cm: pd.Series,
    age_years: pd.Series,
) -> pd.Series:
    """Return kg CO2/year per tree (proxy, not a botanical truth model)."""
    s_factor = species.map(SPECIES_GROWTH_FACTOR).fillna(0.9).astype(float)

    age = age_years.clip(lower=1).astype(float)
    # Saturating response with age (urban growth constraints)
    age_term = 1.0 - np.exp(-age / 18.0)

    d = trunk_diameter_cm.clip(lower=2.0, upper=160.0).astype(float)
    diam_term = d**1.35

    annual_kg = 0.045 * s_factor * age_term * diam_term
    return annual_kg.clip(lower=0.2, upper=120.0)


def estimate_current_storage_kg(annual_kg: pd.Series, age_years: pd.Series) -> pd.Series:
    """Simple cumulative proxy (kg CO2 stored)."""
    age = age_years.clip(lower=1).astype(float)
    return (0.55 * annual_kg * age).clip(lower=1.0)


def enrich_trees(trees_df: pd.DataFrame, current_year: int) -> pd.DataFrame:
    df = trees_df.copy()

    df["PLZ"] = df["PLZ"].astype(str)
    df["planting_year"] = pd.to_numeric(df["planting_year"], errors="coerce")
    df["trunk_diameter_cm"] = pd.to_numeric(df["trunk_diameter_cm"], errors="coerce")
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    df = df.dropna(
        subset=["tree_id", "species", "planting_year", "trunk_diameter_cm", "latitude", "longitude", "PLZ"]
    ).copy()

    df["tree_age_years"] = (current_year - df["planting_year"].astype(int)).clip(lower=1)

    df["annual_sequestration_kg"] = estimate_annual_sequestration_kg(
        df["species"], df["trunk_diameter_cm"], df["tree_age_years"]
    )
    df["current_storage_kg"] = estimate_current_storage_kg(df["annual_sequestration_kg"], df["tree_age_years"])

    return df


def build_plz_features(trees_enriched: pd.DataFrame, emissions_df: pd.DataFrame) -> pd.DataFrame:
    trees_enriched = trees_enriched.copy()
    emissions_df = emissions_df.copy()

    trees_enriched["PLZ"] = trees_enriched["PLZ"].astype(str)
    emissions_df["PLZ"] = emissions_df["PLZ"].astype(str)

    canopy_agg = (
        trees_enriched.groupby("PLZ", as_index=False)
        .agg(
            total_canopy_co2_absorption_tons=("annual_sequestration_kg", lambda s: float(s.sum()) / 1000.0),
            total_current_storage_tons=("current_storage_kg", lambda s: float(s.sum()) / 1000.0),
            tree_count=("tree_id", "count"),
            mean_tree_age=("tree_age_years", "mean"),
            mean_trunk_diameter_cm=("trunk_diameter_cm", "mean"),
        )
    )

    species_counts = (
        trees_enriched.pivot_table(
            index="PLZ",
            columns="species",
            values="tree_id",
            aggfunc="count",
            fill_value=0,
        )
        .reset_index()
    )
    species_counts.columns = [str(c) for c in species_counts.columns]

    plz_features = (
        emissions_df.merge(canopy_agg, on="PLZ", how="left")
        .merge(species_counts, on="PLZ", how="left")
        .fillna(
            {
                "total_canopy_co2_absorption_tons": 0.0,
                "total_current_storage_tons": 0.0,
                "tree_count": 0,
                "mean_tree_age": 0.0,
                "mean_trunk_diameter_cm": 0.0,
            }
        )
    )

    # Ensure consistent species columns
    for sp in SPECIES_GROWTH_FACTOR.keys():
        if sp not in plz_features.columns:
            plz_features[sp] = 0

    return plz_features


# ---------------------------------------------------------------------------
# Model A: Unsupervised clustering
# ---------------------------------------------------------------------------

def train_kmeans(plz_features: pd.DataFrame, n_clusters: int = 4) -> Tuple[Pipeline, List[str]]:
    feature_cols = ["total_co2_tons", "sealed_surface_ratio", "total_canopy_co2_absorption_tons"]

    X = plz_features[feature_cols].astype(float)

    pipe = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("kmeans", KMeans(n_clusters=n_clusters, n_init="auto", random_state=42)),
        ]
    )
    pipe.fit(X)
    return pipe, feature_cols


def compute_priority_score(plz_features: pd.DataFrame) -> pd.Series:
    cols = ["total_co2_tons", "sealed_surface_ratio", "total_canopy_co2_absorption_tons"]
    z = {}
    for c in cols:
        v = plz_features[c].astype(float)
        z[c] = (v - v.mean()) / (v.std(ddof=0) + 1e-9)

    # Higher emissions + higher sealed surface => higher priority; more canopy => lower priority
    return z["total_co2_tons"] + 0.8 * z["sealed_surface_ratio"] - 1.0 * z["total_canopy_co2_absorption_tons"]


# ---------------------------------------------------------------------------
# Model B: Supervised regression (predict 2050 absorption under planting plan)
# ---------------------------------------------------------------------------

def _annual_kg_per_new_tree_at_age(species: str, age_years: int) -> float:
    s_factor = SPECIES_GROWTH_FACTOR.get(species, 0.9)
    age_term = 1.0 - math.exp(-max(age_years, 1) / 18.0)

    # Rough diameter-from-age proxy (for new trees)
    diam_cm = min(55.0, 8.0 + (age_years**0.75) * 1.6 * s_factor)
    annual_kg = 0.045 * s_factor * age_term * (diam_cm**1.35)
    return float(np.clip(annual_kg, 0.2, 120.0))


def _simulate_2050_target(plz_row: pd.Series, plantings: Dict[str, int], current_year: int, target_year: int = 2050) -> float:
    base_abs = float(plz_row["total_canopy_co2_absorption_tons"])
    years = max(target_year - current_year, 1)

    # Baseline canopy evolution (proxy, saturating)
    baseline_multiplier = 1.0 + 0.22 * (1.0 - math.exp(-years / 18.0))
    baseline_2050 = base_abs * baseline_multiplier

    added_tons = 0.0
    for sp, n in plantings.items():
        per_tree_kg = _annual_kg_per_new_tree_at_age(sp, years)
        added_tons += (per_tree_kg * max(int(n), 0)) / 1000.0

    # Noise for realism
    noise = np.random.default_rng(42).normal(0, 0.04 * max(baseline_2050 + added_tons, 1.0))
    return float(max(0.0, baseline_2050 + added_tons + noise))


def build_regression_training_set(
    plz_features: pd.DataFrame,
    current_year: int,
    scenarios_per_plz: int = 18,
) -> Tuple[pd.DataFrame, pd.Series, List[str]]:
    rng = np.random.default_rng(123)

    species_cols = list(SPECIES_GROWTH_FACTOR.keys())
    base_cols = [
        "total_co2_tons",
        "population_density",
        "sealed_surface_ratio",
        "total_canopy_co2_absorption_tons",
        "tree_count",
        "mean_tree_age",
        "mean_trunk_diameter_cm",
        *species_cols,
    ]

    rows: list[dict] = []
    y: list[float] = []

    for _, plz_row in plz_features.iterrows():
        for _ in range(scenarios_per_plz):
            # Intervention intensity linked to "need" (sealed + emissions)
            intensity = (
                0.6 * float(plz_row["sealed_surface_ratio"])
                + 0.4 * (float(plz_row["total_co2_tons"]) / (plz_features["total_co2_tons"].max() + 1e-9))
            )
            intensity = float(np.clip(intensity, 0.1, 1.0))

            plantings: Dict[str, int] = {}
            for sp in species_cols:
                plantings[sp] = int(rng.integers(0, int(8000 * intensity) + 1))

            x = plz_row[base_cols].to_dict()
            for sp in species_cols:
                x[f"plant_{sp}"] = float(plantings[sp])

            target = _simulate_2050_target(plz_row, plantings, current_year=current_year, target_year=2050)
            rows.append(x)
            y.append(target)

    X = pd.DataFrame(rows)
    y_ser = pd.Series(y, name="target_2050_absorption_tons")
    feature_cols = list(X.columns)
    return X, y_ser, feature_cols


def train_rf(X: pd.DataFrame, y: pd.Series) -> Pipeline:
    numeric_features = list(X.columns)

    pre = ColumnTransformer(
        transformers=[("num", "passthrough", numeric_features)],
        remainder="drop",
        verbose_feature_names_out=False,
    )

    rf = RandomForestRegressor(
        n_estimators=450,
        random_state=42,
        max_depth=14,
        min_samples_leaf=2,
        n_jobs=-1,
    )

    pipe = Pipeline(steps=[("pre", pre), ("rf", rf)])
    pipe.fit(X, y)
    return pipe


def main() -> None:
    paths = Paths()
    _ensure_dirs(paths)

    required = [paths.trees_csv, paths.emissions_csv, paths.plz_geojson]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing raw dataset(s). Run data_generator.py first or place real data in berlin_smart_canopy/data/raw.\n"
            + "\n".join(missing)
        )

    current_year = int(pd.Timestamp.today().year)

    trees_df = pd.read_csv(paths.trees_csv)
    emissions_df = pd.read_csv(paths.emissions_csv)
    plz_gdf = gpd.read_file(paths.plz_geojson)

    # Enrich & persist trees
    trees_enriched = enrich_trees(trees_df, current_year=current_year)
    trees_enriched.to_parquet(paths.trees_enriched_parquet, index=False)

    # PLZ features
    plz_features = build_plz_features(trees_enriched, emissions_df)

    # Model A
    kmeans_pipe, kmeans_feature_cols = train_kmeans(plz_features, n_clusters=4)
    plz_features["cluster_label"] = kmeans_pipe.predict(plz_features[kmeans_feature_cols].astype(float))
    plz_features["priority_score"] = compute_priority_score(plz_features)
    plz_features["priority_rank"] = plz_features["priority_score"].rank(ascending=False, method="dense").astype(int)

    # Geo-join for mapping
    plz_gdf["PLZ"] = plz_gdf["PLZ"].astype(str)
    plz_geo = plz_gdf.merge(plz_features, on="PLZ", how="left")
    plz_geo = plz_geo.set_crs("EPSG:4326", allow_override=True)
    plz_geo.to_file(paths.plz_features_geojson, driver="GeoJSON")

    # Model B
    X, y, rf_feature_cols = build_regression_training_set(plz_features, current_year=current_year, scenarios_per_plz=18)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.22, random_state=42)
    rf_pipe = train_rf(X_train, y_train)

    yhat = rf_pipe.predict(X_test)
    print("Model B (RF) evaluation on synthetic holdout:")
    print(f"- R2:  {r2_score(y_test, yhat):.3f}")
    print(f"- MAE: {mean_absolute_error(y_test, yhat):.3f} tons/year")

    # Persist
    joblib.dump(kmeans_pipe, paths.kmeans_pipeline_path)
    joblib.dump(rf_pipe, paths.rf_pipeline_path)

    metadata = {
        "current_year": current_year,
        "kmeans_feature_cols": kmeans_feature_cols,
        "rf_feature_cols": rf_feature_cols,
        "species_cols": list(SPECIES_GROWTH_FACTOR.keys()),
        "notes": "Botanical and 2050 targets are proxy-based for demo; replace with validated equations for production.",
    }
    joblib.dump(metadata, paths.metadata_path)

    print("Saved artifacts:")
    print(f"- {paths.trees_enriched_parquet}")
    print(f"- {paths.plz_features_geojson}")
    print(f"- {paths.kmeans_pipeline_path}")
    print(f"- {paths.rf_pipeline_path}")
    print(f"- {paths.metadata_path}")


if __name__ == "__main__":
    main()
