# Decision Log — Monday.com BI Agent

## Key assumptions

- **The agent must query monday live on every conversation, not on a pre-loaded snapshot.** The prompt is explicit about this; my in-process cache (schema 5 min, rows 60 s) is per-instance and short so demoed answers reflect edits made in monday quickly.
- **Masked money values are structurally correct.** Numbers look inflated (deals in the hundreds of millions) because they're masked, but ratios, rankings, and time trends are meaningful — so the agent reasons about proportions rather than trying to state absolute revenue.
- **Currency is INR.** Amount columns in the Work Orders board name "Rupees" explicitly; Deals values are consistent in scale. The agent formats as ₹ lakh / crore for readability.
- **The two boards are the whole world.** No cross-referencing to CRM, ERP, or a warehouse. Anything the agent cannot answer from Deals + Work Orders it says so, rather than fabricating.
- **Fiscal year = calendar year unless the user says otherwise.** Skylark's FY runs Apr–Mar in India, but no user context tells the agent this; the safer default is calendar quarters with an assumption stated inline.
- **"Owner code" columns are opaque.** OWNER_001, WOCOMPANY_002, etc. are not real names — the agent uses the codes verbatim rather than inventing personas.

## Trade-offs

**Gemini 2.5 Flash over Claude / GPT.** Free-tier access (250 req/day) was the deciding factor for a demo assignment — the reviewer never pays and never sees a rate limit if they poke around. Flash handles the tool loop reliably and its function-calling format is straightforward. Cost: the SDK's tool-calling response objects are slightly less structured than Anthropic's (no per-call ID, args come back as proto mappings) — the loop mints IDs and coerces args explicitly. For production use with paying users I'd re-evaluate against Claude Sonnet, where the agent's tool orchestration tends to be steadier on ambiguous prompts.

**REST/GraphQL over MCP.** monday.com ships an MCP server, but for a single well-scoped integration it adds a process and a permissions ceremony without giving me anything the GraphQL API doesn't. Direct httpx + a tiny normalizer is ~150 lines and completely transparent when things break. If this agent grew to talk to five SaaS tools, I'd swap in MCP for the interface consistency.

**Rich preloaded system prompt over discovery.** At startup the backend fetches both board schemas and embeds them into the system prompt. This costs one round-trip per boot but saves the agent 2–3 tool calls on every conversation ("list boards", "get schema for X", "get schema for Y") and produces materially faster answers. Cost: if a monday user renames a column mid-session, the agent won't notice until the process restarts. Acceptable for a demo; in production I'd refresh the prompt on a 5-min timer or invalidate it via a webhook.

**Per-conversation pandas sandbox over a SQL layer.** For 500 rows total, loading both boards into DataFrames and letting Claude write pandas is faster to build and lets the agent handle any question shape (joins, aggregations, ranking, ratios). It doesn't scale past a few thousand rows per board — at that point I'd stand up DuckDB or a real warehouse and give the agent a `run_sql` tool instead.

**`exec` for the analysis tool.** The pandas sandbox is unsandboxed Python. That is fine because the model is Claude and the code runs in the backend process on Render — there is no user-supplied Python path. The trade-off is real: a compromised model could exfiltrate env vars. For a prototype I accept it and note it here; for production this tool would run in a subprocess with a restricted namespace (no `os`, no `open`, no network) or, better, be replaced by a structured tool that dispatches known pandas operations from a spec rather than executing free-form code.

**In-memory conversation state.** No Redis, no Postgres. State lives on one backend replica; a redeploy wipes conversations. Fine for a single-user demo — I'd move to Redis the moment there was more than one concurrent user or a real uptime target.

**SSE, not WebSockets.** SSE is one-way and ergonomic under HTTP; `sse-starlette` on the server and `fetch` + `ReadableStream` on the client are ~30 lines total. The agent never needs to receive mid-stream input from the user, so bidirectional isn't earning its keep.

**Data-quality is a citable artifact, not a silent filter.** The normalizer never drops rows for being messy — it coerces to `None` and records per-column null / parse-error counts. The tool response gives Claude that summary, and the system prompt tells it to caveat inline when it matters. Rationale: "we found 340 open deals" is more useful than "we found 289 open deals (silently excluded 51 with missing close dates)."

**CORS wide open.** `allow_origins=["*"]` for the prototype; `CORS_ORIGINS` env var is wired up but not enforced today. Would tighten in production.

## "Leadership updates" interpretation

I interpreted this as **a structured brief the agent can produce on demand**, not a scheduled email or PDF. When the user says "leadership update", "weekly brief", or "board update", the agent generates a five-section markdown report: pipeline snapshot (open count + value by stage), movers (biggest / most-recently-changed deals), execution status (WOs in progress / completed / blocked, with overdue call-outs), sector view (pipeline value + execution load), and data caveats (one line per material data-quality issue).

**Why on-demand rather than scheduled:** founders don't consume updates on a fixed cadence — they want them before the board meeting, before the investor call, before the Monday standup. A conversational agent that reliably assembles the brief in ten seconds is more useful than one that emails yesterday's version overnight. The prompt scaffolds the sections but lets the agent adapt: if there are zero blocked WOs this week, that section shrinks to one line rather than being padded.

**What I'd add with more time:** a "publish" mode that renders the brief as a shareable HTML page (Artifact-style) with the underlying tables inlined, plus a `/brief` shortcut endpoint the frontend calls to skip the chat framing entirely.

## What I'd do with more time

- **Persistence:** Redis for conversation state; Postgres for chat transcripts so founders can revisit past analyses.
- **A structured analysis tool** instead of `run_analysis` — a schema of allowed pandas ops the agent fills in — closing the security gap.
- **Follow-up prompts / drill-downs** the frontend surfaces after each answer ("break down by owner", "show me the deals behind this number").
- **Webhook-driven cache invalidation** so column renames and value edits in monday reach the agent immediately.
- **Eval harness:** a set of 20 golden questions with expected answer patterns, run on every PR. Right now correctness relies on manual spot-checks.
- **Charts.** For most BI answers a small inline chart (bar of pipeline by stage, line of deals-by-close-quarter) is worth a paragraph of text. I'd add a `render_chart` tool that returns a Vega-Lite spec the frontend renders.
