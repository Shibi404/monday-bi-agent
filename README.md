# Monday.com Business Intelligence Agent

Conversational AI agent that answers founder-level business questions by querying monday.com boards (Deals + Work Orders) live. Ask "how's our pipeline in Mining this quarter?" or "prepare a leadership update for this week" and it fetches the relevant boards, cleans messy data, runs the numbers, and answers with insight — not just rows.

- **Live demo:** https://monday-bi-agent-seven.vercel.app
- **Backend health:** https://monday-bi-agent-backend-tjli.onrender.com/health

---

## Architecture

```
┌────────────────────────────┐        ┌─────────────────────────────────────┐
│     Next.js 15 chat UI     │        │      FastAPI  (Python 3.11+)        │
│  (React 19 · Tailwind)     │        │                                     │
│                            │        │   ┌──────────────────────────────┐  │
│  input ─▶ POST /chat ──────┼──SSE──▶│   │        Agent loop            │  │
│                            │        │   │  ─ system prompt (preloaded  │  │
│  text_delta ◀──────────────┼────────┤   │    with both board schemas)  │  │
│  error / done ◀────────────┼────────┤   │  ─ Gemini function calling   │  │
│                            │        │   │  ─ retry on 5xx w/ backoff   │  │
└────────────────────────────┘        │   └────┬─────────────────────────┘  │
                                      │        │                            │
                                      │        ▼   tools                    │
                                      │   ┌─────────────────────────────┐   │
                                      │   │ list_boards                 │   │
                                      │   │ get_board_schema            │   │
                                      │   │ query_board  ─── normalize ─┼───┼──► monday.com GraphQL v2024-10
                                      │   │ run_analysis (pandas exec)  │   │       (read-only, cursor pagination)
                                      │   │ ask_user                    │   │
                                      │   └─────────────────────────────┘   │
                                      └─────────────────────────────────────┘
```

**Layers, in one line each:**

| Layer | What it does |
|---|---|
| **Frontend** (`frontend/`) | Chat UI in Next.js 15 + React 19 + Tailwind. Streams tokens via SSE, renders assistant markdown, calls `/reset` to wipe conversation state. |
| **API** (`backend/app/main.py`) | FastAPI. Two routes: `POST /chat` (SSE stream) and `POST /reset`. In-memory session store keyed by `conversation_id`. |
| **Agent loop** (`backend/app/agent/loop.py`) | Drives Gemini's function-calling loop. Preserves `thought_signature` on function-call parts across turns. Retries transient 5xx with exponential backoff. Emits typed events (`text_delta` / `tool_use` / `tool_result` / `done` / `error`). |
| **Tools** (`backend/app/agent/tools.py`) | Five small tools the model can call: `list_boards`, `get_board_schema`, `query_board`, `run_analysis`, `ask_user`. |
| **Monday client** (`backend/app/monday_client.py`, `monday_service.py`) | Async GraphQL wrapper over monday.com's `boards`, `items_page`, and `next_items_page` queries. Service layer adds board-alias resolution and a small in-process TTL cache (schema 5 min, rows 60 s). |
| **Normalizer** (`backend/app/normalize.py`) | Coerces raw column values to typed dicts (ISO dates, floats, cleaned strings), collapses nullish tokens (`N/A`, `TBD`, `—`), and reports per-column null / parse-error counts as a `DataQuality` summary the agent can cite. |
| **Model** | `gemini-3.6-flash` — free tier gives ~20 requests/day per project. Configurable via `GEMINI_MODEL`. |

---

## Request flow — a single user turn

Take **"How's our Mining pipeline this quarter?"** as an example:

1. **Frontend → API.** Chat UI posts `{ message, conversation_id? }` to `/chat`. FastAPI resolves or creates a `conversation_id` and appends the user's message to the running `list[Content]` for that conversation.
2. **Kickoff SSE event.** Server yields `{event: "start", data: {conversation_id}}` so the client can persist the id on first turn.
3. **Agent loop iteration 1 — model turn.** `run_agent` calls `client.aio.models.generate_content_stream`. The system prompt already lists both board schemas (preloaded at startup), so the model rarely needs `get_board_schema`. Streamed text tokens are yielded live as `text_delta` events. When Gemini emits a `function_call` part, its original `Part` object is retained (preserves `thought_signature`).
4. **Tool execution.** The model probably chose `run_analysis` with a small pandas snippet like:
   ```python
   from datetime import date
   q_start = date(2025, 10, 1); q_end = date(2025, 12, 31)
   open_deals = deals_df[deals_df["Deal Status"] == "Open"]
   mining = open_deals[open_deals["Sector/service"].str.contains("Mining", case=False, na=False)]
   result = {
       "count": int(len(mining)),
       "total_value": float(mining["Masked Deal value"].sum()),
       "by_stage": mining.groupby("Deal Stage")["Masked Deal value"].sum().to_dict(),
   }
   ```
   The tool runs the code inside a sandbox with `deals_df` / `work_orders_df` DataFrames already loaded from `MondayService.query_board`. NaN floats are scrubbed to `null` before the result is serialized (Gemini rejects NaN with `400 INVALID_ARGUMENT`, browser `JSON.parse` rejects it too).
5. **Agent loop iteration 2 — model responds.** The function_response is appended to `contents` and Gemini is called again with the full history. This time the model streams a written answer citing the numbers and the data-quality caveats (e.g. "12 of 38 open Mining deals were missing a close date — excluded from the timing view").
6. **Stream close.** `run_agent` yields `message_stop` then `done`. Frontend flips the assistant message out of `streaming` state.

Every non-trivial question follows this shape: model → tool → model → text. Simple metrics resolve in one tool call; multi-board joins may take two or three iterations.

---

## Design highlights

- **Preloaded schemas in the system prompt.** Backend fetches both boards' columns at startup and embeds them into the system prompt. Saves 2–3 tool calls per conversation and lets the model use column titles verbatim without guessing.
- **Data-quality is a citable artifact.** The normalizer never drops rows for being messy — it coerces missing/parse-fail values to `None` and hands the agent a summary of per-column null / parse-error counts. The prompt tells the agent to caveat inline when it matters, so answers read like "we found N open deals; K were excluded because they were missing …" instead of quietly filtering.
- **Pandas sandbox for aggregation.** `run_analysis` gives the model `deals_df` and `work_orders_df` pre-loaded and lets it write ad-hoc pandas. Much faster to build than a fixed set of analytic tools and covers any query shape (joins, group-bys, ranking, ratios) at the ~500-row scale of this dataset.
- **Scope guardrail.** System prompt has an explicit Scope section listing what's in ("our pipeline in Mining") and what's out ("who is the PM of India"). Out-of-scope requests get a one-line polite decline; no tools are called.
- **Friendly errors.** Every provider exception passes through `_friendly_error` in the loop, which maps 429 (with a retry-in-N hint), 503, 504, 401/403, 404, 400, and timeouts to a short actionable line each. Raw JSON dumps never reach the UI.
- **Retry with buffered events.** Transient 5xx from Gemini's free tier are retried up to 2× with exponential backoff. To keep the SSE stream consistent, per-attempt events are buffered and only flushed on the successful attempt so retries never duplicate text.
- **`thought_signature` preservation.** Thinking-capable Gemini models stamp a signature on function-call parts that must be echoed back on the next turn. The loop keeps the original `Part` object rather than reconstructing it, so multi-tool loops don't fail with `400 Function call is missing a thought_signature`.

---

## Repo layout

```
backend/
  app/
    agent/
      loop.py             # Gemini function-calling loop, retry, error mapping
      prompt.py           # System prompt builder (embeds preloaded schemas)
      tools.py            # 5 tools + pandas sandbox executor + ToolContext
    monday_client.py      # Async GraphQL wrapper (list_boards, get_board_schema, query_board_raw)
    monday_service.py     # Aliases + TTL cache on top of MondayClient
    normalize.py          # Column-value coercion + DataQuality summaries
    config.py             # Settings dataclass; strips env whitespace defensively
    bootstrap.py          # One-time startup wiring (schemas, prompt, gen config, singletons)
    main.py               # FastAPI app, /chat SSE, /reset, /health, NaN scrubber
  scripts/
    verify_monday.py      # Smoke test — proves token + board IDs work
  render.yaml             # Render blueprint (pinned Python 3.11.9)
  requirements.txt
  .env.example

frontend/
  app/
    layout.tsx            # Root layout + metadata
    page.tsx              # Chat page (state, send loop, mic, model picker, new-chat confirm)
    globals.css           # Cream palette tokens, slim scrollbar, markdown styles
    stream.ts             # SSE consumer (CRLF-tolerant, multi-line data)
    types.ts              # AgentEvent + ChatMessage
  components/
    Message.tsx           # Bubble renderer (markdown + thinking + error callout)
    ThinkingIndicator.tsx # Rotating pulse: Thinking / Brainstorming / Reasoning / …
    ModelPicker.tsx       # Custom dropdown (chip + popover, ⌘K-ish)
    DialogBox.tsx         # Reusable confirm modal (position:fixed scroll lock)
  package.json
  .env.example

data/                     # Original CSVs (gitignored; monday.com is source of truth)
DECISION_LOG.md           # Assumptions, trade-offs, "leadership updates" interpretation
```

---

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

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1     # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # then fill in tokens + board IDs
uvicorn app.main:app --reload --port 8000
```

### 4. Frontend

```powershell
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

Open http://localhost:3000.

---

## Verify monday.com integration

Before running the agent, sanity-check the connection:

```
cd backend
python -m scripts.verify_monday
```

It prints board names, column schemas, the first few normalized rows from each board, and a data-quality summary. If this passes, the agent will work.

---

## Environment variables

Backend (`backend/.env`):

| Var | Required | Default | Notes |
|---|---|---|---|
| `GOOGLE_API_KEY` | ✅ | — | From https://aistudio.google.com/apikey |
| `MONDAY_API_TOKEN` | ✅ | — | monday.com personal API token |
| `MONDAY_BOARD_DEALS` | ✅ | — | Numeric board id |
| `MONDAY_BOARD_WORK_ORDERS` | ✅ | — | Numeric board id |
| `GEMINI_MODEL` | — | `gemini-3.6-flash` | Override to try another model |
| `CORS_ORIGINS` | — | `http://localhost:3000` | Comma-separated list |

Frontend (`frontend/.env.local`):

| Var | Required | Default | Notes |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | ✅ | `http://localhost:8000` | Backend base URL |

---

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

---

## Known limits

- **Gemini free tier caps at ~20 requests/day per project.** Enough for a demo but not heavy interactive testing. Add billing to raise it, or override `GEMINI_MODEL` in `.env`.
- **`run_analysis` executes free-form Python.** The model is Claude/Gemini and the code runs in the backend process — there's no user-supplied Python path — but a compromised model could exfiltrate env vars. For prod I'd replace with a structured operation dispatcher.
- **Conversation state is in-memory.** A backend redeploy wipes chats. Fine for a single-user demo; Redis is the obvious upgrade.
- **~500 rows per board.** The pandas sandbox is snappy at this scale. Past a few thousand rows per board I'd move to DuckDB and give the agent a `run_sql` tool.

See `DECISION_LOG.md` for the full trade-off rationale, the "leadership updates" interpretation, and what I'd add with more time.
