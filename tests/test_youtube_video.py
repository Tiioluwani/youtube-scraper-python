import json
from pathlib import Path

import pytest

from requests import Response

from youtube_video import (
    InputError,
    _safe_error,
    canonical_video_url,
    filter_response_for_storage,
    normalize_response,
)

FIXTURE = Path(__file__).parent / "fixtures" / "success.json"


def test_normalizes_documented_response_and_preserves_raw_count_string():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    record = normalize_response(
        payload,
        "https://youtu.be/aqz-KE-bpKQ?si=tracking",
        fetched_at="2026-10-22T12:00:00Z",
    )

    assert record["video_id"] == "aqz-KE-bpKQ"
    assert record["duration_seconds"] == 123
    assert record["view_count"] == 123456
    assert record["like_count"] == "1.2K"
    assert record["field_presence"]["description"] is True
    assert record["description_status"]["ellipsis_truncation_detected"] is True
    assert "truncated" in record["missing_field_reasons"]["description"]


def test_missing_parsed_is_reported_as_extraction_failure():
    record = normalize_response(
        {"html": "<html></html>"},
        "https://www.youtube.com/watch?v=aqz-KE-bpKQ",
        fetched_at="2026-10-22T12:00:00Z",
    )

    assert record["title"] is None
    assert "no parsed key" in record["missing_field_reasons"]["title"]
    assert record["url"] == "https://www.youtube.com/watch?v=aqz-KE-bpKQ"


def test_full_embedded_description_replaces_truncated_parsed_description():
    payload = {
        "html": '<script>{"videoDetails":{"shortDescription":"Complete description\\nSecond line"}}</script>',
        "parsed": {"video": {"description": "Complete desc..."}},
    }

    record = normalize_response(
        payload,
        "https://www.youtube.com/watch?v=aqz-KE-bpKQ",
        fetched_at="2026-10-22T12:00:00Z",
    )

    assert record["description"] == "Complete description\nSecond line"
    assert record["field_sources"]["description"].endswith("videoDetails.shortDescription")
    assert record["description_status"]["source_field_preserved_without_ellipsis"] is True
    assert "description" not in record["missing_field_reasons"]


def test_invalid_duration_is_null_with_specific_reason():
    payload = {"parsed": {"video": {"duration_iso": "not-a-duration"}}}
    record = normalize_response(
        payload,
        "https://www.youtube.com/watch?v=aqz-KE-bpKQ",
        fetched_at="2026-10-22T12:00:00Z",
    )

    assert record["duration_seconds"] is None
    assert record["missing_field_reasons"]["duration_seconds"].endswith("present but invalid")


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=aqz-KE-bpKQ&t=4",
        "https://youtu.be/aqz-KE-bpKQ?si=tracking",
        "https://www.youtube.com/shorts/aqz-KE-bpKQ",
    ],
)
def test_supported_urls_are_canonicalized(url):
    assert canonical_video_url(url) == "https://www.youtube.com/watch?v=aqz-KE-bpKQ"


def test_channel_url_is_rejected():
    with pytest.raises(InputError):
        canonical_video_url("https://www.youtube.com/@Google")


def test_http_error_does_not_include_request_url_or_credentials():
    response = Response()
    response.status_code = 401
    response.url = "https://api.zenrows.com/v1/?apikey=REDACTED&url=https://youtube.com"
    response.headers["X-Request-Id"] = "safe-id"

    message = _safe_error(response)

    assert message == "Zenrows returned HTTP 401 (request id: safe-id)."
    assert "secret" not in message


def test_saved_response_filter_excludes_comments_and_html():
    filtered = filter_response_for_storage(
        {
            "html": "raw page with possible comments",
            "parsed": {
                "video": {"title": "Title"},
                "channel": {"name": "Channel"},
                "engagement": {"view_count": 1},
                "comments": [{"text": "excluded"}],
            },
        }
    )

    assert set(filtered["parsed"]) == {"video", "channel", "engagement"}
    assert "html" not in filtered
    assert "excluded" not in json.dumps(filtered)

