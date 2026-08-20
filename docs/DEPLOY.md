# Deploying the demo for a public resume link

## Streamlit Community Cloud (free)

Deploys directly from a GitHub repo, no separate hosting/model-storage step
to configure, and this project already is a Streamlit app.

### 1. Trim the charging-station dataset to Berlin only

`datasets/Ladesaeulenregister.csv` as downloaded from Bundesnetzagentur
covers all of Germany -- too large to comfortably commit and unnecessary,
since the app only ever uses the Berlin subset. Run this once:

```bash
pip install -r requirements.txt
python scripts/prepare_berlin_data.py
```

This overwrites `datasets/Ladesaeulenregister.csv` in place with just the
Berlin rows, in the exact same column format, so no app code changes are
needed. It'll print how many rows it kept (expect roughly 1,000-3,000, down
from 130,000+).

Sanity check it locally before deploying:

```bash
streamlit run app.py
```

Click through all three pages (Heatmaps & Analysis, Report & Suggest,
Community Reports) and confirm the maps render.

### 2. Push to GitHub (public repo)

```bash
git add app.py config.py core/ scripts/ requirements.txt \
        datasets/Ladesaeulenregister.csv datasets/plz_einwohner.csv datasets/geodata_berlin_plz.csv \
        README.md .gitignore docs/
git commit -m "Trim charging-station data to Berlin and prep for hosted deploy"
git push
```

Make sure the repo is **public** -- Streamlit Community Cloud's free tier
needs to read it, and it's what you'll link on your resume anyway.

### 3. Deploy

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with
   GitHub.
2. **New app** -> pick this repository and branch -> Main file path: `app.py`.
   (This repo also contains a second, unrelated app under
   `berlin_smart_canopy/` -- make sure the main file path points at the root
   `app.py`, not that one.)
3. Deploy. First build takes a few minutes (geopandas pulls in some
   binary dependencies, so it's not instant).
4. You'll get a URL like `https://<something>.streamlit.app` -- **that's
   your resume link.**

### 4. Known limitation worth knowing about: crowdsourced reports aren't durable

`core/reports.py` writes submitted reports to `datasets/user_reports.csv` on
local disk. On Streamlit Community Cloud that file lives inside the app's
container filesystem, which is **not persistent across redeploys or the
periodic container restarts** free-tier apps get. Reports submitted by
visitors will show up in the "Community Reports" page during that session
but can vanish on the next restart. That's fine for a portfolio demo (it's
demonstrating the crowdsourcing *feature*, not running a real production
service), but it's worth being able to explain if a recruiter asks "does
this actually save data?" -- the honest answer is "yes, until the container
restarts; a real deployment would back this with a database instead of a
CSV file."

### 5. Keep it awake

Streamlit Community Cloud's free tier puts idle apps to sleep after a
period of inactivity; the next visitor triggers a ~30-60 second cold start.
Normal for a free-tier demo -- visiting it yourself before an interview
keeps it warm.
