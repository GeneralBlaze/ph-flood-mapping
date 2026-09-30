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
4. **Anomaly detection** — frequent flooding where terrain says water should
   drain away is flagged and ranked.
5. **Web map** — Leaflet over OpenStreetMap, serving precomputed GeoJSON.

Processed LGA by LGA: Obio/Akpor → Port Harcourt → Ikwerre → Okrika → …

## Limitations

- MERIT Hydro (~90 m) cannot resolve individual culverts or street drains.
  Output is neighbourhood-level triage, not per-drain diagnosis.
- Radar struggles under dense canopy and among tall buildings.
- Flagged sites are **hypotheses requiring ground verification**. A site may be
  blocked drainage, or simply built on a natural floodplain.

## Layout

```
analysis/   Earth Engine pipeline (Python)
api/        FastAPI serving precomputed GeoJSON
web/        Leaflet front end
data/       Generated outputs (git-ignored)
```

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
- OpenStreetMap — © OpenStreetMap contributors, ODbL.

MERIT Hydro's licence restricts derived outputs to non-commercial use.

## Licence

Code: MIT. Derived data inherits the licences of its sources above.
