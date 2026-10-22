"""Fetch and normalize metadata for one public YouTube video."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import isodate
import requests
from dotenv import load_dotenv

API_URL = "https://api.zenrows.com/v1/"
ROUTE = "zenrows_fetch_extract_auto"
ARTIFACTS_DIR = Path("artifacts")
EXTRACT_FIELDS = ",".join(
    (
        "video.video_id",
        "video.canonical_url",
        "video.title",
        "video.description",
        "video.upload_date",
        "video.duration_iso",
        "engagement.view_count",
        "engagement.like_count",
        "channel.name",
        "channel.channel_url",
    )
)
BILLING_HEADERS = (
    "Concurrency-Limit",
    "Concurrency-Remaining",
    "X-Request-Cost",
    "X-Key-Credits-Remaining",
    "X-Request-Id",
    "Zr-Final-Url",
)
VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


class InputError(ValueError):
    """Raised when the supplied URL is not a supported YouTube video URL."""


def extract_video_id(url: str) -> str:
    """Extract an 11-character ID from a public YouTube video URL."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    candidate: str | None = None

    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [None])[0]
        else:
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) == 2 and parts[0] in {"shorts", "embed"}:
                candidate = parts[1]
    elif host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/", 1)[0]

    if not candidate or not VIDEO_ID_PATTERN.fullmatch(candidate):
        raise InputError("Provide a valid YouTube watch, Shorts, embed, or youtu.be video URL.")
    return candidate


def canonical_video_url(url: str) -> str:
    """Return a stable watch URL without tracking or playlist parameters."""
    return f"https://www.youtube.com/watch?v={extract_video_id(url)}"


def _nested(data: dict[str, Any], *path: str) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _duration_seconds(value: Any) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        duration = isodate.parse_duration(value)
        return int(duration.total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


def _looks_truncated(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.rstrip().endswith(("…", "..."))


def _embedded_description(html: Any) -> str | None:
    """Read YouTube's full description from embedded player JSON when present."""
    if not isinstance(html, str):
        return None
    match = re.search(r'"shortDescription":("(?:\\.|[^"\\])*")', html)
    if not match:
        return None
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, str) and value else None


def normalize_response(
    payload: Any, requested_url: str, fetched_at: str | None = None
) -> dict[str, Any]:
    """Normalize a Zenrows Fetch with Extract response without inventing values."""
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    missing: dict[str, str] = {}

    if not isinstance(payload, dict):
        parsed: dict[str, Any] = {}
        extraction_failure = "response body is not a JSON object"
    elif "parsed" not in payload:
        parsed = {}
        extraction_failure = "response has no parsed key; Extract did not return structured data"
    elif not isinstance(payload["parsed"], dict):
        parsed = {}
        extraction_failure = "response parsed value is not an object"
    else:
        parsed = payload["parsed"]
        extraction_failure = None

    values = {
        "video_id": _nested(parsed, "video", "video_id"),
        "url": _nested(parsed, "video", "canonical_url"),
        "title": _nested(parsed, "video", "title"),
        "description": _nested(parsed, "video", "description"),
        "channel_name": _nested(parsed, "channel", "name"),
        "channel_url": _nested(parsed, "channel", "channel_url"),
        "published_at": _nested(parsed, "video", "upload_date"),
        "duration_seconds": _duration_seconds(_nested(parsed, "video", "duration_iso")),
        "view_count": _nested(parsed, "engagement", "view_count"),
        "like_count": _nested(parsed, "engagement", "like_count"),
    }
    field_sources = {"description": "parsed.video.description"}

    embedded_description = _embedded_description(payload.get("html") if isinstance(payload, dict) else None)
    if (
        embedded_description
        and len(embedded_description) > len(values["description"] or "")
        and not _looks_truncated(embedded_description)
    ):
        values["description"] = embedded_description
        field_sources["description"] = "html.ytInitialPlayerResponse.videoDetails.shortDescription"

    # The requested canonical URL is known independently of extraction.
    if values["url"] is None:
        values["url"] = canonical_video_url(requested_url)

    source_paths = {
        "video_id": "parsed.video.video_id",
        "title": "parsed.video.title",
        "description": "parsed.video.description",
        "channel_name": "parsed.channel.name",
        "channel_url": "parsed.channel.channel_url",
        "published_at": "parsed.video.upload_date",
        "duration_seconds": "parsed.video.duration_iso",
        "view_count": "parsed.engagement.view_count",
        "like_count": "parsed.engagement.like_count",
    }
    for field, source_path in source_paths.items():
        if values[field] is None:
            missing[field] = extraction_failure or f"{source_path} was absent or null"

    if _nested(parsed, "video", "duration_iso") is not None and values["duration_seconds"] is None:
        missing["duration_seconds"] = "parsed.video.duration_iso was present but invalid"
    if _looks_truncated(values["description"]):
        missing["description"] = "value was returned but appears truncated (ends with an ellipsis)"

    field_presence = {
        field: values[field] is not None
        for field in (
            "video_id", "url", "title", "description", "channel_name", "channel_url",
            "published_at", "duration_seconds", "view_count", "like_count",
        )
    }
    description_truncated = "description" in missing and "truncated" in missing["description"]
    description_status = {
        "source": field_sources["description"],
        "ellipsis_truncation_detected": description_truncated,
        "source_field_preserved_without_ellipsis": (
            values["description"] is not None and not description_truncated
        ),
        "scope_note": (
            "No detected ellipsis means the selected source field was preserved; it does not "
            "independently prove that YouTube exposed the creator's entire original description."
        ),
    }

    return {
        **values,
        "fetched_at": fetched_at,
        "route": ROUTE,
        "field_sources": field_sources,
        "field_presence": field_presence,
        "record_fields_present": all(field_presence.values()),
        "description_status": description_status,
        "missing_field_reasons": missing,
    }


def _safe_error(response: requests.Response) -> str:
    """Create an error message without request URLs, query strings, or credentials."""
    request_id = response.headers.get("X-Request-Id")
    suffix = f" (request id: {request_id})" if request_id else ""
    return f"Zenrows returned HTTP {response.status_code}{suffix}."


def fetch_video(
    url: str,
    api_key: str,
    timeout: float | tuple[float, float] = 180,
) -> tuple[requests.Response, float]:
    """Make the documented Fetch with Extract request."""
    params = {
        "apikey": api_key,
        "url": canonical_video_url(url),
        "mode": "auto",
        "extract": "auto",
        # Restrict structured Extract output to metadata; raw HTML is always returned by the API.
        "extract_fields": EXTRACT_FIELDS,
    }
    started = time.perf_counter()
    response = requests.get(API_URL, params=params, timeout=timeout)
    elapsed = time.perf_counter() - started
    return response, elapsed


def filter_response_for_storage(payload: Any) -> dict[str, Any]:
    """Keep metadata evidence while excluding comments and comment-bearing raw HTML."""
    parsed = payload.get("parsed") if isinstance(payload, dict) else None
    filtered_parsed = {
        key: value
        for key, value in parsed.items()
        if key in {"video", "engagement", "channel"}
    } if isinstance(parsed, dict) else None
    html = payload.get("html") if isinstance(payload, dict) else None
    return {
        "artifact_note": (
            "Filtered local evidence: structured comments and raw HTML were omitted. "
            "The API response is summarized in run.json."
        ),
        "parsed": filtered_parsed,
        "response_evidence": {
            "html_returned": isinstance(html, str),
            "html_characters": len(html) if isinstance(html, str) else None,
            "top_level_keys": sorted(payload) if isinstance(payload, dict) else None,
        },
    }


def save_artifacts(
    response: requests.Response, payload: Any, normalized: dict[str, Any], elapsed: float
) -> Path:
    """Save filtered evidence and derived results; artifacts/ is ignored by git."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = ARTIFACTS_DIR / timestamp
    run_dir.mkdir(parents=True, exist_ok=False)
    filtered_response = filter_response_for_storage(payload)
    (run_dir / "response.filtered.json").write_text(
        json.dumps(filtered_response, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (run_dir / "normalized.json").write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    metadata = {
        "http_status": response.status_code,
        "elapsed_seconds": round(elapsed, 3),
        "response_body_bytes": len(response.content),
        "response_content_type": response.headers.get("Content-Type"),
        "saved_response": "response.filtered.json",
        "saved_response_is_original": False,
        "billing_headers": {
            name: response.headers[name]
            for name in BILLING_HEADERS
            if name in response.headers
        },
    }
    (run_dir / "run.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return run_dir


def save_failure_artifact(exception: Exception, elapsed: float) -> Path:
    """Record a pre-response failure without storing URLs, credentials, or exception text."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = ARTIFACTS_DIR / f"{timestamp}-failed"
    run_dir.mkdir(parents=True, exist_ok=False)
    failure = {
        "outcome": "request_failed_before_response",
        "exception_type": type(exception).__name__,
        "elapsed_seconds": round(elapsed, 3),
        "http_status": None,
    }
    (run_dir / "failure.json").write_text(
        json.dumps(failure, indent=2) + "\n", encoding="utf-8"
    )
    return run_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Public YouTube video URL")
    args = parser.parse_args()

    # A local .env is optional and excluded from git.
    load_dotenv()
    api_key = os.getenv("ZENROWS_API_KEY")
    if not api_key:
        print("ZENROWS_API_KEY is not set. Copy .env.example to .env and add the key locally.", file=sys.stderr)
        return 2

    request_started = time.perf_counter()
    try:
        response, elapsed = fetch_video(args.url, api_key)
        try:
            payload = response.json()
        except requests.exceptions.JSONDecodeError:
            payload = None
        normalized = normalize_response(payload, args.url)
        run_dir = save_artifacts(response, payload, normalized, elapsed)
        if not response.ok:
            print(_safe_error(response), file=sys.stderr)
            print(f"Saved failed run artifacts to {run_dir}", file=sys.stderr)
            return 1
        if payload is None:
            print("Zenrows returned a successful response that was not valid JSON.", file=sys.stderr)
            print(f"Saved failed run artifacts to {run_dir}", file=sys.stderr)
            return 1
    except InputError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except requests.RequestException as exc:
        failure_dir = save_failure_artifact(exc, time.perf_counter() - request_started)
        print(
            f"The Zenrows request failed before a response ({type(exc).__name__}). "
            "No request URL, exception text, or credentials were logged.",
            file=sys.stderr,
        )
        print(f"Saved failure record to {failure_dir}", file=sys.stderr)
        return 1
    print(f"Saved live run artifacts to {run_dir}")
    print(json.dumps(normalized, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

