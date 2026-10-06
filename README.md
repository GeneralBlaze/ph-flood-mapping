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

Deployed on Vercel: every push to `main` deploys automatically (the project is
connected to this repo). `vercel.json` at the repo root serves `web/` with no
build step and sets the security headers and caching.

### Full analysis of a drawn area (`api/area.py`)

Anyone can draw an area (up to 10 km², inside Rivers State) and run the full
pipeline on it: radar flood history 2021–2026 and the latest pass, routing on
FABDEM, Open Buildings on the routes, and OSM streets. It runs as five requests
(`history`, `latest`, `routes`, `buildings`, `streets`), each well under
Vercel's 300 s limit; the browser carries each step's output to the next.
Inside an analysed LGA the history comes from the published yearly stacks;
elsewhere it is recomputed scene by scene with thresholds set over the area.

```bash
python -m analysis.dev_server --port 8792   # site + /api/area with your own Earth Engine login
```

On Vercel it stays hidden until it can log in to Earth Engine. It logs in
without a key: Vercel's per-request OIDC token is exchanged (Workload Identity
Federation) for short-lived credentials of the service account
`ph-flood-server@ph-flood-mapping.iam.gserviceaccount.com`, which has only the
roles *Earth Engine Resource Viewer* and *Service Usage Consumer*. Environment
variables (Settings → Environment Variables):

- `GCP_PROJECT_NUMBER`, `GCP_SERVICE_ACCOUNT_EMAIL`,
  `GCP_WORKLOAD_IDENTITY_POOL_ID`, `GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID`
- `AREA_TOKEN_SECRET` (Sensitive): a random string that signs run tokens.

The pool's OIDC provider trusts issuer `https://oidc.vercel.com/<team-slug>`,
audience `https://vercel.com/<team-slug>`, maps `google.subject` to
`assertion.sub`, and only this project's production deployments may use the
service account. A JSON key in `EE_SERVICE_ACCOUNT_KEY` also works but is not
recommended.

Limits: 3 runs and 30 step requests per connection per 10 minutes in each
server instance, and a signed token ties the later steps to the first. Add a
Vercel Firewall rate-limit rule as the main limit: path `/api/area`, method
POST, 20 requests per 10 minutes per IP.

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
