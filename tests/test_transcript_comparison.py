import json

import requests

from transcript_comparison import (
    choose_zenrows_track,
    cost_headers,
    extract_caption_tracks,
    json3_segments,
    normalized_transcript,
)


def test_extract_caption_tracks_and_separate_manual_from_generated():
    tracks = [
        {"baseUrl": "https://example.test/manual", "languageCode": "en"},
        {
            "baseUrl": "https://example.test/generated",
            "languageCode": "en",
            "kind": "asr",
        },
    ]
    page = f'<script>var player={{"captions":{{"captionTracks":{json.dumps(tracks)}}}}};</script>'
    found = extract_caption_tracks(page)
    assert choose_zenrows_track(
        found, {"requested_language_code": "en", "requested_track_type": "manual"}
    )["baseUrl"].endswith("manual")
    assert choose_zenrows_track(
        found, {"requested_language_code": "en", "requested_track_type": "generated"}
    )["baseUrl"].endswith("generated")


def test_unavailable_language_does_not_select_or_translate_another_track():
    tracks = [{"baseUrl": "https://example.test/en", "languageCode": "en"}]
    assert choose_zenrows_track(
        tracks, {"requested_language_code": "fr", "requested_track_type": "manual"}
    ) is None


def test_json3_timing_is_preserved_in_seconds():
    segments = json3_segments(
        {
            "events": [
                {
                    "tStartMs": 1250,
                    "dDurationMs": 2750,
                    "segs": [{"utf8": "Hello"}, {"utf8": " world"}],
                }
            ]
        }
    )
    assert segments == [
        {"text": "Hello world", "start_seconds": 1.25, "duration_seconds": 2.75}
    ]


def test_normalized_transcript_keeps_required_shape():
    record = normalized_transcript(
        "aaaaaaaaaaa",
        "fr",
        "manual",
        [{"text": "Bonjour", "start_seconds": 0, "duration_seconds": 1.5}],
        "fixture",
    )
    assert set(record) == {
        "video_id", "language_code", "track_type", "segments", "source", "fetched_at"
    }
    assert record["segments"][0]["duration_seconds"] == 1.5


def test_cost_headers_omit_target_urls():
    response = requests.Response()
    response.headers.update(
        {"X-Request-Cost": "0.001", "Zr-Final-Url": "https://signed.example.test"}
    )
    assert cost_headers(response) == {"X-Request-Cost": "0.001"}
