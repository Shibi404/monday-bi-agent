"""Normalize monday.com raw rows into clean typed dicts and surface data quality issues.

Design goals:
- Never drop a row for being messy; coerce to None and record the issue.
- Preserve original human-readable text for text-y columns.
- For dates/numbers, parse the underlying `value` (JSON) when available,
  fall back to `text`.
- Report per-column counts of nulls and parse failures so the agent can
  caveat its answers.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any

from dateutil import parser as dateparser

# Tokens that show up in real-world sheets as "empty"
NULLISH_TOKENS = {"", "n/a", "na", "none", "null", "-", "--", "tbd", "?", "unknown"}

# Numbers/currency stripping
_NUM_STRIP_RE = re.compile(r"[₹$,€£\s]")
_STAGE_PREFIX_RE = re.compile(r"^([A-Z])\.\s+(.*)$")


@dataclass
class DataQuality:
    total_rows: int = 0
    per_column: dict[str, dict[str, int]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def note(self, column: str, kind: str) -> None:
        col = self.per_column.setdefault(
            column, {"null": 0, "parse_error": 0, "coerced": 0}
        )
        col[kind] = col.get(kind, 0) + 1

    def summary(self) -> dict[str, Any]:
        cols = []
        for col, counts in sorted(self.per_column.items()):
            null_pct = (counts["null"] / self.total_rows * 100) if self.total_rows else 0
            if counts["null"] or counts["parse_error"]:
                cols.append(
                    {
                        "column": col,
                        "null_count": counts["null"],
                        "null_pct": round(null_pct, 1),
                        "parse_errors": counts["parse_error"],
                    }
                )
        return {
            "total_rows": self.total_rows,
            "columns_with_issues": cols,
            "warnings": self.warnings,
        }


def _is_nullish(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and v.strip().lower() in NULLISH_TOKENS:
        return True
    return False


def _parse_date(text: str | None, value_json: str | None) -> str | None:
    """Return ISO date string (YYYY-MM-DD) or None."""
    if value_json:
        try:
            v = json.loads(value_json)
            if isinstance(v, dict) and v.get("date"):
                return v["date"]
        except (json.JSONDecodeError, TypeError):
            pass
    if text and not _is_nullish(text):
        try:
            dt = dateparser.parse(text, dayfirst=False, fuzzy=True)
            return dt.date().isoformat()
        except (ValueError, dateparser.ParserError):
            return None
    return None


def _parse_number(text: str | None, value_json: str | None) -> float | None:
    if value_json:
        try:
            v = json.loads(value_json)
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str) and v.strip():
                cleaned = _NUM_STRIP_RE.sub("", v)
                return float(cleaned)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    if text and not _is_nullish(text):
        cleaned = _NUM_STRIP_RE.sub("", text)
        # handle trailing 'k' / 'm'
        mult = 1
        if cleaned.lower().endswith("k"):
            mult, cleaned = 1_000, cleaned[:-1]
        elif cleaned.lower().endswith("m"):
            mult, cleaned = 1_000_000, cleaned[:-1]
        try:
            return float(cleaned) * mult
        except ValueError:
            return None
    return None


def _parse_status(text: str | None) -> str | None:
    """Preserve original but stripped. Callers can further group via stage_letter()."""
    if text is None or _is_nullish(text):
        return None
    return text.strip()


def stage_letter(status: str | None) -> str | None:
    """Extract 'B' from 'B. Sales Qualified Leads', or None."""
    if not status:
        return None
    m = _STAGE_PREFIX_RE.match(status.strip())
    return m.group(1) if m else None


def normalize_rows(
    items: list[dict[str, Any]], columns: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], DataQuality]:
    """Convert monday raw items to clean typed rows.

    Returns (rows, data_quality). Each row keys columns by their TITLE
    (human-readable), plus a synthetic `_item_id` and `_item_name`.
    """
    dq = DataQuality(total_rows=len(items))
    col_by_id = {c["id"]: c for c in columns}
    rows: list[dict[str, Any]] = []

    for item in items:
        row: dict[str, Any] = {
            "_item_id": item["id"],
            "_item_name": item.get("name"),
        }
        cvs_by_id = {cv["id"]: cv for cv in item.get("column_values", [])}

        for col in columns:
            cid = col["id"]
            title = col["title"]
            ctype = col["type"]
            cv = cvs_by_id.get(cid, {})
            text = cv.get("text")
            value_json = cv.get("value")

            parsed: Any
            if ctype in ("date", "date_time", "creation_log", "last_updated"):
                parsed = _parse_date(text, value_json)
                if parsed is None and (text and not _is_nullish(text)):
                    dq.note(title, "parse_error")
            elif ctype in ("numbers", "numeric", "formula"):
                parsed = _parse_number(text, value_json)
                if parsed is None and (text and not _is_nullish(text)):
                    dq.note(title, "parse_error")
            elif ctype in ("status", "color", "dropdown"):
                parsed = _parse_status(text)
            else:
                parsed = None if _is_nullish(text) else (text.strip() if isinstance(text, str) else text)

            if parsed is None:
                dq.note(title, "null")

            row[title] = parsed

        rows.append(row)

    # Global warnings for high-null columns
    for col_name, counts in dq.per_column.items():
        if dq.total_rows and counts["null"] / dq.total_rows > 0.5:
            dq.warnings.append(
                f"{col_name!r} is missing in {counts['null']}/{dq.total_rows} rows"
                f" ({counts['null']/dq.total_rows*100:.0f}%)"
            )

    return rows, dq
