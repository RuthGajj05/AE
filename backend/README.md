# Backend

FastAPI service. Keys stay here; the frontend never sees them.

## Run
```
cd backend
pip install -r requirements.txt
cp .env.example .env        # add ANTHROPIC_API_KEY (and TAVILY_API_KEY)
export $(cat .env | xargs)
uvicorn main:app --reload --port 8000
```

## Endpoints
| Endpoint | Status | Notes |
|---|---|---|
| `POST /api/recommendations` | done | Contract in `frontend/API.md`. `?demo=true` returns canned tips. |
| `GET /api/competitors` | not built | Owned by the scraping branch; needs an adapter to the contract's shape. |
| `POST /api/analyze` | extra | Earlier one-call version (search + report). Not used by the frontend. |
| `GET /api/health` | done | Shows whether keys are set. |

Errors are returned as `{"error": "plain-English message"}`.
