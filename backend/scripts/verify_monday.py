"""Smoke-test the monday.com connection.

Usage (from backend/):
    python -m scripts.verify_monday

Prints board metadata, column schemas, first few normalized rows, and
data-quality summary for both configured boards.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# allow running as `python -m scripts.verify_monday` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_settings
from app.monday_client import MondayClient
from app.monday_service import MondayService


def _brief(row: dict) -> dict:
    """Return a compact preview of a row for terminal display."""
    return {k: v for k, v in list(row.items())[:6]}


async def main() -> int:
    settings = load_settings()
    client = MondayClient(settings.monday_api_token)
    service = MondayService(
        client=client,
        board_aliases={
            "deals": settings.monday_board_deals,
            "work_orders": settings.monday_board_work_orders,
        },
    )

    try:
        print("=" * 70)
        print("Boards visible to this token:")
        boards = await service.list_boards()
        for b in boards:
            print(f"  - {b['name']!r} (id={b['id']}, items={b.get('items_count')}, alias={b.get('alias')})")

        for alias in ("deals", "work_orders"):
            print("\n" + "=" * 70)
            print(f"Board: {alias}")
            schema = await service.get_schema(alias)
            print(f"  Name: {schema['name']}")
            print(f"  Columns ({len(schema['columns'])}):")
            for c in schema["columns"]:
                print(f"    - {c['title']!r:40}  type={c['type']}")

            rows, dq, _ = await service.query_board(alias, max_items=200)
            print(f"\n  Fetched {len(rows)} rows (capped at 200 for verification).")
            print("  First 3 rows (first 6 fields shown):")
            for r in rows[:3]:
                print(f"    {json.dumps(_brief(r), default=str)}")

            print("\n  Data quality summary:")
            print(json.dumps(dq.summary(), indent=2))
    finally:
        await client.aclose()

    print("\nOK — monday.com integration verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
