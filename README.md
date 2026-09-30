# PH Flood Mapping

Finds areas of Rivers State, Nigeria that flood repeatedly, models where water
*should* drain to, and flags the mismatches as suspected drainage blockages.
Built entirely on free satellite data and open geospatial tools.

**Status:** early prototype — non-commercial research.

## How it works

1. **Flood detection** — Sentinel-1 radar (sees through cloud) compared against a
   dry-season baseline; open water classified with Otsu thresholding, permanent
   water removed with the JRC Global Surface Water mask.
2. **Repeat-offender stacking** — flood masks from several rainy seasons summed
   into a flood-frequency map.
3. **Drainage modelling** — MERIT Hydro flow accumulation and HAND (Height Above
   Nearest Drainage), computed on the wider catchment, not per LGA.
4. **Anomaly detection** — each repeat-flood area is classified with explicit
   rules (`analysis/suspects.py`): *natural* (major river, very low ground, or
   mapped wetland), *suspect* (built-up and either ≥ 3 m above drainage in both
   MERIT and FABDEM, or on a channel within 150 m of a major-road crossing), or
   *unclear*. Suspects are ranked by years flooded × height anomaly.
5. **Web map** — static Leaflet site (`web/`) reading precomputed files; no backend.

Processed LGA by LGA: Obio/Akpor → Port Harcourt → Ikwerre → Okrika → …

## Limitations

- MERIT Hydro (~90 m) cannot resolve individual culverts or street drains.
  Output is neighbourhood-level triage, not per-drain diagnosis.
- Radar struggles under dense canopy and among tall buildings.
- Flagged sites are **hypotheses requiring ground verification**. A site may be
  blocked drainage, or simply built on a natural floodplain.

## Layout

```
analysis/       Earth Engine pipeline (Python)
web/            Static site deployed to Vercel (Leaflet, no build step)
web/data/       Published results — written by `python -m analysis.publish`
data/           Working outputs (git-ignored)
design-system/  Design tokens and rules for the site
```

## Running the pipeline

```bash
python -m analysis.run_stage2 --lga "Obio/Akpor" --pass 2026-09-29:22 --pass 2026-09-29:30
python -m analysis.run_stage3 --lga "Obio/Akpor" --years 2021-2026
python -m analysis.run_stage4 --lga "Obio/Akpor"
python -m analysis.run_stage5 --lga "Obio/Akpor"
python -m analysis.publish          # copy results into web/data/
```

## Site

```bash
cd web && python3 -m http.server 8765   # preview at http://localhost:8765
node --test js/                        # front-end unit tests
```

Deploy on Vercel with **Root Directory = `web`** (no build command). Security
headers and caching are in `web/vercel.json`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/earthengine authenticate
```

Requires a Google Earth Engine project registered for non-commercial use.
Credentials are stored in `~/.config/earthengine/` and never in this repo.

## Data sources and attribution

- Sentinel-1 SAR GRD — contains modified Copernicus Sentinel data, ESA.
- MERIT Hydro — Yamazaki et al. (2019), CC-BY-NC 4.0 / ODbL 1.0.
- JRC Global Surface Water — Pekel et al. (2016), EC JRC / Google.
- geoBoundaries — Runfola et al. (2020), CC-BY 4.0.
- FABDEM — Hawker et al. (2022), CC BY-NC-SA 4.0 (terrain layers inherit this).
- Google Open Buildings v3 — CC BY 4.0 / ODbL.
- ESA WorldCover 2021 v200 — CC BY 4.0.
- OpenStreetMap (roads, place names, basemap) — © OpenStreetMap contributors, ODbL.

MERIT Hydro's licence restricts derived outputs to non-commercial use.

## Licence

Code: MIT. Derived data inherits the licences of its sources above.
