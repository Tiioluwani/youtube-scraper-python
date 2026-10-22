"""Discover public video URLs from one YouTube channel tab with Zenrows Fetch."""

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

import requests
from dotenv import load_dotenv

from youtube_video import (
    API_URL,
    BILLING_HEADERS,
    fetch_video,
    filter_response_for_storage,
    normalize_response,
)

CHANNEL_URL = "https://www.youtube.com/@BlenderOfficial"
ALLOWED_LIMITS = (10, 100, 1000)
CATEGORIES = {
    "videos": "regular_videos",
    "shorts": "shorts",
    "streams": "streams",
}
VIDEO_ID_RE = re.compile(r'(?:"|\\")videoId(?:"|\\")\s*:\s*(?:"|\\")([A-Za-z0-9_-]{11})')
SCROLL_DEPTHS = (10, 25, 50, 100)


def ordered_video_ids(html: str) -> list[str]:
    """Return unique video IDs in first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for video_id in VIDEO_ID_RE.findall(html):
        if video_id not in seen:
            seen.add(video_id)
            result.append(video_id)
    return result


def canonical_url(video_id: str, category: str) -> str:
    if category == "shorts":
        return f"https://www.youtube.com/shorts/{video_id}"
    return f"https://www.youtube.com/watch?v={video_id}"


def merge_unique(existing: list[str], incoming: list[str], limit: int) -> int:
    """Merge IDs without duplicates and return the number of new IDs."""
    before = len(existing)
    known = set(existing)
    for video_id in incoming:
        if video_id not in known and len(existing) < limit:
            existing.append(video_id)
            known.add(video_id)
    return len(existing) - before


def stopping_reason(
    count: int,
    limit: int,
    *,
    failed: bool = False,
    timed_out: bool = False,
    no_progress: bool = False,
) -> str:
    if count >= limit:
        return "requested_limit_reached"
    if timed_out:
        return "timeout"
    if failed:
        return "request_failure"
    if no_progress:
        return "no_progress"
    return "channel_exhausted"


def scroll_instructions(depth: int) -> str:
    """Build documented evaluate-and-wait instructions for infinite scrolling."""
    # Let the initial dynamic grid become ready before the first scroll.
    instructions: list[dict[str, Any]] = [{"wait": 2000}]
    for _ in range(depth):
        instructions.append({"scroll_y": 10000})
        instructions.append({"wait": 1000})
    return json.dumps(instructions, separators=(",", ":"))


def sanitized_exception_chain(exc: BaseException) -> list[dict[str, Any]]:
    """Describe exception classes and safe OS codes without messages or URLs."""
    output: list[dict[str, Any]] = []
    queue: list[BaseException] = [exc]
    seen: set[int] = set()
    while queue and len(output) < 8:
        current = queue.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        item: dict[str, Any] = {"type": type(current).__name__}
        if isinstance(current, OSError):
            item["errno"] = current.errno
        output.append(item)
        for candidate in (
            current.__cause__,
            current.__context__,
            getattr(current, "reason", None),
            *current.args,
        ):
            if isinstance(candidate, BaseException):
                queue.append(candidate)
    return output


def request_tab(
    api_key: str, channel_url: str, category: str, scroll_depth: int
) -> tuple[requests.Response, float, dict[str, Any]]:
    params: dict[str, Any] = {
        "apikey": api_key,
        "url": f"{channel_url.rstrip('/')}/{category}",
    }
    if scroll_depth:
        # JavaScript instructions require js_render=true; mode=auto is intentionally omitted.
        params.update(
            {
                "js_render": "true",
                "js_instructions": scroll_instructions(scroll_depth),
            }
        )
        route = "fetch_js_render_scroll"
    else:
        params["mode"] = "auto"
        route = "fetch_mode_auto_initial"

    started = time.perf_counter()
    response = requests.get(API_URL, params=params, timeout=180)
    elapsed = time.perf_counter() - started
    configuration = {
        "route": route,
        "category": category,
        "scroll_depth": scroll_depth,
        "initial_wait_ms": 2000 if scroll_depth else 0,
        "wait_per_scroll_ms": 1000 if scroll_depth else 0,
    }
    return response, elapsed, configuration


def discover_category(
    api_key: str, channel_url: str, category: str, limit: int
) -> dict[str, Any]:
    ids: list[str] = []
    requests_log: list[dict[str, Any]] = []
    no_progress_runs = 0
    failure = False
    timeout = False
    started = time.perf_counter()

    for scroll_depth in (0, *SCROLL_DEPTHS):
        try:
            response, elapsed, configuration = request_tab(
                api_key, channel_url, category, scroll_depth
            )
        except requests.Timeout as exc:
            timeout = True
            requests_log.append(
                {
                    "configuration": {
                        "category": category,
                        "scroll_depth": scroll_depth,
                    },
                    "http_status": None,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "exception_type": type(exc).__name__,
                }
            )
            break
        except requests.RequestException as exc:
            failure = True
            requests_log.append(
                {
                    "configuration": {
                        "category": category,
                        "scroll_depth": scroll_depth,
                    },
                    "http_status": None,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "exception_type": type(exc).__name__,
                }
            )
            break

        try:
            body = response.text
            body_bytes = len(response.content)
        except requests.RequestException as exc:
            failure = True
            requests_log.append(
                {
                    "configuration": configuration,
                    "http_status": response.status_code,
                    "elapsed_seconds": round(elapsed, 3),
                    "exception_type": type(exc).__name__,
                    "phase": "response_body_read",
                }
            )
            break

        found = ordered_video_ids(body)
        added = merge_unique(ids, found, limit)
        headers = {
            name: response.headers[name]
            for name in BILLING_HEADERS
            if name in response.headers
        }
        requests_log.append(
            {
                "configuration": configuration,
                "http_status": response.status_code,
                "elapsed_seconds": round(elapsed, 3),
                "response_body_bytes": body_bytes,
                "ids_observed": len(found),
                "new_unique_ids": added,
                "cost_headers": headers,
            }
        )
        if not response.ok:
            failure = True
            break
        if len(ids) >= limit:
            break
        no_progress_runs = no_progress_runs + 1 if added == 0 else 0
        if no_progress_runs >= 2:
            break

    reason = stopping_reason(
        len(ids),
        limit,
        failed=failure,
        timed_out=timeout,
        no_progress=no_progress_runs >= 2,
    )
    return {
        "category": category,
        "requested_limit": limit,
        "unique_collected": len(ids),
        "complete": reason in {"requested_limit_reached", "channel_exhausted"},
        "stopping_reason": reason,
        "requests_made": len(requests_log),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "requests": requests_log,
        "items": [
            {"video_id": video_id, "url": canonical_url(video_id, category)}
            for video_id in ids
        ],
    }


def fetch_first_metadata(
    items: list[dict[str, str]],
    api_key: str,
    run_dir: Path,
    connection_retries: int = 0,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    metadata_dir = run_dir / "metadata_first_10"
    metadata_dir.mkdir()
    results: list[dict[str, Any]] = []
    for item in items[:10]:
        attempts: list[dict[str, Any]] = []
        entry: dict[str, Any] | None = None
        for attempt_number in range(1, connection_retries + 2):
            started = time.perf_counter()
            try:
                response, elapsed = fetch_video(
                    item["url"], api_key, timeout=(10, timeout_seconds)
                )
                payload = response.json()
                normalized = normalize_response(payload, item["url"])
                attempt = {
                    "attempt": attempt_number,
                    "http_status": response.status_code,
                    "elapsed_seconds": round(elapsed, 3),
                    "success": response.ok,
                    "cost_headers": {
                        name: response.headers[name]
                        for name in BILLING_HEADERS
                        if name in response.headers
                    },
                }
                attempts.append(attempt)
                entry = {
                    "video_id": item["video_id"],
                    **attempt,
                    "record": normalized if response.ok else None,
                    "attempts": attempts,
                }
                evidence = filter_response_for_storage(payload)
                (metadata_dir / f"{item['video_id']}.filtered.json").write_text(
                    json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )
                break
            except requests.exceptions.JSONDecodeError as exc:
                attempt = {
                    "attempt": attempt_number,
                    "http_status": response.status_code,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "success": False,
                    "exception_type": type(exc).__name__,
                    "exception_chain": sanitized_exception_chain(exc),
                }
                attempts.append(attempt)
                entry = {
                    "video_id": item["video_id"],
                    **attempt,
                    "record": None,
                    "attempts": attempts,
                }
                break
            except requests.RequestException as exc:
                attempt = {
                    "attempt": attempt_number,
                    "http_status": None,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "success": False,
                    "exception_type": type(exc).__name__,
                }
                attempts.append(attempt)
                entry = {
                    "video_id": item["video_id"],
                    **attempt,
                    "record": None,
                    "attempts": attempts,
                }
                if attempt_number <= connection_retries:
                    time.sleep(1)
                    continue
                break
            except ValueError as exc:
                attempt = {
                    "attempt": attempt_number,
                    "http_status": response.status_code,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "success": False,
                    "exception_type": type(exc).__name__,
                }
                attempts.append(attempt)
                entry = {
                    "video_id": item["video_id"],
                    **attempt,
                    "record": None,
                    "attempts": attempts,
                }
                break
        assert entry is not None
        results.append(entry)
    summary = {
        "discovered_input_count": min(10, len(items)),
        "successful_metadata_records": sum(1 for result in results if result["success"]),
        "records_with_all_required_fields_present": sum(
            1
            for result in results
            if result.get("record")
            and all(
                result["record"].get(field) is not None
                for field in (
                    "video_id",
                    "url",
                    "title",
                    "description",
                    "channel_name",
                    "channel_url",
                    "published_at",
                    "duration_seconds",
                    "view_count",
                    "like_count",
                )
            )
        ),
        "records_with_source_description_preserved_without_ellipsis": sum(
            1
            for result in results
            if result.get("record")
            and result["record"].get("description_status", {}).get(
                "source_field_preserved_without_ellipsis"
            ) is True
        ),
        "records_with_all_fields_present_and_no_detected_truncation": sum(
            1
            for result in results
            if result.get("record")
            and result["record"].get("record_fields_present") is True
            and result["record"].get("description_status", {}).get(
                "ellipsis_truncation_detected"
            ) is False
        ),
        "connection_retries_per_video": connection_retries,
        "connect_timeout_seconds": 10,
        "read_timeout_seconds": timeout_seconds,
        "retry_policy": "Only pre-response requests.RequestException failures; one-second backoff; HTTP responses are not retried.",
        "results": results,
    }
    (metadata_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel_url", nargs="?", default=CHANNEL_URL)
    parser.add_argument("--limit", type=int, choices=ALLOWED_LIMITS, required=True)
    parser.add_argument("--category", choices=CATEGORIES, default="videos")
    parser.add_argument("--fetch-metadata-first", type=int, choices=(0, 10), default=0)
    parser.add_argument("--metadata-connection-retries", type=int, choices=(0, 1), default=0)
    parser.add_argument("--metadata-timeout-seconds", type=int, choices=(30, 60, 120), default=60)
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("ZENROWS_API_KEY")
    if not api_key:
        print("ZENROWS_API_KEY is not set.", file=sys.stderr)
        return 2

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path("artifacts") / f"channel-{args.category}-{args.limit}-{timestamp}"
    run_dir.mkdir(parents=True)
    try:
        discovery = discover_category(api_key, args.channel_url, args.category, args.limit)
    except Exception as exc:
        failure = {
            "outcome": "unexpected_discovery_failure",
            "exception_type": type(exc).__name__,
            "http_status": None,
            "note": "Exception text, request URLs, and credentials are intentionally omitted.",
        }
        (run_dir / "failure.json").write_text(
            json.dumps(failure, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"Channel discovery failed unexpectedly ({type(exc).__name__}); "
            f"saved {run_dir / 'failure.json'}.",
            file=sys.stderr,
        )
        return 1
    output = {
        "channel_url": args.channel_url,
        "test_date_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "requested_category": args.category,
        "requested_limit": args.limit,
        "categories": {
            name: discovery if name == CATEGORIES[args.category] else {
                "unique_collected": 0,
                "stopping_reason": "not_requested",
                "items": [],
            }
            for name in CATEGORIES.values()
        },
    }
    (run_dir / "discovery.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    if args.fetch_metadata_first:
        metadata = fetch_first_metadata(
            discovery["items"],
            api_key,
            run_dir,
            args.metadata_connection_retries,
            args.metadata_timeout_seconds,
        )
        output["metadata_first_10"] = {
            "discovered_input_count": metadata["discovered_input_count"],
            "successful_metadata_records": metadata["successful_metadata_records"],
            "records_with_all_required_fields_present": metadata[
                "records_with_all_required_fields_present"
            ],
            "records_with_source_description_preserved_without_ellipsis": metadata[
                "records_with_source_description_preserved_without_ellipsis"
            ],
            "records_with_all_fields_present_and_no_detected_truncation": metadata[
                "records_with_all_fields_present_and_no_detected_truncation"
            ],
        }
        (run_dir / "discovery.json").write_text(
            json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    print(f"Saved channel run to {run_dir}")
    print(
        json.dumps(
            {
                "category": args.category,
                "requested_limit": args.limit,
                "unique_collected": discovery["unique_collected"],
                "requests_made": discovery["requests_made"],
                "elapsed_seconds": discovery["elapsed_seconds"],
                "stopping_reason": discovery["stopping_reason"],
                "metadata_first_10": output.get("metadata_first_10"),
            },
            indent=2,
        )
    )
    return 0 if discovery["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

