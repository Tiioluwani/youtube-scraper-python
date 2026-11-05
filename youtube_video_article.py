"""Fetch and normalize one public YouTube video with Zenrows."""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import isodate
import requests
from dotenv import load_dotenv

API_URL = "https://api.zenrows.com/v1/"
ROUTE = "zenrows_fetch_extract_auto"
FIELDS = {
    "video_id": "video.video_id", "url": "video.canonical_url",
    "title": "video.title", "description": "video.description",
    "channel_name": "channel.name", "channel_url": "channel.channel_url",
    "published_at": "video.upload_date", "duration_seconds": "video.duration_iso",
    "view_count": "engagement.view_count", "like_count": "engagement.like_count",
}
EXTRACT_FIELDS = ",".join(FIELDS[name] for name in (
    "video_id", "url", "title", "description", "published_at",
    "duration_seconds", "view_count", "like_count", "channel_name", "channel_url",
))
BILLING_HEADERS = (
    "Concurrency-Limit", "Concurrency-Remaining", "X-Request-Cost",
    "X-Key-Credits-Remaining", "X-Request-Id", "Zr-Final-Url",
)
InputError = ValueError


def _safe_error(response):
    request_id = response.headers.get("X-Request-Id")
    suffix = f" (request id: {request_id})" if request_id else ""
    return f"Zenrows returned HTTP {response.status_code}{suffix}."


def canonical_video_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    video_id = None
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        else:
            match = re.fullmatch(r"/(?:shorts|embed)/([^/]+)/?", parsed.path)
            video_id = match[1] if match else None
    elif host == "youtu.be":
        video_id = parsed.path.lstrip("/").split("/", 1)[0]
    if not video_id or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("Provide a valid YouTube watch, Shorts, embed, or youtu.be video URL.")
    return f"https://www.youtube.com/watch?v={video_id}"


def nested(data, path):
    for key in path.split("."):
        data = data.get(key) if isinstance(data, dict) else None
    return data


def truncated(value):
    return isinstance(value, str) and value.rstrip().endswith(("…", "..."))


def normalize_response(payload, requested_url, fetched_at=None):
    problem = None
    if not isinstance(payload, dict):
        problem = "response body is not a JSON object"
    elif "parsed" not in payload:
        problem = "response has no parsed key; Extract did not return structured data"
    elif not isinstance(payload["parsed"], dict):
        problem = "response parsed value is not an object"
    parsed = payload["parsed"] if problem is None else {}
    values = {field: nested(parsed, path) for field, path in FIELDS.items()}
    duration = values["duration_seconds"]
    values["duration_seconds"] = None
    if isinstance(duration, str) and duration:
        try:
            values["duration_seconds"] = int(isodate.parse_duration(duration).total_seconds())
        except (ValueError, TypeError, OverflowError):
            pass
    source = "parsed.video.description"
    html = payload.get("html", "") if isinstance(payload, dict) else ""
    html = html if isinstance(html, str) else ""
    # decode the source field without evaluating page code.
    for match in re.finditer(r'"shortDescription":("(?:\\.|[^"\\])*")', html or ""):
        try:
            description = json.loads(match.group(1))
        except json.JSONDecodeError:
            break
        if description and len(description) > len(values["description"] or "") and not truncated(description):
            values["description"] = description
            source = "html.ytInitialPlayerResponse.videoDetails.shortDescription"
        break
    # the fallback url is input-derived metadata context.
    if values["url"] is None:
        values["url"] = canonical_video_url(requested_url)
    missing = {
        field: problem or f"parsed.{path} was absent or null"
        for field, path in FIELDS.items() if field != "url" and values[field] is None
    }
    if duration is not None and values["duration_seconds"] is None:
        missing["duration_seconds"] = "parsed.video.duration_iso was present but invalid"
    if truncated(values["description"]):
        missing["description"] = "value was returned but appears truncated (ends with an ellipsis)"
    presence = {field: value is not None for field, value in values.items()}
    return {
        **values,
        "fetched_at": fetched_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "route": ROUTE, "field_sources": {"description": source},
        "field_presence": presence, "record_fields_present": all(presence.values()),
        "description_status": {
            "source": source,
            "ellipsis_truncation_detected": truncated(values["description"]),
            "source_field_preserved_without_ellipsis": values["description"] is not None and not truncated(values["description"]),
            "scope_note": "No detected ellipsis means the selected source field was preserved; it does not independently prove that YouTube exposed the creator's entire original description.",
        },
        "missing_field_reasons": missing,
    }


def filter_response_for_storage(payload):
    parsed = payload.get("parsed") if isinstance(payload, dict) else None
    return {
        "artifact_note": "Filtered metadata only; raw HTML and comments omitted.",
        "parsed": {key: value for key, value in parsed.items() if key in {"video", "engagement", "channel"}} if isinstance(parsed, dict) else None,
    }


def write_json(directory, name, value):
    (directory / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Public YouTube video URL")
    args = parser.parse_args()
    load_dotenv()
    key = os.getenv("ZENROWS_API_KEY")
    if not key:
        print("ZENROWS_API_KEY is not set. Add it to your environment or local .env.", file=sys.stderr)
        return 2
    try:
        url = canonical_video_url(args.url)
    except ValueError:
        print("Provide a valid YouTube video URL.", file=sys.stderr)
        return 2
    directory = Path("artifacts") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    try:
        response = requests.get(API_URL, params={
            "apikey": key, "url": url, "mode": "auto", "extract": "auto",
            "extract_fields": EXTRACT_FIELDS,
        }, timeout=180)
    except requests.RequestException as exc:
        write_json(directory, "failure.json", {
            "outcome": "request_failed_before_response", "exception_type": type(exc).__name__,
            "elapsed_seconds": round(time.perf_counter() - started, 3), "http_status": None,
        })
        # exception text can contain credential-bearing request urls.
        print(f"Request failed before a response ({type(exc).__name__}). Saved {directory}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - started
    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError:
        payload = None
    normalized = normalize_response(payload, url)
    write_json(directory, "response.filtered.json", filter_response_for_storage(payload))
    write_json(directory, "normalized.json", normalized)
    write_json(directory, "run.json", {
        "http_status": response.status_code, "elapsed_seconds": round(elapsed, 3),
        "response_body_bytes": len(response.content),
        "response_content_type": response.headers.get("Content-Type"),
        "saved_response": "response.filtered.json", "saved_response_is_original": False,
        "billing_headers": {name: response.headers[name] for name in BILLING_HEADERS if name in response.headers},
    })
    if not response.ok or payload is None:
        # report status and request id without the request url.
        message = _safe_error(response) if not response.ok else "Zenrows returned a successful response that was not valid JSON."
        print(f"{message} Saved failed run artifacts to {directory}", file=sys.stderr)
        return 1
    print(f"Saved live run artifacts to {directory}")
    print(json.dumps(normalized, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
