# Heatmaps: Electric Charging Stations & Residents in Berlin

**Group 2** — An interactive Streamlit platform for analysing the spatial distribution of residents and electric vehicle charging stations across Berlin's postal codes. Heatmaps highlight population density and charging-station distribution so users can identify infrastructure gaps and make data-driven decisions.

## Features

- **Residents heatmap** — choropleth of population per postal code (yellow → red gradient)
- **Charging-station heatmaps** — station counts per postal code, a kW-weighted point-density heatmap, and toggleable layers by nominal-power class (AC normal, fast, DC fast, HPC)
- **Crowdsourced reporting** — users click the map to report malfunctioning stations (red wrench markers) or suggest new station locations (green plus markers); reports persist to `datasets/user_reports.csv`
- **Community reports page** — filterable map + table of all submissions with CSV export
- **Gap analysis** — residents-per-station per postal code, enriched with crowdsourced malfunction/suggestion counts, to surface high-demand underserved areas
- **Interactive map** — pan, zoom, hover tooltips and dynamic legends per layer

## Project structure

```
berlin-ev-heatmaps/
├── app.py               # Streamlit application (3 pages: heatmaps, report & suggest, community)
├── config.py            # Paths, map settings, power bins
├── core/
│   ├── methods.py       # Loading, preprocessing, geospatial merge, map builders
│   └── reports.py       # Crowdsourcing: store/load user reports, map markers
├── datasets/            # Place the three data files here (user_reports.csv is created automatically)
└── requirements.txt
```

## Setup

1. **Python 3.12** recommended.

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Download the datasets and place them in `datasets/`:

   | File | Source |
   |---|---|
   | `Ladesaeulenregister_SEP.xlsx` (or `Ladesaeulenregister.csv`) | Bundesnetzagentur Ladesäulenregister — bundesnetzagentur.de |
   | `plz_einwohner.csv` | suche-postleitzahl.org (population per PLZ) |
   | `geodata_berlin_plz.csv` | Berlin PLZ polygons as WKT (course material / suche-postleitzahl.org shapefiles converted to CSV with `PLZ;geometry`) |

4. Run the app:
   ```bash
   streamlit run app.py
   ```

   The app opens at `http://localhost:8501`.

## How it works

1. **Data input & preprocessing** — population data is filtered to Berlin postal codes (10115–14199) and cleaned of invalid entries; the charging register is filtered to Berlin, coordinates are standardised (German decimal commas → floats) and rows with missing values dropped.
2. **Geospatial processing** — both datasets are merged with the PLZ polygon geometries into GeoDataFrames; counts and total nominal power are aggregated per postal code; geometries are validated before rendering.
3. **Visualisation** — folium renders the choropleths and heatmaps inside Streamlit via `streamlit-folium`, with branca colormaps providing dynamic legends.

## Technologies

Python 3.12 · pandas · geopandas · shapely · folium · branca · streamlit · streamlit-folium
