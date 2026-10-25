import os
import sys
import tempfile
from pathlib import Path

# Tests import backend modules directly (store, scoring, ...), like uvicorn does from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# A throwaway database, set before config is imported. Tests never make live calls.
os.environ["CRUMBS_DB"] = str(Path(tempfile.mkdtemp(prefix="crumbs-test-")) / "crumbs.db")
os.environ.pop("DEMO_MODE", None)
# Never reach a real Supabase project from tests, even if backend/.env has keys (load_dotenv won't override these).
for _name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY"):
    os.environ[_name] = ""
