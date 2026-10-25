import os
import sys
import tempfile
from pathlib import Path

# Tests import backend modules directly (store, scoring, ...), like uvicorn does from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# A throwaway database, set before config is imported. Tests never make live calls.
os.environ["CRUMBS_DB"] = str(Path(tempfile.mkdtemp(prefix="crumbs-test-")) / "crumbs.db")
os.environ.pop("DEMO_MODE", None)
# Sign-in is tested on its own (test_auth.py patches auth.enabled). Elsewhere it stays off, even though importing
# agent/ loads the repo's .env, which may hold real Supabase keys.
os.environ["AUTH_DISABLED"] = "1"
os.environ["ALERT_SCHEDULE"] = "off"  # no background competitor checks during tests (test_scheduler.py runs ticks itself)
