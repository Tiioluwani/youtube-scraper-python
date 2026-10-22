"""Inspect one plain requests YouTube response without JavaScript rendering."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import requests

from metadata_common import load_sample, utc_now, write_json


def embedded_video_details(page: str) -> dict:
    marker = '"videoDetails":'
    offset = page.find(marker)
    if offset < 0:
        return {}
    try:
        value, _ = json.JSONDecoder().raw_decode(page[offset + len(marker):])
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def run(sample_path: Path) -> dict:
    video = load_sample(sample_path)[0]
    started = time.perf_counter()
    try:
        response = requests.get(video["url"], timeout=(10, 60))
        body = response.text
    except requests.RequestException as exc:
        return {"route": "plain_requests", "outcome": "transport_error",
                "exception_type": type(exc).__name__,
                "elapsed_seconds": round(time.perf_counter() - started, 3)}
    details = embedded_video_details(body)
    meta_title = re.search(r'<meta\s+(?:name|property)="(?:title|og:title)"\s+content="([^"]*)"', body)
    return {
        "route": "plain_requests", "tested_at_utc": utc_now(), "outcome": "success" if response.ok else "http_error",
        "video_id": video["video_id"], "http_status": response.status_code,
        "elapsed_seconds": round(time.perf_counter() - started, 3), "response_body_bytes": len(response.content),
        "content_type": response.headers.get("Content-Type"),
        "evidence": {
            "yt_initial_player_response_marker": "ytInitialPlayerResponse" in body,
            "embedded_video_details_found": bool(details),
            "embedded_fields_present": {
                key: details.get(key) is not None
                for key in ("videoId", "title", "shortDescription", "lengthSeconds", "viewCount", "author")
            },
            "meta_title_found": bool(meta_title),
            "note": "Raw HTML is not saved; no comments or commenter data are retained.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, default=Path("metadata_sample_10.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/plain-requests-baseline.json"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, run(args.sample))
    print(f"Saved plain requests baseline to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
