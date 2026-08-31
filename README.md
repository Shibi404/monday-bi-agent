# Monday.com Business Intelligence Agent

Conversational AI agent that answers founder-level business questions by querying monday.com boards (Deals + Work Orders) live.

## Architecture

```
Next.js chat UI ── SSE ──► FastAPI /chat ──► Claude (tool-use loop)
                                                │
                                                ├── list_boards
                                                ├── get_board_schema
                                                ├── query_board  ──► monday.com GraphQL API
                                                └── run_analysis (pandas sandbox)
```

- **Backend**: Python 3.11+, FastAPI, Anthropic SDK, pandas
- **Frontend**: Next.js 15, React 19, Tailwind, SSE streaming
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

### 2. Backend

```
cd backend
python -m venv .venv
.venv\Scripts\activate    # Windows PowerShell:  .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env    # then fill in tokens + board IDs
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

Open http://localhost:3000.

## Deploy

- **Backend**: Render (Docker or Python). Set env vars from `.env.example`.
- **Frontend**: Vercel. Set `NEXT_PUBLIC_API_URL` to the Render URL.

See `DECISION_LOG.md` for architecture rationale, trade-offs, and the "leadership updates" interpretation.
