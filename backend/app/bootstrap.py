"""One-time startup wiring: build singletons + preload board schemas."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import types

from .agent.loop import build_config
from .agent.prompt import build_system_prompt
from .agent.tools import ToolContext
from .config import Settings
from .monday_client import MondayClient
from .monday_service import MondayService


@dataclass
class AppState:
    settings: Settings
    genai_client: genai.Client
    gen_config: types.GenerateContentConfig
    monday_client: MondayClient
    monday_service: MondayService
    system_prompt: str
    # conversation_id -> {"contents": list[Content], "ctx": ToolContext}
    conversations: dict[str, dict[str, Any]] = field(default_factory=dict)

    async def aclose(self) -> None:
        await self.monday_client.aclose()

    def new_context(self) -> ToolContext:
        return ToolContext(
            service=self.monday_service,
            dfs={},
            last_quality={},
        )


async def build_app_state(settings: Settings) -> AppState:
    monday_client = MondayClient(settings.monday_api_token)
    monday_service = MondayService(
        client=monday_client,
        board_aliases={
            "deals": settings.monday_board_deals,
            "work_orders": settings.monday_board_work_orders,
        },
    )

    # Preload schemas so the system prompt can list columns.
    summaries = []
    for alias, bid in monday_service.board_aliases.items():
        try:
            schema = await monday_service.get_schema(alias)
            summaries.append(
                {
                    "alias": alias,
                    "id": schema["id"],
                    "name": schema["name"],
                    "items_count": schema.get("items_count"),
                    "columns": [
                        {"title": c["title"], "type": c["type"]}
                        for c in schema["columns"]
                    ],
                }
            )
        except Exception as e:
            summaries.append(
                {
                    "alias": alias,
                    "id": bid,
                    "name": "(unavailable)",
                    "items_count": None,
                    "columns": [],
                    "error": str(e),
                }
            )

    system_prompt = build_system_prompt(summaries)
    gen_config = build_config(system_prompt)

    genai_client = genai.Client(api_key=settings.google_api_key)

    return AppState(
        settings=settings,
        genai_client=genai_client,
        gen_config=gen_config,
        monday_client=monday_client,
        monday_service=monday_service,
        system_prompt=system_prompt,
    )
