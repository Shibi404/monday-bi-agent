# Monday.com Business Intelligence Agent

Conversational AI agent that answers founder-level business questions by querying monday.com boards (Deals + Work Orders) live.

## Architecture

```
Next.js chat UI ── SSE ──► FastAPI /chat ──► Gemini (function-calling loop)
                                                │
                                                ├── list_boards
                                                ├── get_board_schema
                                                ├── query_board  ──► monday.com GraphQL API
                                                └── run_analysis (pandas sandbox)
```

- **Backend**: Python 3.11+, FastAPI, google-genai SDK, pandas
- **Frontend**: Next.js 15, React 19, Tailwind, SSE streaming
- **Model**: `gemini-3.6-flash` (free tier: 20 requests/day per project — enough for a demo but not for heavy interactive testing; add billing to your Google AI Studio project for a much larger quota)
- **Data source**: monday.com GraphQL API (read-only)

## Repo layout

```
backend/       FastAPI service, Monday client, agent loop
frontend/      Next.js chat UI
data/          Original CSVs (gitignored; source of truth is monday.com)
```

## Local setup

### 1. monday.com

1. Create a free monday.com account.
2. Import both CSVs (`data/deals.csv`, `data/work_orders.csv`) as separate boards. Name them **Deals** and **Work Orders**. Let monday auto-detect column types; the agent tolerates messy typing on read.
3. Grab your API token: **Avatar (top-right) → Developers → My access tokens**.
4. Grab both board IDs from the board URLs (`monday.com/boards/{ID}`).

### 2. Google AI Studio (free)

1. Go to https://aistudio.google.com/apikey.
2. **Create API key** → copy the `AIza…` value. Free tier requires no billing setup.

### 3. Backend

```
cd backend
python -m venv .venv
.venv\Scripts\activate    # Windows PowerShell:  .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env    # then fill in tokens + board IDs
uvicorn app.main:app --reload --port 8000
```

### 4. Frontend

```
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

Open http://localhost:3000.

## Verify monday.com integration

Before running the agent, sanity-check the connection:

```
cd backend
python -m scripts.verify_monday
```

It prints board names, column schemas, the first few normalized rows from each board, and a data-quality summary. If this passes, the agent will work.

## Deploy

### Backend → Render

`backend/render.yaml` is a ready blueprint. From Render dashboard:

1. **New +** → **Blueprint** → point at this repo.
2. Render picks up `backend/render.yaml` and creates the web service.
3. Fill in the `sync: false` env vars in the dashboard:
   - `GOOGLE_API_KEY`
   - `MONDAY_API_TOKEN`
   - `MONDAY_BOARD_DEALS` (numeric board id)
   - `MONDAY_BOARD_WORK_ORDERS` (numeric board id)
   - `CORS_ORIGINS` — your Vercel URL, e.g. `https://monday-bi-agent.vercel.app`
4. First deploy takes ~3 min. Confirm `GET /health` returns `{"status":"ok",...}`.

### Frontend → Vercel

1. Import the repo on Vercel, set **Root Directory** to `frontend`.
2. Add env var `NEXT_PUBLIC_API_URL` = your Render backend URL.
3. Deploy. Vercel auto-detects Next.js.

See `DECISION_LOG.md` for architecture rationale, trade-offs, and the "leadership updates" interpretation.
