"""Compare existing YouTube captions via youtube-transcript-api and Zenrows Fetch."""

from __future__ import annotations

import argparse
import html as html_module
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi

from youtube_video import API_URL, BILLING_HEADERS

SAMPLE_FILE = Path("transcript_samples.json")
ARTIFACTS_DIR = Path("artifacts")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def classify_exception(exc: BaseException) -> str:
    name = type(exc).__name__
    if name == "TranscriptsDisabled":
        return "absent_captions"
    if name in {"NoTranscriptFound", "NotTranslatable"}:
        return "unavailable_requested_language"
    if name in {"RequestBlocked", "IpBlocked", "PoTokenRequired"}:
        return "blocking"
    if isinstance(exc, (requests.Timeout, TimeoutError)):
        return "transport_error"
    if isinstance(exc, requests.RequestException) or name in {
        "YouTubeRequestFailed", "VideoUnavailable", "AgeRestricted"
    }:
        return "transport_error"
    return "parsing_failure"


def normalized_transcript(
    video_id: str,
    language_code: str,
    track_type: str,
    segments: list[dict[str, Any]],
    source: str,
) -> dict[str, Any]:
    return {
        "video_id": video_id,
        "language_code": language_code,
        "track_type": track_type,
        "segments": [
            {
                "text": segment["text"],
                "start_seconds": float(segment["start_seconds"]),
                "duration_seconds": float(segment["duration_seconds"]),
            }
            for segment in segments
        ],
        "source": source,
        "fetched_at": utc_now(),
    }


def choose_yta_track(transcripts: Any, sample: dict[str, Any]) -> Any:
    language = sample["requested_language_code"]
    track_type = sample["requested_track_type"]
    if track_type == "manual":
        return transcripts.find_manually_created_transcript([language])
    if track_type == "generated":
        return transcripts.find_generated_transcript([language])
    raise ValueError("The no-caption sample does not request a track.")


def run_yta(sample: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    attempts: list[dict[str, Any]] = []
    api = YouTubeTranscriptApi()
    try:
        listed = api.list(sample["video_id"])
        tracks = list(listed)
        attempts.append({"operation": "list", "outcome": "success"})
        available = [
            {
                "language_code": track.language_code,
                "track_type": "generated" if track.is_generated else "manual",
                "is_translatable": track.is_translatable,
            }
            for track in tracks
        ]
        if sample["category"] == "no_captions":
            return {
                "route": "youtube-transcript-api",
                "outcome": "unexpected_captions_available" if tracks else "absent_captions",
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "attempt_count": len(attempts),
                "attempts": attempts,
                "available_tracks": available,
                "transcript": None,
                "cost_information": "No per-request billing or cost headers are exposed.",
            }
        selected = choose_yta_track(listed, sample)
        fetched = selected.fetch()
        attempts.append({"operation": "fetch_selected_track", "outcome": "success"})
        segments = [
            {
                "text": snippet.text,
                "start_seconds": snippet.start,
                "duration_seconds": snippet.duration,
            }
            for snippet in fetched
        ]
        return {
            "route": "youtube-transcript-api",
            "outcome": "success",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "attempt_count": len(attempts),
            "attempts": attempts,
            "available_tracks": available,
            "transcript": normalized_transcript(
                sample["video_id"],
                fetched.language_code,
                "generated" if fetched.is_generated else "manual",
                segments,
                "youtube-transcript-api existing YouTube caption track",
            ),
            "cost_information": "No per-request billing or cost headers are exposed.",
        }
    except Exception as exc:
        outcome = classify_exception(exc)
        attempts.append(
            {"operation": "list_or_fetch", "outcome": outcome, "exception_type": type(exc).__name__}
        )
        return {
            "route": "youtube-transcript-api",
            "outcome": outcome,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "attempt_count": len(attempts),
            "attempts": attempts,
            "available_tracks": None,
            "transcript": None,
            "cost_information": "No per-request billing or cost headers are exposed.",
        }


def extract_caption_tracks(page_html: str) -> list[dict[str, Any]]:
    decoded_html = html_module.unescape(page_html)
    decoder = json.JSONDecoder()
    for marker in ('"captionTracks":', '\\"captionTracks\\":'):
        for match in re.finditer(re.escape(marker), decoded_html):
            remainder = decoded_html[match.end():]
            if marker.startswith("\\"):
                remainder = remainder.replace('\\"', '"').replace("\\u0026", "&")
            start = remainder.find("[")
            if start < 0:
                continue
            try:
                value, _ = decoder.raw_decode(remainder[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, list):
                return [track for track in value if isinstance(track, dict)]
    return []


def caption_track_summary(track: dict[str, Any]) -> dict[str, Any]:
    name = track.get("name")
    label = name.get("simpleText") if isinstance(name, dict) else None
    return {
        "language_code": track.get("languageCode"),
        "track_type": "generated" if track.get("kind") == "asr" else "manual",
        "label": label,
        "is_translatable": track.get("isTranslatable"),
    }


def choose_zenrows_track(
    tracks: list[dict[str, Any]], sample: dict[str, Any]
) -> dict[str, Any] | None:
    for track in tracks:
        generated = track.get("kind") == "asr"
        if track.get("languageCode") != sample["requested_language_code"]:
            continue
        if sample["requested_track_type"] == "generated" and generated:
            return track
        if sample["requested_track_type"] == "manual" and not generated:
            return track
    return None


def with_json3_format(url: str) -> str:
    parts = urlsplit(url.replace("\\u0026", "&"))
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["fmt"] = "json3"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def cost_headers(response: requests.Response) -> dict[str, str]:
    return {
        name: response.headers[name]
        for name in BILLING_HEADERS
        if name in response.headers and name.lower() != "zr-final-url"
    }


def json3_segments(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise ValueError("Caption response is not YouTube JSON3.")
    output: list[dict[str, Any]] = []
    for event in payload["events"]:
        if not isinstance(event, dict) or not isinstance(event.get("segs"), list):
            continue
        text = "".join(
            segment.get("utf8", "")
            for segment in event["segs"]
            if isinstance(segment, dict)
        ).strip()
        if not text:
            continue
        output.append(
            {
                "text": text,
                "start_seconds": event.get("tStartMs", 0) / 1000,
                "duration_seconds": event.get("dDurationMs", 0) / 1000,
            }
        )
    return output


def fetch_through_zenrows(
    target_url: str, api_key: str, *, extract: bool
) -> tuple[requests.Response, float]:
    params: dict[str, Any] = {"apikey": api_key, "url": target_url, "mode": "auto"}
    if extract:
        params["extract"] = "auto"
    started = time.perf_counter()
    response = requests.get(API_URL, params=params, timeout=(10, 180))
    return response, time.perf_counter() - started


def run_zenrows(sample: dict[str, Any], api_key: str) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.perf_counter()
    attempts: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {
        "video_id": sample["video_id"],
        "artifact_note": "Filtered evidence; raw HTML, caption endpoint URLs, comments, and credentials are omitted.",
    }
    try:
        response, elapsed = fetch_through_zenrows(sample["url"], api_key, extract=True)
        attempt = {
            "operation": "fetch_watch_page_with_extract_auto",
            "http_status": response.status_code,
            "elapsed_seconds": round(elapsed, 3),
            "cost_headers": cost_headers(response),
        }
        attempts.append(attempt)
        if not response.ok:
            return zenrows_failure("request_failure", started, attempts), evidence
        try:
            payload = response.json()
        except (requests.exceptions.JSONDecodeError, ValueError):
            return zenrows_failure("parsing_failure", started, attempts), evidence
        parsed = payload.get("parsed") if isinstance(payload, dict) else None
        html = payload.get("html") if isinstance(payload, dict) else None
        evidence["watch_response"] = {
            "top_level_keys": sorted(payload) if isinstance(payload, dict) else None,
            "parsed_keys": sorted(parsed) if isinstance(parsed, dict) else None,
            "html_returned": isinstance(html, str),
            "html_characters": len(html) if isinstance(html, str) else None,
            "extract_transcript_field_present": isinstance(parsed, dict)
            and any(key in parsed for key in ("transcript", "transcripts", "captions")),
        }
        tracks = extract_caption_tracks(html) if isinstance(html, str) else []
        evidence["caption_tracks"] = [caption_track_summary(track) for track in tracks]
        if sample["category"] == "no_captions":
            outcome = "unexpected_captions_available" if tracks else "absent_captions"
            return zenrows_result(outcome, started, attempts, None), evidence
        selected = choose_zenrows_track(tracks, sample)
        if selected is None:
            outcome = "unavailable_requested_language" if tracks else "parsing_failure"
            return zenrows_result(outcome, started, attempts, None), evidence
        base_url = selected.get("baseUrl")
        if not isinstance(base_url, str):
            return zenrows_result("parsing_failure", started, attempts, None), evidence
        caption_response, caption_elapsed = fetch_through_zenrows(
            with_json3_format(base_url), api_key, extract=False
        )
        attempts.append(
            {
                "operation": "fetch_existing_caption_track",
                "http_status": caption_response.status_code,
                "elapsed_seconds": round(caption_elapsed, 3),
                "cost_headers": cost_headers(caption_response),
            }
        )
        evidence["caption_response"] = {
            "http_status": caption_response.status_code,
            "body_bytes": len(caption_response.content),
            "content_type": caption_response.headers.get("Content-Type"),
            "body_empty": len(caption_response.content) == 0,
        }
        if not caption_response.ok:
            return zenrows_result("request_failure", started, attempts, None), evidence
        try:
            segments = json3_segments(caption_response.json())
        except (requests.exceptions.JSONDecodeError, ValueError, TypeError):
            return zenrows_result("parsing_failure", started, attempts, None), evidence
        if not segments:
            return zenrows_result("parsing_failure", started, attempts, None), evidence
        track_type = "generated" if selected.get("kind") == "asr" else "manual"
        transcript = normalized_transcript(
            sample["video_id"],
            selected.get("languageCode"),
            track_type,
            segments,
            "Zenrows Fetch of existing YouTube caption track discovered in watch-page data",
        )
        return zenrows_result("success", started, attempts, transcript), evidence
    except requests.Timeout as exc:
        attempts.append({"operation": "request", "outcome": "transport_error", "exception_type": type(exc).__name__})
        return zenrows_failure("transport_error", started, attempts), evidence
    except requests.RequestException as exc:
        attempts.append({"operation": "request", "outcome": "transport_error", "exception_type": type(exc).__name__})
        return zenrows_failure("transport_error", started, attempts), evidence


def zenrows_result(
    outcome: str,
    started: float,
    attempts: list[dict[str, Any]],
    transcript: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "route": "zenrows_fetch",
        "outcome": outcome,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "attempt_count": len(attempts),
        "attempts": attempts,
        "transcript": transcript,
        "cost_information": "Exact returned cost headers are recorded per attempt; their units are not converted.",
    }


def zenrows_failure(
    outcome: str, started: float, attempts: list[dict[str, Any]]
) -> dict[str, Any]:
    return zenrows_result(outcome, started, attempts, None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-file", type=Path, default=SAMPLE_FILE)
    args = parser.parse_args()
    load_dotenv()
    api_key = os.getenv("ZENROWS_API_KEY")
    if not api_key:
        print("ZENROWS_API_KEY is not set.")
        return 2
    sample_document = json.loads(args.sample_file.read_text(encoding="utf-8"))
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = ARTIFACTS_DIR / f"transcripts-{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "sample.json").write_text(
        json.dumps(sample_document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    results: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for sample in sample_document["samples"]:
        yta = run_yta(sample)
        zenrows, filtered = run_zenrows(sample, api_key)
        results.append({"sample": sample, "youtube_transcript_api": yta, "zenrows_fetch": zenrows})
        evidence.append(filtered)
    output = {
        "tested_at_utc": utc_now(),
        "scope_note": "Four-video functional comparison; not a reliability benchmark.",
        "retry_policy": "No retries. Every network operation is recorded as one attempt.",
        "results": results,
    }
    (run_dir / "results.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (run_dir / "zenrows-evidence.filtered.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    summary = [
        {
            "video_id": row["sample"]["video_id"],
            "category": row["sample"]["category"],
            "youtube_transcript_api": row["youtube_transcript_api"]["outcome"],
            "zenrows_fetch": row["zenrows_fetch"]["outcome"],
        }
        for row in results
    ]
    print(f"Saved transcript comparison to {run_dir}")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
