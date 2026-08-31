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
import uuid
from typing import Any, AsyncIterator

from google import genai
from google.genai import types

from .tools import EXECUTORS, FUNCTION_DECLARATIONS, ToolContext

MAX_ITERATIONS = 12
MAX_TOKENS = 4096

# Free-tier Gemini regularly returns 503/429/500 under load. Retry
# transient failures with exponential backoff before giving up.
RETRY_STATUSES = (429, 500, 502, 503, 504)
MAX_RETRIES = 3
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
        text_chunks: list[str] = []
        # Preserve the original Part objects for function calls — they
        # carry a thought_signature the API requires when the same call
        # is echoed back on the next turn. Rebuilding via
        # types.Part(function_call=fc) drops that signature and Gemini
        # rejects the follow-up with a 400.
        fc_parts: list[types.Part] = []
        # Pair each FunctionCall with the id we emitted so tool_result
        # events can be matched back to their tool_use on the frontend.
        function_calls: list[tuple[str, Any]] = []

        stream_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            text_chunks = []
            fc_parts = []
            function_calls = []
            emitted_events: list[dict[str, Any]] = []  # buffer to avoid double-emit on retry
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
            yield {"type": "error", "message": f"model call failed: {stream_error}"}
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

    yield {"type": "error", "message": f"agent exceeded {MAX_ITERATIONS} iterations"}
