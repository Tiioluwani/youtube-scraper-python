"""Run streamers/youtube-scraper for the fixed sample in metadata-only mode."""

from __future__ import annotations

import argparse
import os
import time
from datetime import timedelta
from pathlib import Path

from apify_client import ApifyClient
from dotenv import load_dotenv

from metadata_common import load_sample, normalize_record, utc_now, write_json

ACTOR_ID = "streamers/youtube-scraper"


def metadata_only_input(videos: list[dict[str, str]]) -> dict:
    return {
        "startUrls": [{"url": video["url"]} for video in videos],
        "maxResults": 10,
        "maxResultsShorts": 0,
        "maxResultStreams": 0,
        "transcriptionAndSubtitle": "NONE",
        "saveSubsToKVS": False,
        "aiVideoDescription": False,
        "aiVideoSummary": False,
    }


def result_from_run(videos: list[dict[str, str]], actor_run, items: list[dict], elapsed: float) -> dict:
    actor_input = metadata_only_input(videos)
    by_id = {item.get("id"): item for item in items if isinstance(item, dict) and item.get("id")}
    records, failures = [], []
    for video in videos:
        item = by_id.get(video["video_id"])
        if item is None:
            failures.append({"video_id": video["video_id"], "reason": "not_returned"})
            continue
        if item.get("error"):
            failures.append({"video_id": video["video_id"], "reason": "actor_error",
                             "error_code": item.get("error")})
            continue
        records.append(normalize_record(
            route="apify_streamers_youtube_scraper_metadata_only",
            video_id=video["video_id"],
            values={
                "title": item.get("title"), "description": item.get("text"),
                "channel_name": item.get("channelName"), "channel_url": item.get("channelUrl"),
                "published_at": item.get("date"), "duration_seconds": item.get("duration"),
                "view_count": item.get("viewCount"), "like_count": item.get("likes"),
            }, description_source="apify_dataset.text",
        ))
    run_data = actor_run.model_dump(mode="json")
    safe_run = {
        key: run_data.get(key)
        for key in ("id", "status", "started_at", "finished_at", "usage", "usage_total_usd",
                    "charged_event_counts", "default_dataset_id")
        if run_data.get(key) is not None
    }
    return {
        "route": "apify_streamers_youtube_scraper", "outcome": "success" if not failures else "partial",
        "tested_at_utc": utc_now(), "elapsed_seconds": round(elapsed, 3), "attempts": 1,
        "first_attempt_success": run_data.get("status") == "SUCCEEDED",
        "configuration": {**actor_input, "startUrls": f"{len(videos)} fixed video URLs"},
        "billing_information": safe_run, "dataset_items_returned": len(items),
        "saved_fields_note": "Comments, subtitles, transcripts, AI fields, and raw dataset items are omitted.",
        "failures": failures, "records": records,
    }


def recover_completed_run(sample_path: Path, token: str, run_id: str, elapsed: float) -> dict:
    videos = load_sample(sample_path)
    client = ApifyClient(token)
    actor_run = client.run(run_id).get()
    items = client.dataset(actor_run.default_dataset_id).list_items(clean=True).items
    return result_from_run(videos, actor_run, items, elapsed)


def run(sample_path: Path, token: str) -> dict:
    videos = load_sample(sample_path)
    actor_input = metadata_only_input(videos)
    started = time.perf_counter()
    try:
        client = ApifyClient(token)
        actor_run = client.actor(ACTOR_ID).call(
            run_input=actor_input,
            run_timeout=timedelta(seconds=600),
        )
        elapsed = time.perf_counter() - started
        items = client.dataset(actor_run.default_dataset_id).list_items(clean=True).items
    except Exception as exc:
        return {
            "route": "apify_streamers_youtube_scraper", "outcome": "request_failure",
            "attempts": 1, "elapsed_seconds": round(time.perf_counter() - started, 3),
            "exception_type": type(exc).__name__, "records": [],
        }
    return result_from_run(videos, actor_run, items, elapsed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, default=Path("metadata_sample_10.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/apify-latest.json"))
    args = parser.parse_args()
    load_dotenv()
    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        print("APIFY_API_TOKEN is not set; live route untested.")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, run(args.sample, token))
    print(f"Saved Apify results to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

