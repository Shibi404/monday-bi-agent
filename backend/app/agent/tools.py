"""Tool schemas and executors used by the Claude tool-use loop.

Tools are intentionally small and composable so the agent chooses
its own path:

    list_boards        -> discover what boards exist
    get_board_schema   -> see columns before querying
    query_board        -> pull normalized rows + data-quality report
    run_analysis       -> pandas sandbox for aggregations / joins
    ask_user           -> pause and request clarification

Every tool returns a JSON-serialisable dict; errors are caught and
returned as {"error": "..."} so the agent can recover.
"""
from __future__ import annotations

import io
import json
import textwrap
import traceback
from contextlib import redirect_stdout
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

import pandas as pd

from ..monday_service import MondayService


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "list_boards",
        "description": (
            "List the monday.com boards this agent can read. Use once at "
            "the start of a session to see what data is available. Each board "
            "has a numeric id, a human-readable name, an alias ('deals' or "
            "'work_orders') for convenience, and an item count."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_board_schema",
        "description": (
            "Return the columns of a board so you can pick the right ones "
            "for filtering or aggregation. Call this BEFORE query_board if "
            "you're not already sure which columns exist. Returns "
            "{name, columns: [{title, type, id}]}."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "board": {
                    "type": "string",
                    "description": "Board alias ('deals' or 'work_orders') or numeric ID.",
                }
            },
            "required": ["board"],
        },
    },
    {
        "name": "query_board",
        "description": (
            "Fetch normalized rows from a board and a data-quality summary "
            "in one call. Rows are keyed by column TITLE (as shown in "
            "monday). Dates come back as ISO strings, numbers as floats, "
            "empty/nullish values as null. The data_quality field lists "
            "columns with missing values and any parse errors so you can "
            "caveat the answer. Loads the full board unless max_items is set."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "board": {
                    "type": "string",
                    "description": "Board alias ('deals' or 'work_orders') or numeric ID.",
                },
                "max_items": {
                    "type": "integer",
                    "description": "Optional cap on rows fetched (leave off for full board).",
                    "minimum": 1,
                },
            },
            "required": ["board"],
        },
    },
    {
        "name": "run_analysis",
        "description": (
            "Run Python + pandas over the boards to compute aggregates, "
            "filters, joins, or any analysis that isn't a straight row "
            "listing. The environment already has:\n"
            "  - pd (pandas)\n"
            "  - deals_df, work_orders_df: DataFrames of the FULL boards, "
            "already normalized (columns keyed by title).\n"
            "Assign your final answer to a variable named `result` (any "
            "JSON-serialisable value, or a DataFrame — the first 50 rows "
            "will be returned). print()s are also captured.\n\n"
            "Example:\n"
            "    open_deals = deals_df[deals_df['Deal Status'] == 'Open']\n"
            "    result = open_deals.groupby('Sector/service')['Masked Deal value'].sum().to_dict()\n"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute. Set `result` to the value you want back.",
                }
            },
            "required": ["code"],
        },
    },
    {
        "name": "ask_user",
        "description": (
            "Ask the user a clarifying question when the request is genuinely "
            "ambiguous (e.g. 'this quarter' with no fiscal-year context, or a "
            "sector name that doesn't match any value). Prefer making a "
            "reasonable assumption and stating it — only use this tool when "
            "an assumption would materially change the answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
            },
            "required": ["question"],
        },
    },
]


@dataclass
class ToolContext:
    """State shared across tool calls within one conversation."""

    service: MondayService
    # DataFrame cache so run_analysis doesn't refetch every call
    dfs: dict[str, pd.DataFrame]
    # Track quality reports so the agent's answers can cite them
    last_quality: dict[str, dict[str, Any]]

    async def ensure_df(self, alias: str) -> pd.DataFrame:
        if alias in self.dfs:
            return self.dfs[alias]
        rows, dq, _ = await self.service.query_board(alias)
        df = pd.DataFrame(rows)
        self.dfs[alias] = df
        self.last_quality[alias] = dq.summary()
        return df


ToolExecutor = Callable[[dict[str, Any], ToolContext], Awaitable[dict[str, Any]]]


async def _list_boards(_args: dict, ctx: ToolContext) -> dict:
    boards = await ctx.service.list_boards()
    return {"boards": boards}


async def _get_board_schema(args: dict, ctx: ToolContext) -> dict:
    schema = await ctx.service.get_schema(args["board"])
    return {
        "id": schema["id"],
        "name": schema["name"],
        "items_count": schema.get("items_count"),
        "columns": [
            {"title": c["title"], "type": c["type"], "id": c["id"]}
            for c in schema["columns"]
        ],
    }


async def _query_board(args: dict, ctx: ToolContext) -> dict:
    rows, dq, schema = await ctx.service.query_board(
        args["board"], max_items=args.get("max_items")
    )
    # Cache the df for later run_analysis calls
    alias = args["board"] if not str(args["board"]).isdigit() else schema["name"]
    ctx.dfs[str(alias).lower().replace(" ", "_")] = pd.DataFrame(rows)
    ctx.last_quality[str(alias).lower().replace(" ", "_")] = dq.summary()

    # Cap the payload back to Claude to avoid blowing up context.
    # The full DataFrame stays available inside run_analysis.
    preview = rows[:20]
    return {
        "board": schema["name"],
        "row_count": len(rows),
        "preview_rows": preview,
        "preview_note": (
            f"Showing first {len(preview)} of {len(rows)} rows. "
            "Use run_analysis for aggregations over the full dataset."
        ),
        "data_quality": dq.summary(),
    }


def _serialise_result(result: Any) -> Any:
    if isinstance(result, pd.DataFrame):
        head = result.head(50).where(pd.notna(result.head(50)), None)
        return {
            "type": "dataframe",
            "shape": list(result.shape),
            "columns": list(result.columns),
            "rows": head.to_dict(orient="records"),
            "truncated": len(result) > 50,
        }
    if isinstance(result, pd.Series):
        return {
            "type": "series",
            "length": len(result),
            "data": result.head(50).to_dict(),
            "truncated": len(result) > 50,
        }
    try:
        json.dumps(result)
        return result
    except TypeError:
        return str(result)


async def _run_analysis(args: dict, ctx: ToolContext) -> dict:
    # Pre-load both boards so DataFrames are ready
    for alias in ("deals", "work_orders"):
        await ctx.ensure_df(alias)

    code = textwrap.dedent(args["code"])
    env: dict[str, Any] = {
        "pd": pd,
        "deals_df": ctx.dfs.get("deals"),
        "work_orders_df": ctx.dfs.get("work_orders"),
    }
    stdout_buf = io.StringIO()
    try:
        with redirect_stdout(stdout_buf):
            exec(code, env, env)
    except Exception:
        return {
            "error": "execution failed",
            "traceback": traceback.format_exc(limit=3),
            "stdout": stdout_buf.getvalue(),
        }

    result_val = env.get("result", None)
    return {
        "stdout": stdout_buf.getvalue(),
        "result": _serialise_result(result_val) if result_val is not None else None,
    }


async def _ask_user(args: dict, _ctx: ToolContext) -> dict:
    # Actual UX is handled by the loop / frontend; the tool result just
    # confirms the question was accepted. The loop treats this as a
    # signal to yield the question to the user and pause.
    return {"asked": args["question"]}


EXECUTORS: dict[str, ToolExecutor] = {
    "list_boards": _list_boards,
    "get_board_schema": _get_board_schema,
    "query_board": _query_board,
    "run_analysis": _run_analysis,
    "ask_user": _ask_user,
}
