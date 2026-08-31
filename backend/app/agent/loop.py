"""Gemini function-calling loop with streaming.

Emits an async iterator of dicts the FastAPI layer forwards over SSE:

    {"type": "text_delta", "text": "..."}
    {"type": "tool_use", "name": "...", "input": {...}, "id": "..."}
    {"type": "tool_result", "id": "...", "content": {...}, "is_error": bool}
    {"type": "message_stop", "stop_reason": "end_turn" | "user_input_required"}
    {"type": "done"}
    {"type": "error", "message": "..."}

The conversation contents (list[Content]) is mutated in place so the
caller can persist it across turns.
"""
from __future__ import annotations

import asyncio
import math
import re
import uuid
from typing import Any, AsyncIterator

from google import genai
from google.genai import types

from .tools import EXECUTORS, FUNCTION_DECLARATIONS, ToolContext


def _friendly_error(exc: Exception) -> str:
    """Turn a raw provider exception into one short line suitable for the UI.

    The Gemini SDK surfaces server errors as long JSON dumps; showing those
    verbatim leaks quota telemetry and confuses users. This mapping keeps
    the technical text out of the chat while still telling the user what
    to do next.
    """
    text = str(exc)
    if "429" in text or "RESOURCE_EXHAUSTED" in text:
        m = re.search(r"retry in (\d+(?:\.\d+)?)s", text)
        wait = f" Please try again in about {int(float(m.group(1)))} seconds." if m else ""
        return (
            "The daily request quota for this model has been reached."
            f"{wait} You can wait for the quota to reset, or add billing"
            " to raise the limit."
        )
    if "503" in text or "UNAVAILABLE" in text:
        return (
            "The model is temporarily unavailable due to high demand."
            " Please try again in a moment."
        )
    if "504" in text or "timeout" in text.lower() or "timed out" in text.lower():
        return "That request took too long. Please try again."
    if any(k in text for k in ("401", "403", "PERMISSION_DENIED", "UNAUTHENTICATED")):
        return "The service could not authenticate the request. Please contact the administrator."
    if "404" in text or "NOT_FOUND" in text:
        return "The configured model is not available. Please contact the administrator."
    if "INVALID_ARGUMENT" in text or ("400" in text and "invalid" in text.lower()):
        return "The model rejected the request. Try rephrasing your question."
    return "Something went wrong while contacting the model. Please try again."


def _scrub_nan(obj: Any) -> Any:
    """Convert NaN/Inf floats anywhere in a nested structure to None.

    pandas returns NaN for missing numeric cells even after .where(pd.notna,
    None) — the None only survives in object columns. Both consumers of
    a tool result reject NaN: Gemini's function_response payload is
    validated server-side (400 INVALID_ARGUMENT), and the browser's
    JSON.parse rejects the token itself. Scrubbing once at the tool
    boundary keeps everything downstream valid JSON.
    """
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    if isinstance(obj, dict):
        return {k: _scrub_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_scrub_nan(v) for v in obj]
    return obj

MAX_ITERATIONS = 12
MAX_TOKENS = 4096

# Free-tier Gemini regularly returns 503 UNAVAILABLE and other
# transient 5xx errors under load. Those are worth retrying. 429
# is a quota error — retrying just burns wall time without a chance
# of success until the quota window rolls over, so we don't retry it.
RETRY_STATUSES = (500, 502, 503, 504)
MAX_RETRIES = 2
BACKOFF_BASE_S = 1.5


def _is_retryable(exc: Exception) -> bool:
    text = str(exc)
    return any(str(code) in text for code in RETRY_STATUSES)


def build_config(system_prompt: str) -> types.GenerateContentConfig:
    """Config reused every turn — declares the tools + system prompt."""
    return types.GenerateContentConfig(
        system_instruction=system_prompt,
        max_output_tokens=MAX_TOKENS,
        tools=[
            types.Tool(function_declarations=FUNCTION_DECLARATIONS),
        ],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="AUTO")
        ),
    )


def _args_to_dict(args: Any) -> dict[str, Any]:
    """FunctionCall.args is a proto-mapping or dict; coerce to plain dict."""
    if args is None:
        return {}
    if isinstance(args, dict):
        return dict(args)
    try:
        return dict(args)
    except TypeError:
        return {}


async def run_agent(
    *,
    client: genai.Client,
    model: str,
    config: types.GenerateContentConfig,
    contents: list[types.Content],
    ctx: ToolContext,
) -> AsyncIterator[dict[str, Any]]:
    """Drive the tool-use loop, mutating `contents` in place.

    Caller appends the user's Content before invoking; on return the
    model's Content (and any function_response Content) has been
    appended too, so the next turn can pick up cleanly.
    """
    for _ in range(MAX_ITERATIONS):
        # Reset per-iteration state on every retry attempt so a failed
        # attempt's partial output can't leak into the next one. The
        # retained fc parts preserve each call's thought_signature that
        # Gemini requires when the call is echoed back next turn.
        text_chunks: list[str] = []
        fc_parts: list[types.Part] = []
        function_calls: list[tuple[str, Any]] = []
        emitted_events: list[dict[str, Any]] = []
        stream_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            text_chunks = []
            fc_parts = []
            function_calls = []
            emitted_events = []
            try:
                stream = await client.aio.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=config,
                )
                async for chunk in stream:
                    if not chunk.candidates:
                        continue
                    candidate = chunk.candidates[0]
                    if not candidate.content or not candidate.content.parts:
                        continue
                    for part in candidate.content.parts:
                        if getattr(part, "text", None):
                            text_chunks.append(part.text)
                            emitted_events.append(
                                {"type": "text_delta", "text": part.text}
                            )
                        if getattr(part, "function_call", None):
                            fc = part.function_call
                            call_id = f"{fc.name}-{uuid.uuid4().hex[:8]}"
                            function_calls.append((call_id, fc))
                            fc_parts.append(part)
                            emitted_events.append(
                                {
                                    "type": "tool_use",
                                    "id": call_id,
                                    "name": fc.name,
                                    "input": _args_to_dict(fc.args),
                                }
                            )
                stream_error = None
                break
            except Exception as e:
                stream_error = e
                if attempt < MAX_RETRIES and _is_retryable(e):
                    await asyncio.sleep(BACKOFF_BASE_S * (2**attempt))
                    continue
                break

        if stream_error is not None:
            yield {"type": "error", "message": _friendly_error(stream_error)}
            return

        # Flush the successful attempt's events now that we're not retrying.
        for ev in emitted_events:
            yield ev

        # Reconstruct the model's turn: text (concat) first, then the
        # raw function_call parts so their thought_signature survives.
        model_parts: list[types.Part] = []
        if text_chunks:
            model_parts.append(types.Part.from_text(text="".join(text_chunks)))
        model_parts.extend(fc_parts)
        if not model_parts:
            # Nothing at all came back — treat as end of turn to avoid loop.
            yield {"type": "message_stop", "stop_reason": "empty_response"}
            yield {"type": "done"}
            return
        contents.append(types.Content(role="model", parts=model_parts))

        if not function_calls:
            yield {"type": "message_stop", "stop_reason": "end_turn"}
            yield {"type": "done"}
            return

        # Execute every function call and gather function_response parts.
        response_parts: list[types.Part] = []
        pause_for_user: str | None = None

        for call_id, fc in function_calls:
            name = fc.name
            args = _args_to_dict(fc.args)
            executor = EXECUTORS.get(name)
            if executor is None:
                result = {"error": f"unknown tool: {name}"}
                is_error = True
            else:
                try:
                    result = await executor(args, ctx)
                    is_error = "error" in result
                except Exception as e:
                    result = {"error": f"{type(e).__name__}: {e}"}
                    is_error = True

            result = _scrub_nan(result)

            if name == "ask_user":
                pause_for_user = args.get("question", "")

            yield {
                "type": "tool_result",
                "id": call_id,
                "name": name,
                "content": result,
                "is_error": is_error,
            }
            response_parts.append(
                types.Part.from_function_response(name=name, response=result)
            )

        contents.append(types.Content(role="user", parts=response_parts))

        if pause_for_user is not None:
            yield {"type": "message_stop", "stop_reason": "user_input_required"}
            yield {"type": "done"}
            return

    yield {
        "type": "error",
        "message": (
            "The agent worked on this for a while but couldn't reach a final "
            "answer. Try breaking the question into smaller pieces."
        ),
    }
