"""Extract metadata for the fixed sample with yt-dlp without downloading media."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from yt_dlp import YoutubeDL

from metadata_common import load_sample, normalize_record, utc_now, write_json


def run(sample_path: Path) -> dict:
    videos = load_sample(sample_path)
    records, failures, attempts = [], [], []
    started_all = time.perf_counter()
    options = {
        "skip_download": True, "quiet": True, "no_warnings": True,
        "noplaylist": True, "getcomments": False, "writesubtitles": False,
        "writeautomaticsub": False,
    }
    with YoutubeDL(options) as ydl:
        for video in videos:
            started = time.perf_counter()
            try:
                info = ydl.extract_info(video["url"], download=False)
                attempts.append({"video_id": video["video_id"], "attempt": 1, "success": True,
                                 "elapsed_seconds": round(time.perf_counter() - started, 3)})
                records.append(normalize_record(
                    route="yt_dlp_metadata_no_download", video_id=video["video_id"],
                    values={
                        "title": info.get("title"), "description": info.get("description"),
                        "channel_name": info.get("channel") or info.get("uploader"),
                        "channel_url": info.get("channel_url") or info.get("uploader_url"),
                        "published_at": info.get("upload_date"), "duration_seconds": info.get("duration"),
                        "view_count": info.get("view_count"), "like_count": info.get("like_count"),
                    }, description_source="yt_dlp.description",
                ))
            except Exception as exc:
                attempts.append({"video_id": video["video_id"], "attempt": 1, "success": False,
                                 "elapsed_seconds": round(time.perf_counter() - started, 3),
                                 "exception_type": type(exc).__name__})
                failures.append({"video_id": video["video_id"], "reason": "extraction_failure",
                                 "exception_type": type(exc).__name__})
    return {
        "route": "yt_dlp", "outcome": "success" if not failures else "partial",
        "tested_at_utc": utc_now(), "elapsed_seconds": round(time.perf_counter() - started_all, 3),
        "attempts": attempts, "retry_policy": "No retries.",
        "cost_information": "No quota or billing headers are exposed.",
        "failures": failures, "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, default=Path("metadata_sample_10.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/ytdlp-latest.json"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, run(args.sample))
    print(f"Saved yt-dlp results to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
