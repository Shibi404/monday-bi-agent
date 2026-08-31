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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from google.genai import types
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
        "model": s.settings.gemini_model,
        "boards": list(s.monday_service.board_aliases.keys()),
        "conversations": len(s.conversations),
    }


app.add_middleware(
    CORSMiddleware,
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
        conv = {"contents": [], "ctx": s.new_context()}
        s.conversations[conv_id] = conv

    conv["contents"].append(
        types.Content(role="user", parts=[types.Part.from_text(text=req.message)])
    )

    async def event_stream() -> AsyncIterator[dict]:
        yield {
            "event": "start",
            "data": json.dumps({"conversation_id": conv_id}),
        }
        try:
            async for ev in run_agent(
                client=s.genai_client,
                model=s.settings.gemini_model,
                config=s.gen_config,
                contents=conv["contents"],
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
