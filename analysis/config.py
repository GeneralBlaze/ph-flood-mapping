"""Project-wide settings. Tune thresholds here, not in the pipeline code."""

EE_PROJECT = "ph-flood-mapping"

BOUNDARIES_ASSET = "WM/geoLab/geoBoundaries/600/ADM2"
S1_ASSET = "COPERNICUS/S1_GRD"
JRC_ASSET = "JRC/GSW1_4/GlobalSurfaceWater"

# Processing order agreed for Rivers State. Names as spelled in geoBoundaries.
LGA_ORDER = ["Obio/Akpor", "Port-Harcourt", "Ikwerre", "Okrika"]

# Dry-season baseline window (harmattan months, lowest water).
DRY_SEASON = ("2025-12-01", "2026-03-01")

# SAR preprocessing
POLARISATION = "VH"
SPECKLE_RADIUS_M = 50

# Flood classification
PERMANENT_WATER_OCCURRENCE_PCT = 50   # JRC occurrence at/above this = permanent water
TIDAL_OCCURRENCE_PCT = 10             # water this often (JRC) = tidal/intermittent; excluded as not flooding
WORLDCOVER_ASSET = "ESA/WorldCover/v200"
MANGROVE_CLASS = 95                   # ESA WorldCover mangroves: tidal, excluded
MAX_DIFF_THRESHOLD_DB = -1.5          # a flood pixel must darken by at least this much
MIN_PATCH_PIXELS = 10                 # drop specks smaller than ~0.1 ha at 10 m
HISTOGRAM_SCALE_M = 20

# Place ranking
TOP_CLUSTERS = 25                     # largest flood patches to name via Nominatim
PLACE_BUFFER_M = 750
MIN_FLOODED_HA = 0.5

OUTPUT_SCALE_M = 10

# Stage 3 stacking
ORBITS = [22, 30, 124]                # relative orbits covering Port Harcourt
STACK_YEARS = "2021-2026"
MIN_FLOOD_OBS_PER_YEAR = 3            # flooded on >= this many dates to count a year (1 was mostly noise)
YEAR_MIN_PATCH_PIXELS = 10            # drop isolated specks from each year's flood flag
REPEAT_MIN_PATCH_PIXELS = 50          # repeat-flood areas smaller than ~0.5 ha are not vectorised
REPEAT_MIN_YEARS = 3                  # "repeat offender" = flooded in at least this many years
EE_WORKERS = 6                        # parallel Earth Engine requests when thresholding scenes

# Stage 4 drainage modelling
WORKING_CRS = "EPSG:32632"            # UTM 32N, metric grid for Port Harcourt
TERRAIN_SCALE_M = 30
HYDRO_BUFFER_M = 10_000               # model the catchment around the LGA, not just inside it
CHANNEL_UPA_KM2 = 1.0                 # upstream area that makes a cell an expected channel
MAX_CHANNEL_DISTANCE_PX = 256         # ~7.7 km at 30 m; beyond this distance is capped
HOLLOW_RADIUS_M = 250                 # neighbourhood for local-hollow detection
CHANNEL_SEARCH_M = 1000              # search radius for the nearest channel in FABDEM-based HAND

# Standing water after a dry spell
STANDING_SITE_MIN_FRAC = 0.1          # share of a site still wet to call it "still under water"
