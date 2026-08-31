"""One-time startup wiring: build singletons + preload board schemas."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from anthropic import AsyncAnthropic

from .agent.prompt import build_system_prompt
from .agent.tools import ToolContext
from .config import Settings
from .monday_client import MondayClient
from .monday_service import MondayService


@dataclass
class AppState:
    settings: Settings
    anthropic: AsyncAnthropic
    monday_client: MondayClient
    monday_service: MondayService
    system_prompt: str
    # conversation_id -> {"messages": [...], "ctx": ToolContext}
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
    # Fetch once at startup; a schema TTL of 5 min in the service means
    # tools will use cached values for early tool calls too.
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

    anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)

    return AppState(
        settings=settings,
        anthropic=anthropic,
        monday_client=monday_client,
        monday_service=monday_service,
        system_prompt=system_prompt,
    )
