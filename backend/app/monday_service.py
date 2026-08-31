"""Higher-level facade the agent uses.

Combines MondayClient (raw GraphQL) with the normalizer, and adds a small
in-process cache so repeated tool calls in one conversation don't hammer
the API. Cache TTL is short (5 min) — good enough for a demo.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .monday_client import MondayClient
from .normalize import DataQuality, normalize_rows

SCHEMA_TTL_S = 300
DATA_TTL_S = 60  # keep fresh so demoed answers reflect Monday edits quickly


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


@dataclass
class MondayService:
    client: MondayClient
    board_aliases: dict[str, int] = field(default_factory=dict)
    _schema_cache: dict[int, _CacheEntry] = field(default_factory=dict)
    _rows_cache: dict[int, _CacheEntry] = field(default_factory=dict)

    def resolve_board(self, ref: str | int) -> int:
        """Accept a board ID (int/str) or alias (case-insensitive)."""
        if isinstance(ref, int):
            return ref
        s = str(ref).strip()
        if s.isdigit():
            return int(s)
        low = s.lower()
        for alias, bid in self.board_aliases.items():
            if alias.lower() == low:
                return bid
        raise ValueError(
            f"Unknown board reference {ref!r}. Known: {list(self.board_aliases)}"
        )

    async def list_boards(self) -> list[dict[str, Any]]:
        ids = list(self.board_aliases.values())
        boards = await self.client.list_boards(ids=ids or None)
        # attach aliases where known
        alias_by_id = {bid: alias for alias, bid in self.board_aliases.items()}
        for b in boards:
            b["alias"] = alias_by_id.get(int(b["id"]))
        return boards

    async def get_schema(self, board_ref: str | int) -> dict[str, Any]:
        bid = self.resolve_board(board_ref)
        now = time.time()
        cached = self._schema_cache.get(bid)
        if cached and cached.expires_at > now:
            return cached.value
        schema = await self.client.get_board_schema(bid)
        self._schema_cache[bid] = _CacheEntry(schema, now + SCHEMA_TTL_S)
        return schema

    async def query_board(
        self, board_ref: str | int, max_items: int | None = None
    ) -> tuple[list[dict[str, Any]], DataQuality, dict[str, Any]]:
        """Returns (rows, dq, schema)."""
        bid = self.resolve_board(board_ref)
        schema = await self.get_schema(bid)

        now = time.time()
        cached = self._rows_cache.get(bid)
        if cached and cached.expires_at > now:
            items = cached.value
        else:
            items = await self.client.query_board_raw(bid, max_items=max_items)
            self._rows_cache[bid] = _CacheEntry(items, now + DATA_TTL_S)

        rows, dq = normalize_rows(items, schema["columns"])
        return rows, dq, schema
