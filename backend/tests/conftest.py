import sys
from pathlib import Path

# Tests import backend modules directly (store, scoring, ...), like uvicorn does from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
