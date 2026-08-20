# Berlin Smart Canopy: Urban Carbon Sequestration & ML Optimization

This folder contains a complete, runnable demo implementation of the **Berlin Smart Canopy** concept:

- Synthetic Berlin-like datasets (trees, emissions, PLZ polygons) in **EPSG:4326**
- Botanical proxy equations for per-tree sequestration and storage
- **Model A** (KMeans): cluster PLZs to identify high-priority planting zones
- **Model B** (RandomForest): predict **2050 annual canopy absorption** under a user-defined planting plan
- Streamlit app with an interactive folium map + an ML planting simulator

## Quickstart

From the repository root:

```bash
pip install -r requirements.txt
python berlin_smart_canopy/data_generator.py
python berlin_smart_canopy/ml_engine.py
streamlit run berlin_smart_canopy/app.py
```

## Files

- `data_generator.py` — creates mock data in `berlin_smart_canopy/data/raw/`
- `ml_engine.py` — feature engineering + trains models + saves artifacts
- `app.py` — Streamlit UI (Dashboard + Simulator)

## Notes

- The sequestration equations are **proxies for demonstration**. For production, replace them with validated species- and site-specific allometric models and include mortality/maintenance constraints.
- The generated PLZ polygons are a **synthetic grid**, not real Berlin postal geometries.
