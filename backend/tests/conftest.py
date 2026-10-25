import os
import sys
import tempfile
from pathlib import Path

# Tests import backend modules directly (store, scoring, ...), like uvicorn does from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# A throwaway database, set before config is imported. Tests never make live calls.
os.environ["CRUMBS_DB"] = str(Path(tempfile.mkdtemp(prefix="crumbs-test-")) / "crumbs.db")
os.environ.pop("DEMO_MODE", None)
