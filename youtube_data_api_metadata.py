"""Fetch the fixed metadata sample with YouTube Data API videos.list."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from metadata_common import load_sample, normalize_record, utc_now, write_json

API_URL = "https://www.googleapis.com/youtube/v3/videos"


def run(sample_path: Path, api_key: str) -> dict:
    videos = load_sample(sample_path)
    started = time.perf_counter()
    try:
        response = requests.get(
            API_URL,
            params={
                "key": api_key,
                "id": ",".join(video["video_id"] for video in videos),
                "part": "snippet,contentDetails,statistics",
            },
            timeout=(10, 60),
        )
        elapsed = time.perf_counter() - started
    except requests.RequestException as exc:
        return {"route": "youtube_data_api", "outcome": "transport_error", "attempts": 1,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "exception_type": type(exc).__name__, "records": []}
    if not response.ok:
        return {"route": "youtube_data_api", "outcome": "http_error", "attempts": 1,
                "http_status": response.status_code, "elapsed_seconds": round(elapsed, 3), "records": []}
    payload = response.json()
    by_id = {item.get("id"): item for item in payload.get("items", [])}
    records = []
    failures = []
    for video in videos:
        item = by_id.get(video["video_id"])
        if not item:
            failures.append({"video_id": video["video_id"], "reason": "not_returned"})
            continue
        snippet = item.get("snippet", {})
        details = item.get("contentDetails", {})
        statistics = item.get("statistics", {})
        records.append(normalize_record(
            route="youtube_data_api_videos_list",
            video_id=video["video_id"],
            values={
                "title": snippet.get("title"), "description": snippet.get("description"),
                "channel_name": snippet.get("channelTitle"),
                "channel_url": f"https://www.youtube.com/channel/{snippet['channelId']}" if snippet.get("channelId") else None,
                "published_at": snippet.get("publishedAt"), "duration_seconds": details.get("duration"),
                "view_count": statistics.get("viewCount"), "like_count": statistics.get("likeCount"),
            },
            description_source="youtube_data_api.snippet.description",
        ))
    return {
        "route": "youtube_data_api", "outcome": "success" if not failures else "partial",
        "tested_at_utc": utc_now(), "attempts": 1, "first_attempt_success": response.ok,
        "elapsed_seconds": round(elapsed, 3), "http_status": response.status_code,
        "quota_information": {"documented_units": 1, "observed_usage_header": None,
                              "note": "videos.list has a documented cost of 1 quota unit per call."},
        "response_evidence": {"top_level_keys": sorted(payload), "items_returned": len(by_id)},
        "failures": failures, "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, default=Path("metadata_sample_10.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/youtube-data-api-latest.json"))
    args = parser.parse_args()
    load_dotenv()
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        print("YOUTUBE_API_KEY is not set; live route untested.")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, run(args.sample, key))
    print(f"Saved YouTube Data API results to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

