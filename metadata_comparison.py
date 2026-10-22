"""Run available metadata routes against the fixed 10-video sample."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from apify_metadata import run as run_apify
from metadata_common import load_sample, utc_now, write_json
from plain_requests_baseline import run as run_baseline
from youtube_data_api_metadata import run as run_youtube_api
from youtube_video import BILLING_HEADERS, fetch_video, normalize_response
from ytdlp_metadata import run as run_ytdlp


def zenrows_cost_headers(response: requests.Response) -> dict[str, str]:
    return {
        name: response.headers[name]
        for name in BILLING_HEADERS
        if name in response.headers and name.lower() != "zr-final-url"
    }


def run_zenrows(sample_path: Path, api_key: str) -> dict:
    videos = load_sample(sample_path)
    records, failures, attempts = [], [], []
    started_all = time.perf_counter()
    for video in videos:
        for attempt_number in (1, 2):
            try:
                response, elapsed = fetch_video(video["url"], api_key, timeout=(10, 60))
                attempt = {
                    "video_id": video["video_id"], "attempt": attempt_number,
                    "http_status": response.status_code, "elapsed_seconds": round(elapsed, 3),
                    "cost_headers": zenrows_cost_headers(response), "success": False,
                }
                if not response.ok:
                    attempts.append(attempt)
                    failures.append({"video_id": video["video_id"], "reason": "http_error",
                                     "http_status": response.status_code})
                    break
                try:
                    payload = response.json()
                    record = normalize_response(payload, video["url"])
                except (ValueError, requests.exceptions.JSONDecodeError) as exc:
                    attempt["exception_type"] = type(exc).__name__
                    attempts.append(attempt)
                    failures.append({"video_id": video["video_id"], "reason": "parsing_failure"})
                    break
                attempt["success"] = True
                attempts.append(attempt)
                records.append(record)
                break
            except requests.RequestException as exc:
                attempts.append({
                    "video_id": video["video_id"], "attempt": attempt_number,
                    "success": False, "http_status": None,
                    "elapsed_seconds": round(time.perf_counter() - started_all, 3),
                    "exception_type": type(exc).__name__, "phase": "pre_response_transport",
                })
                if attempt_number == 1:
                    time.sleep(1)
                    continue
                failures.append({"video_id": video["video_id"], "reason": "transport_error",
                                 "exception_type": type(exc).__name__})
    first_attempt_successes = sum(
        1 for attempt in attempts if attempt["attempt"] == 1 and attempt.get("success")
    )
    recovered_after_retry = sum(
        1 for attempt in attempts if attempt["attempt"] == 2 and attempt.get("success")
    )
    return {
        "route": "zenrows_fetch_extract_auto", "outcome": "success" if not failures else "partial",
        "tested_at_utc": utc_now(), "elapsed_seconds": round(time.perf_counter() - started_all, 3),
        "retry_policy": "At most one retry after a pre-response requests.RequestException; HTTP and parsing failures are not retried.",
        "first_attempt_successes": first_attempt_successes,
        "recovered_after_retry": recovered_after_retry,
        "attempts": attempts, "failures": failures, "records": records,
    }


def unavailable(route: str, variable: str) -> dict:
    return {
        "route": route, "outcome": "untested_missing_credential",
        "required_environment_variable": variable, "attempts": 0, "records": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, default=Path("metadata_sample_10.json"))
    args = parser.parse_args()
    load_dotenv()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path("artifacts") / f"metadata-comparison-{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    sample_document = json.loads(args.sample.read_text(encoding="utf-8"))
    write_json(run_dir / "sample.json", sample_document)

    routes = {
        "plain_requests": run_baseline(args.sample),
        "yt_dlp": run_ytdlp(args.sample),
        "youtube_data_api": run_youtube_api(args.sample, os.environ["YOUTUBE_API_KEY"])
        if os.getenv("YOUTUBE_API_KEY") else unavailable("youtube_data_api", "YOUTUBE_API_KEY"),
        "apify": run_apify(args.sample, os.environ["APIFY_API_TOKEN"])
        if os.getenv("APIFY_API_TOKEN") else unavailable("apify_streamers_youtube_scraper", "APIFY_API_TOKEN"),
        "zenrows": run_zenrows(args.sample, os.environ["ZENROWS_API_KEY"])
        if os.getenv("ZENROWS_API_KEY") else unavailable("zenrows_fetch_extract_auto", "ZENROWS_API_KEY"),
    }
    for name, result in routes.items():
        write_json(run_dir / f"{name}.json", result)
    report = {
        "tested_at_utc": utc_now(),
        "scope_note": "Fixed 10-video functional comparison; not a general success-rate benchmark.",
        "routes": {
            name: {
                "outcome": result.get("outcome"),
                "records": len(result.get("records", [])),
                "elapsed_seconds": result.get("elapsed_seconds"),
                "attempts": len(result.get("attempts", [])) if isinstance(result.get("attempts"), list) else result.get("attempts"),
            }
            for name, result in routes.items()
        },
    }
    write_json(run_dir / "report.json", report)
    print(f"Saved metadata comparison to {run_dir}")
    print(json.dumps(report["routes"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
