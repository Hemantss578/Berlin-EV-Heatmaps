# Heatmaps: Electric Charging Stations & Residents in Berlin

**Group 2** — An interactive Streamlit platform for analysing the spatial distribution of residents and electric vehicle charging stations across Berlin's postal codes. Heatmaps highlight population density and charging-station distribution so users can identify infrastructure gaps and make data-driven decisions.

**Live demo:** [add your Streamlit Community Cloud link here after deploying — see docs/DEPLOY.md]

**Live Power BI dashboard:** [add your Publish to web link here]

A companion **Power BI dashboard** (see below) reframes the same underlying
data as a single-page performance-analytics view — KPI cards, a coverage
trend, and a ranked/underserved-region breakdown — for a quick, recruiter-facing
look at the analysis without running the app.

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
├── scripts/
│   └── prepare_berlin_data.py   # One-time: trims the national charging register to Berlin-only (see docs/DEPLOY.md)
├── docs/
│   └── DEPLOY.md                 # Streamlit Community Cloud deployment walkthrough
├── POWERBI_DASHBOARD_GUIDE.md   # Full Power BI build walkthrough (Power Query, DAX, visuals, publish)
├── assets/                       # Dashboard screenshots/GIFs for this README (add your own)
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

## Deploying a public link

See `docs/DEPLOY.md` for the full walkthrough (trimming the national
charging-station register to Berlin-only so it's small enough to commit,
pushing to GitHub, and deploying to Streamlit Community Cloud for free).

## How it works

1. **Data input & preprocessing** — population data is filtered to Berlin postal codes (10115–14199) and cleaned of invalid entries; the charging register is filtered to Berlin, coordinates are standardised (German decimal commas → floats) and rows with missing values dropped.
2. **Geospatial processing** — both datasets are merged with the PLZ polygon geometries into GeoDataFrames; counts and total nominal power are aggregated per postal code; geometries are validated before rendering.
3. **Visualisation** — folium renders the choropleths and heatmaps inside Streamlit via `streamlit-folium`, with branca colormaps providing dynamic legends.

## Power BI dashboard

A single-page, interactive Power BI dashboard built from the same two real
data sources as the Streamlit app (`Ladesaeulenregister.csv`,
`plz_einwohner.csv`), reframed in business/product-analytics language so it
reads as performance monitoring rather than a niche EV study.

**Live link:** [add your Publish to web link here]

**Screenshot:**

![Power BI dashboard screenshot](assets/powerbi-dashboard.png)
*(add a screenshot or short GIF of the dashboard here)*

**What it answers**

- How much charging capacity is deployed, and how is it trending over time?
- Which Berlin postal codes are underserved relative to their population?
- What's the mix of standard vs. fast charging capacity?
- How does coverage compare to a defined target?

**KPIs**

| KPI | Definition |
|---|---|
| Total charge points | Sum of installed charge points across active stations |
| Coverage rate (per 10k) | Charge points per 10,000 residents, by postal code |
| Residents per charge point | Population ÷ charge points — the core "how underserved" ratio |
| MoM growth % | Month-over-month change in cumulative charge points, from commissioning date |
| Coverage vs. target % | Measured coverage rate against a self-defined benchmark target |

**How it was built**

- **Power Query:** imported and cleaned the raw Bundesnetzagentur register
  (fixed Windows-1252 encoding, stripped ~10 metadata header rows, converted
  German decimal-comma numbers and `DD.MM.YYYY` dates via locale-aware type
  conversion, filtered to active stations in Berlin's postal-code range).
- **Data model:** a star schema — `Stations` (fact) related to a
  `DateTable` (marked as the official date table) on commissioning date, and
  to `Residents` (population per postal code) on postal code.
- **DAX:** custom measures for total capacity, month-over-month growth
  (`DATEADD`), a residents-per-charge-point coverage ratio, and a
  KPI-vs-target measure.
- **Visuals:** KPI card row, a cumulative-growth trend line, a top-10
  ranked bar by postal code, a charging-type mix breakdown, and a detail
  matrix with conditional formatting highlighting the most underserved
  postal codes — plus date/region/power-class slicers.

Full build walkthrough (every Power Query step, DAX with plain-English
explanations, layout rationale): [`POWERBI_DASHBOARD_GUIDE.md`](POWERBI_DASHBOARD_GUIDE.md).

**Honest note:** the Power Query cleaning, data model, and every KPI except
one are built directly on the real Bundesnetzagentur and population data —
nothing is synthetic. The one exception is the coverage *target* value used
in the KPI-vs-target measure, which is a self-defined illustrative
benchmark (there's no official per-postal-code EV coverage target), not an
official figure.

## Technologies

Python 3.12 · pandas · geopandas · shapely · folium · branca · streamlit · streamlit-folium · Power BI (Power Query, DAX, data modelling)
