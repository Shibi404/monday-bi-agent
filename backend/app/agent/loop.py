"""Claude tool-use loop with streaming events.

Emits an async iterator of dicts the FastAPI layer forwards over SSE:

    {"type": "text_delta", "text": "..."}
    {"type": "tool_use", "name": "...", "input": {...}, "id": "..."}
    {"type": "tool_result", "id": "...", "content": {...}, "is_error": bool}
    {"type": "message_stop", "stop_reason": "end_turn" | "tool_use" | ...}
    {"type": "done"}
    {"type": "error", "message": "..."}
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic

from .tools import EXECUTORS, TOOL_SCHEMAS, ToolContext

MAX_ITERATIONS = 12
MAX_TOKENS = 4096


def _tool_result_content(payload: dict) -> str:
    """Serialise a tool executor's dict to a string for the tool_result block."""
    try:
        return json.dumps(payload, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(payload)


async def run_agent(
    *,
    client: AsyncAnthropic,
    model: str,
    system_prompt: str,
    messages: list[dict[str, Any]],
    ctx: ToolContext,
) -> AsyncIterator[dict[str, Any]]:
    """Drive the tool-use loop, mutating `messages` in place.

    `messages` is the running conversation for this turn — the caller
    appends the user's new message before invoking. On success the
    assistant's final response(s) are appended too, so the caller can
    persist it for the next turn.
    """
    for _ in range(MAX_ITERATIONS):
        assistant_blocks: list[dict[str, Any]] = []
        stop_reason: str | None = None

        try:
            async with client.messages.stream(
                model=model,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                tools=TOOL_SCHEMAS,
                messages=messages,
            ) as stream:
                async for event in stream:
                    et = event.type
                    if et == "content_block_start":
                        block = event.content_block
                        if block.type == "tool_use":
                            # placeholder; we'll fill input from the final message
                            pass
                    elif et == "text":
                        yield {"type": "text_delta", "text": event.text}
                    elif et == "message_stop":
                        pass  # handled below

                final = await stream.get_final_message()
                stop_reason = final.stop_reason
                for block in final.content:
                    if block.type == "text":
                        assistant_blocks.append({"type": "text", "text": block.text})
                    elif block.type == "tool_use":
                        assistant_blocks.append(
                            {
                                "type": "tool_use",
                                "id": block.id,
                                "name": block.name,
                                "input": block.input,
                            }
                        )
                        yield {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
        except Exception as e:
            yield {"type": "error", "message": f"model call failed: {e}"}
            return

        messages.append({"role": "assistant", "content": assistant_blocks})

        if stop_reason != "tool_use":
            yield {"type": "message_stop", "stop_reason": stop_reason}
            yield {"type": "done"}
            return

        # Execute every tool_use block, collecting tool_result blocks
        tool_results: list[dict[str, Any]] = []
        pause_for_user: str | None = None
        for block in assistant_blocks:
            if block["type"] != "tool_use":
                continue
            name = block["name"]
            executor = EXECUTORS.get(name)
            if executor is None:
                result = {"error": f"unknown tool: {name}"}
                is_error = True
            else:
                try:
                    result = await executor(block["input"] or {}, ctx)
                    is_error = "error" in result
                except Exception as e:
                    result = {"error": f"{type(e).__name__}: {e}"}
                    is_error = True

            if name == "ask_user":
                pause_for_user = block["input"].get("question", "")

            yield {
                "type": "tool_result",
                "id": block["id"],
                "name": name,
                "content": result,
                "is_error": is_error,
            }
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": _tool_result_content(result),
                    "is_error": is_error,
                }
            )

        messages.append({"role": "user", "content": tool_results})

        if pause_for_user is not None:
            # Yield control back to the user; the next user message will resume.
            yield {"type": "message_stop", "stop_reason": "user_input_required"}
            yield {"type": "done"}
            return

    yield {"type": "error", "message": f"agent exceeded {MAX_ITERATIONS} iterations"}
