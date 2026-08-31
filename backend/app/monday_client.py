"""monday.com GraphQL client. Read-only.

The board schema and items_page queries follow monday's 2024-10 API version.
Pagination uses cursors (items_page returns up to 500 items per call).
"""
from __future__ import annotations

import json
from typing import Any

import httpx

MONDAY_API_URL = "https://api.monday.com/v2"
API_VERSION = "2024-10"
PAGE_SIZE = 500


class MondayError(RuntimeError):
    pass


class MondayClient:
    def __init__(self, token: str, timeout: float = 30.0):
        self._client = httpx.AsyncClient(
            base_url=MONDAY_API_URL,
            headers={
                "Authorization": token,
                "API-Version": API_VERSION,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _gql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = await self._client.post(
            "", json={"query": query, "variables": variables or {}}
        )
        resp.raise_for_status()
        payload = resp.json()
        if "errors" in payload:
            raise MondayError(json.dumps(payload["errors"]))
        return payload["data"]

    async def list_boards(self, ids: list[int] | None = None) -> list[dict[str, Any]]:
        """Return [{id, name, items_count}] for the given board IDs (or all boards)."""
        if ids:
            query = """
            query ($ids: [ID!]) {
              boards(ids: $ids) {
                id
                name
                items_count
                description
              }
            }
            """
            data = await self._gql(query, {"ids": [str(i) for i in ids]})
        else:
            query = """
            query {
              boards(limit: 50) {
                id
                name
                items_count
              }
            }
            """
            data = await self._gql(query)
        return data["boards"] or []

    async def get_board_schema(self, board_id: int) -> dict[str, Any]:
        """Return {id, name, columns: [{id, title, type, settings}]}"""
        query = """
        query ($ids: [ID!]) {
          boards(ids: $ids) {
            id
            name
            items_count
            columns {
              id
              title
              type
              settings_str
            }
          }
        }
        """
        data = await self._gql(query, {"ids": [str(board_id)]})
        boards = data["boards"] or []
        if not boards:
            raise MondayError(f"Board {board_id} not found or not accessible")
        b = boards[0]
        columns = []
        for c in b["columns"]:
            settings = {}
            if c.get("settings_str"):
                try:
                    settings = json.loads(c["settings_str"])
                except json.JSONDecodeError:
                    settings = {}
            columns.append(
                {
                    "id": c["id"],
                    "title": c["title"],
                    "type": c["type"],
                    "settings": settings,
                }
            )
        return {
            "id": b["id"],
            "name": b["name"],
            "items_count": b.get("items_count"),
            "columns": columns,
        }

    async def query_board_raw(
        self, board_id: int, limit: int = PAGE_SIZE, max_items: int | None = None
    ) -> list[dict[str, Any]]:
        """Fetch all items from a board via cursor pagination.

        Each item is: {id, name, column_values: [{id, text, type, value}]}
        Returns up to max_items (or all items when None).
        """
        first_query = """
        query ($ids: [ID!], $limit: Int!) {
          boards(ids: $ids) {
            items_page(limit: $limit) {
              cursor
              items {
                id
                name
                column_values { id text type value }
              }
            }
          }
        }
        """
        data = await self._gql(first_query, {"ids": [str(board_id)], "limit": limit})
        boards = data["boards"] or []
        if not boards:
            raise MondayError(f"Board {board_id} not found or not accessible")
        page = boards[0]["items_page"]
        items: list[dict[str, Any]] = list(page["items"])
        cursor = page.get("cursor")

        next_query = """
        query ($cursor: String!, $limit: Int!) {
          next_items_page(cursor: $cursor, limit: $limit) {
            cursor
            items {
              id
              name
              column_values { id text type value }
            }
          }
        }
        """
        while cursor and (max_items is None or len(items) < max_items):
            data = await self._gql(next_query, {"cursor": cursor, "limit": limit})
            page = data["next_items_page"]
            items.extend(page["items"])
            cursor = page.get("cursor")
            if not page["items"]:
                break

        if max_items is not None:
            items = items[:max_items]
        return items
