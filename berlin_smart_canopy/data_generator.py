"""\
    
Synthetic data generator for Berlin Smart Canopy (mock datasets).

Creates (in berlin_smart_canopy/data/raw):
- baumbestand_berlin.csv       (street tree point inventory)
- berlin_emissions_plz.csv     (annual CO2 emissions by PLZ)
- berlin_plz.geojson           (synthetic PLZ polygons as a grid)

All geometries and coordinates are EPSG:4326 (lat/lon).

Usage:
    python data_generator.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon, Point


@dataclass(frozen=True)
class Paths:
    project_root: Path = Path(__file__).resolve().parent
    data_raw: Path = project_root / "data" / "raw"

    trees_csv: Path = data_raw / "baumbestand_berlin.csv"
    emissions_csv: Path = data_raw / "berlin_emissions_plz.csv"
    plz_geojson: Path = data_raw / "berlin_plz.geojson"


SPECIES_POOL = [
    "Tilia (Linde)",
    "Quercus (Eiche)",
    "Acer (Ahorn)",
    "Platanus",
    "Betula",
    "Fraxinus",
]
SPECIES_PROBS = np.array([0.24, 0.16, 0.22, 0.14, 0.14, 0.10])


def _ensure_dirs(paths: Paths) -> None:
    paths.data_raw.mkdir(parents=True, exist_ok=True)


def _make_plz_grid(
    bbox: tuple[float, float, float, float],
    n_cols: int,
    n_rows: int,
    plz_start: int = 10115,
) -> gpd.GeoDataFrame:
    """Create a synthetic rectangular grid (valid polygons) over a Berlin-like bbox."""
    min_lon, min_lat, max_lon, max_lat = bbox
    dx = (max_lon - min_lon) / n_cols
    dy = (max_lat - min_lat) / n_rows

    polys: list[Polygon] = []
    plzs: list[str] = []
    i = 0
    for r in range(n_rows):
        for c in range(n_cols):
            x0 = min_lon + c * dx
            x1 = x0 + dx
            y0 = min_lat + r * dy
            y1 = y0 + dy
            polys.append(Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)]))
            plzs.append(str(plz_start + i))
            i += 1

    return gpd.GeoDataFrame({"PLZ": plzs}, geometry=polys, crs="EPSG:4326")


def _random_point_in_polygon(rng: np.random.Generator, poly: Polygon, max_tries: int = 500) -> Point:
    """Rejection sample a point within polygon bounds."""
    minx, miny, maxx, maxy = poly.bounds
    for _ in range(max_tries):
        p = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
        if poly.contains(p):
            return p
    return poly.centroid


def main(seed: int = 42) -> None:
    paths = Paths()
    _ensure_dirs(paths)

    rng = np.random.default_rng(seed)
    current_year = int(pd.Timestamp.today().year)

    # Approximate Berlin bounding box (synthetic; not official)
    berlin_bbox = (13.088, 52.338, 13.761, 52.675)  # (min_lon, min_lat, max_lon, max_lat)

    # 30 synthetic districts
    plz_gdf = _make_plz_grid(berlin_bbox, n_cols=6, n_rows=5, plz_start=10115)

    # Emissions / urban form signals
    n_plz = len(plz_gdf)
    pop_density = rng.uniform(2500, 18000, size=n_plz)  # people/km2
    sealed_surface_ratio = np.clip(
        0.25
        + (pop_density - pop_density.min()) / (pop_density.max() - pop_density.min()) * 0.6
        + rng.normal(0, 0.05, size=n_plz),
        0.05,
        0.98,
    )

    total_co2_tons = (
        25000
        + pop_density * 2.2
        + sealed_surface_ratio * 40000
        + rng.normal(0, 4000, size=n_plz)
    )
    total_co2_tons = np.clip(total_co2_tons, 15000, None)

    emissions_df = pd.DataFrame(
        {
            "PLZ": plz_gdf["PLZ"].astype(str).values,
            "total_co2_tons": total_co2_tons.round(2),
            "population_density": pop_density.round(2),
            "sealed_surface_ratio": sealed_surface_ratio.round(4),
        }
    )

    # Trees per PLZ inversely related to density (weakly)
    base_trees = 900
    density_scaled = (pop_density - pop_density.min()) / (pop_density.max() - pop_density.min())
    expected_trees = base_trees * (1.15 - 0.55 * density_scaled)
    expected_trees = np.clip(expected_trees, 250, 1400)

    rows: list[dict] = []
    tree_id = 1

    for idx, plz_row in plz_gdf.iterrows():
        plz = str(plz_row["PLZ"])
        poly = plz_row.geometry

        n_trees = int(max(80, rng.poisson(lam=float(expected_trees[idx]))))

        species = rng.choice(SPECIES_POOL, size=n_trees, p=SPECIES_PROBS)

        # More recent planting is more common
        u = rng.beta(2.2, 1.6, size=n_trees)
        planting_year = (1950 + u * (current_year - 1950)).astype(int)
        age = np.maximum(current_year - planting_year, 1)

        # Diameter grows with age + species-specific multiplier + noise
        diam_mult = pd.Series(species).map(
            {
                "Quercus (Eiche)": 1.15,
                "Tilia (Linde)": 1.05,
                "Acer (Ahorn)": 0.95,
                "Platanus": 1.10,
                "Betula": 0.85,
                "Fraxinus": 1.00,
            }
        ).fillna(1.0).to_numpy()

        trunk_diameter_cm = 5.0 + (age**0.75) * 1.8 * diam_mult + rng.normal(0, 3.0, size=n_trees)
        trunk_diameter_cm = np.clip(trunk_diameter_cm, 4.0, 140.0)

        points = [_random_point_in_polygon(rng, poly) for _ in range(n_trees)]

        for i in range(n_trees):
            rows.append(
                {
                    "tree_id": tree_id,
                    "species": str(species[i]),
                    "planting_year": int(planting_year[i]),
                    "trunk_diameter_cm": float(trunk_diameter_cm[i]),
                    "latitude": float(points[i].y),
                    "longitude": float(points[i].x),
                    "PLZ": plz,
                }
            )
            tree_id += 1

    trees_df = pd.DataFrame(rows)

    # Write
    plz_gdf.to_file(paths.plz_geojson, driver="GeoJSON")
    emissions_df.to_csv(paths.emissions_csv, index=False)
    trees_df.to_csv(paths.trees_csv, index=False)

    print("Berlin Smart Canopy synthetic datasets written:")
    print(f"- {paths.plz_geojson}")
    print(f"- {paths.emissions_csv}")
    print(f"- {paths.trees_csv}")
    print(f"Trees generated: {len(trees_df):,} across PLZs: {len(plz_gdf):,}")


if __name__ == "__main__":
    main()
