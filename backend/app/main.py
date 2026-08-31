"""FastAPI entrypoint. Exposes:

    GET  /health           liveness probe
    POST /chat             SSE stream of agent events for one user turn
    POST /reset            drop a conversation's history + df cache
"""
from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .agent.loop import run_agent
from .bootstrap import AppState, build_app_state
from .config import load_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    state = await build_app_state(settings)
    app.state.app_state = state
    try:
        yield
    finally:
        await state.aclose()


app = FastAPI(title="Monday BI Agent", lifespan=lifespan)


def _state(app: FastAPI) -> AppState:
    return app.state.app_state  # type: ignore[attr-defined]


@app.get("/health")
async def health():
    s = _state(app)
    return {
        "status": "ok",
        "model": s.settings.anthropic_model,
        "boards": list(s.monday_service.board_aliases.keys()),
        "conversations": len(s.conversations),
    }


app.add_middleware(
    CORSMiddleware,
    # Configured after app is created because we need settings; middleware
    # is added in the startup hook below.
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = None


class ResetRequest(BaseModel):
    conversation_id: str


@app.post("/reset")
async def reset(req: ResetRequest):
    s = _state(app)
    s.conversations.pop(req.conversation_id, None)
    return {"ok": True}


@app.post("/chat")
async def chat(req: ChatRequest):
    s = _state(app)

    conv_id = req.conversation_id or str(uuid.uuid4())
    conv = s.conversations.get(conv_id)
    if conv is None:
        conv = {"messages": [], "ctx": s.new_context()}
        s.conversations[conv_id] = conv

    conv["messages"].append({"role": "user", "content": req.message})

    async def event_stream() -> AsyncIterator[dict]:
        # Kickoff event so the client learns its conversation_id
        yield {
            "event": "start",
            "data": json.dumps({"conversation_id": conv_id}),
        }
        try:
            async for ev in run_agent(
                client=s.anthropic,
                model=s.settings.anthropic_model,
                system_prompt=s.system_prompt,
                messages=conv["messages"],
                ctx=conv["ctx"],
            ):
                yield {
                    "event": ev.get("type", "message"),
                    "data": json.dumps(ev, default=str, ensure_ascii=False),
                }
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"message": f"stream failed: {e}"}),
            }

    return EventSourceResponse(event_stream())
