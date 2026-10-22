"""Shared metadata schema and artifact helpers for route comparisons."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import isodate

FIELDS = (
    "video_id", "url", "title", "description", "channel_name", "channel_url",
    "published_at", "duration_seconds", "view_count", "like_count",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def integer_or_none(value: Any) -> int | str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        return int(stripped) if re.fullmatch(r"\d+", stripped) else stripped or None
    return None


def duration_seconds(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.startswith("P"):
            try:
                return int(isodate.parse_duration(value).total_seconds())
            except (ValueError, TypeError):
                return None
        parts = value.split(":")
        if all(part.isdigit() for part in parts) and 1 < len(parts) <= 3:
            total = 0
            for part in parts:
                total = total * 60 + int(part)
            return total
    return None


def normalize_record(
    *, route: str, video_id: str, values: dict[str, Any], description_source: str | None
) -> dict[str, Any]:
    record = {field: values.get(field) for field in FIELDS}
    record["video_id"] = video_id
    record["url"] = f"https://www.youtube.com/watch?v={video_id}"
    record["duration_seconds"] = duration_seconds(record["duration_seconds"])
    record["view_count"] = integer_or_none(record["view_count"])
    record["like_count"] = integer_or_none(record["like_count"])
    presence = {field: record[field] is not None for field in FIELDS}
    description = record["description"]
    ellipsis = isinstance(description, str) and description.rstrip().endswith(("...", "…"))
    missing = {
        field: "source did not return this field"
        for field, present in presence.items()
        if not present
    }
    record.update(
        {
            "fetched_at": utc_now(),
            "route": route,
            "field_sources": {"description": description_source} if description_source else {},
            "field_presence": presence,
            "record_fields_present": all(presence.values()),
            "description_status": {
                "source": description_source,
                "ellipsis_truncation_detected": ellipsis,
                "source_field_preserved_without_ellipsis": isinstance(description, str) and not ellipsis,
                "scope_note": (
                    "No detected ellipsis means the selected source field was preserved; "
                    "it does not independently prove YouTube exposed the creator's entire original description."
                ),
            },
            "missing_field_reasons": missing,
        }
    )
    return record


def load_sample(path: Path) -> list[dict[str, str]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    videos = document.get("videos")
    if not isinstance(videos, list) or len(videos) != 10:
        raise ValueError("Metadata comparison requires the fixed 10-video sample.")
    return videos


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

