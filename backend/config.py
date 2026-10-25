"""Settings for the crumbs backend.

Keys come only from backend/.env (gitignored) or the process environment, and are never sent to the
frontend. This module is imported first so .env is loaded before Ruth's agent reads os.environ.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")

# Ruth's scraper lives in agent/ at the repo root.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DB_PATH = Path(os.getenv("CRUMBS_DB", str(BACKEND_DIR / "crumbs.db")))
DEMO_DIR = BACKEND_DIR / "demo"
SCORING_MODEL = os.getenv("SCORING_MODEL", "claude-sonnet-5-5")
CACHE_HOURS = 24
FRONTEND_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
KEY_NAMES = ["ANTHROPIC_API_KEY", "TAVILY_API_KEY", "GOOGLE_PLACES_API_KEY", "SQUARE_ACCESS_TOKEN", "SUPABASE_URL",
             "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEY"]

# The demo area: the middle of Capitol Hill, Seattle.
CAPITOL_HILL = {"lat": 47.6190, "lng": -122.3210, "radiusMi": 1.0, "label": "Capitol Hill, Seattle"}


def demo_mode() -> bool:
    return os.getenv("DEMO_MODE") == "1"


def has_key(name: str) -> bool:
    return bool(os.getenv(name, "").strip())
