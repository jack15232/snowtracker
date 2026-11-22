"""All tunables in one place. Edit here, not in the code."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = ROOT / "archive"          # raw API responses, gitignored
STATE_FILE = ROOT / "archive" / "state.json"
DOCS_DIR = ROOT / "docs"                # GitHub Pages root
DATA_DIR = DOCS_DIR / "data"

TZ = "Europe/Rome"
FORECAST_DAYS = 7

# One gridpoint above Alagna; elevation is overridden per band so Open-Meteo
# lapse-rate-corrects temperature to each band.
LAT, LON = 45.854, 7.938

BANDS = [
    {"id": "1200", "elev": 1200, "label": "Village 1200m"},
    {"id": "2000", "elev": 2000, "label": "Pianalunga 2000m"},
    {"id": "2400", "elev": 2400, "label": "Pisse 2400m"},
    {"id": "3000", "elev": 3000, "label": "Salati 3000m"},
]
HEADLINE_BAND = "2400"

# Ensemble models. Open-Meteo renamed tokens during 2026, so each model lists
# candidate tokens tried in order; the first that works is remembered.
MODELS = [
    {"id": "ecmwf_ifs", "name": "ECMWF IFS", "tokens": ["ecmwf_ifs025_ensemble", "ecmwf_ifs025"]},
    {"id": "ecmwf_aifs", "name": "ECMWF AIFS", "tokens": ["ecmwf_aifs025_ensemble", "ecmwf_aifs025"]},
    {"id": "icon", "name": "DWD ICON", "tokens": ["icon_seamless_eps", "dwd_icon_seamless_eps", "icon_seamless"]},
    {"id": "gefs", "name": "NOAA GEFS", "tokens": ["ncep_gefs025", "gfs025", "ncep_gefs_seamless", "gfs_seamless"]},
    {"id": "ch2", "name": "MeteoSwiss CH2", "tokens": ["meteoswiss_icon_ch2_ensemble", "meteoswiss_icon_ch2"]},
    {"id": "ch1", "name": "MeteoSwiss CH1", "tokens": ["meteoswiss_icon_ch1_ensemble", "meteoswiss_icon_ch1"]},
]
# Each model gets equal total weight in the pooled ensemble (members share it).
MODEL_WEIGHTS = {m["id"]: 1.0 for m in MODELS}

ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARS = ["precipitation", "snowfall", "temperature_2m", "freezing_level_height"]
CORE_VARS = ["precipitation", "temperature_2m"]   # fallback if a model rejects a variable

# ---- snow calc -------------------------------------------------------------
# Snow fraction from band elevation vs freezing level (FL). The snow line sits
# ~300 m below FL; transition is linear across SNOW_RAMP_M centred there.
SNOWLINE_BELOW_FL_M = 300
SNOW_RAMP_M = 300
# Fallback when FL is missing: fraction from band temperature (°C)
T_ALL_SNOW, T_ALL_RAIN = -0.5, 2.0
# Snow-to-liquid ratio by band temperature (°C -> ratio), linearly interpolated
# Conservative (~10:1 around -3°C, close to Alpine mean new-snow density ~100 kg/m3) until
# calibrated against Bocchetta delle Pisse depth changes.
SLR_TABLE = [(-15, 15), (-10, 13), (-6, 11), (-3, 10), (0, 8), (1, 7), (3, 7)]

PROB_THRESHOLDS_CM = [10, 30]   # daily
HEADLINE_THRESHOLD_CM = 20      # next-72h

# ---- observations ---------------------------------------------------------
ARPA_SERIES_URL = "https://www.arpa.piemonte.it/rischi_naturali/data/tr/{param}/{sensor}.geojson"
STATIONS = [
    {"sensor": "002002900", "name": "Bocchetta delle Pisse", "elev": 2410, "side": "Alagna"},
    {"sensor": "002002901", "name": "Alagna Miniere", "elev": 1347, "side": "Alagna"},
    {"sensor": "003086900", "name": "Passo del Moro", "elev": 2820, "side": "Macugnaga"},
]
EAWS_URL = "https://static.avalanche.report/eaws_bulletins/{d}/{d}-IT-21.json"
AVALANCHE_REGION = "IT-21-VB-01"   # Alpi Pennine di confine (contains Alagna)

# ---- scheduling (used by `run.py --auto`) -----------------------------------
OBS_EVERY_MIN = 30
FORECAST_EVERY_MIN = 60
AVALANCHE_EVERY_MIN = 180

USER_AGENT = "snowcast/1.0 (personal ski forecast; github.com)"

# ---- webcams (Monterosa Ski, Alagna side) ----------------------------------
# Direct JPEGs served by monterosa2000.it (as embedded on monterosaski.eu).
WEBCAM_BASE = "https://www.monterosa2000.it/webcam/"
WEBCAMS = [
    {"id": "pianalunga", "name": "Pianalunga", "elev": 2046, "path": "Pianalunga/001/Pianalunga.jpg",
     "page": "https://monterosaski.eu/en/webcam/pianalunga-webcam-20743"},
    {"id": "olen", "name": "Valle Olen", "elev": 2070, "path": "Pianalunga/002/Pianalunga.jpg",
     "page": "https://monterosaski.eu/en/webcam/valle-olen-webcam-25194"},
    {"id": "cimalegna", "name": "Cimalegna chairlift", "elev": 2656, "path": "Cimalegna/011/Cimalegna.jpg",
     "page": "https://monterosaski.eu/en/webcam/seggiovia-cimalegna-webcam-20747"},
    {"id": "salati_view", "name": "View to Passo dei Salati", "elev": 2656, "path": "Cimalegna/012/Cimalegna.jpg",
     "page": "https://monterosaski.eu/en/webcam/seggiovia-cimalegna-webcam-20747"},
    {"id": "monterosa", "name": "Monte Rosa panorama", "elev": 2656, "path": "Cimalegna/013/Cimalegna.jpg",
     "page": "https://monterosaski.eu/en/webcam/seggiovia-cimalegna-webcam-20747"},
    {"id": "salati", "name": "Passo dei Salati / Mosso", "elev": 2900, "path": "Mosso/602/Mosso.jpg",
     "page": "https://monterosaski.eu/en/webcam/stazione-funifor-passo-dei-salati-webcam-25190"},
    {"id": "valsesia", "name": "Valsesia panorama", "elev": 2656, "path": "Cimalegna/015/Cimalegna.jpg",
     "page": "https://monterosaski.eu/en/webcam/seggiovia-cimalegna-webcam-20747"},
]
WEBCAM_INDEX = "https://monterosaski.eu/en/webcam"
