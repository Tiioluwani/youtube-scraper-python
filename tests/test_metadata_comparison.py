from pathlib import Path

import requests

from apify_metadata import metadata_only_input
from metadata_common import duration_seconds, load_sample, normalize_record
from metadata_comparison import zenrows_cost_headers
from plain_requests_baseline import embedded_video_details


def test_fixed_metadata_sample_has_ten_unique_canonical_urls():
    videos = load_sample(Path("metadata_sample_10.json"))
    assert len({video["video_id"] for video in videos}) == 10
    assert all(video["url"].endswith(video["video_id"]) for video in videos)


def test_shared_duration_parses_iso_and_clock_formats():
    assert duration_seconds("PT1H2M3S") == 3723
    assert duration_seconds("01:02:03") == 3723
    assert duration_seconds(None) is None


def test_shared_schema_does_not_invent_missing_counts():
    record = normalize_record(
        route="fixture", video_id="aaaaaaaaaaa",
        values={"title": "Title", "description": "Description"},
        description_source="fixture.description",
    )
    assert record["view_count"] is None
    assert record["like_count"] is None
    assert record["field_presence"]["view_count"] is False
    assert record["description_status"]["source_field_preserved_without_ellipsis"] is True


def test_plain_html_embedded_video_details_parser():
    page = '<script>{"videoDetails":{"videoId":"aaaaaaaaaaa","title":"A"}}</script>'
    assert embedded_video_details(page)["title"] == "A"


def test_zenrows_comparison_headers_omit_final_target_url():
    response = requests.Response()
    response.headers.update({"X-Request-Cost": "1", "Zr-Final-Url": "https://example.test"})
    assert zenrows_cost_headers(response) == {"X-Request-Cost": "1"}


def test_apify_input_is_limited_and_disables_paid_additions():
    videos = load_sample(Path("metadata_sample_10.json"))
    actor_input = metadata_only_input(videos)
    assert len(actor_input["startUrls"]) == 10
    assert actor_input["maxResults"] == 10
    assert actor_input["transcriptionAndSubtitle"] == "NONE"
    assert actor_input["saveSubsToKVS"] is False
    assert actor_input["aiVideoDescription"] is False
    assert actor_input["aiVideoSummary"] is False
