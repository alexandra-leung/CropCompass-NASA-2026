from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = APP_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
DATABASE_PATH = DATA_DIR / "climate_cache.sqlite3"
CACHE_TTL_SECONDS = 6 * 60 * 60
NASA_POWER_BASE_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
NEX_GDDP_BASE_URL = "https://ds.nccs.nasa.gov/thredds/ncss/grid/AMES/NEX/GDDP-CMIP6"
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
MODEL_REGISTRY_PATH = BACKEND_DIR / "config" / "model_registry.json"

NEX_GDDP_DATASET_VERSION = "v2.0"

NEX_GDDP_MAX_CONCURRENCY = 3