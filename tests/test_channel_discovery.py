from channel_discovery import (
    canonical_url,
    merge_unique,
    ordered_video_ids,
    scroll_instructions,
    stopping_reason,
)


def test_video_ids_are_deduplicated_in_first_seen_order():
    html = (
        '{"videoId":"aaaaaaaaaaa"}'
        '{"videoId":"bbbbbbbbbbb"}'
        '{"videoId":"aaaaaaaaaaa"}'
    )
    assert ordered_video_ids(html) == ["aaaaaaaaaaa", "bbbbbbbbbbb"]


def test_escaped_video_ids_are_parsed():
    assert ordered_video_ids(r'{\"videoId\":\"ccccccccccc\"}') == ["ccccccccccc"]


def test_merge_respects_limit_and_deduplicates():
    existing = ["aaaaaaaaaaa"]
    added = merge_unique(existing, ["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"], 2)
    assert added == 1
    assert existing == ["aaaaaaaaaaa", "bbbbbbbbbbb"]


def test_category_urls_remain_separate():
    assert canonical_url("aaaaaaaaaaa", "videos").endswith("watch?v=aaaaaaaaaaa")
    assert canonical_url("aaaaaaaaaaa", "streams").endswith("watch?v=aaaaaaaaaaa")
    assert canonical_url("aaaaaaaaaaa", "shorts").endswith("shorts/aaaaaaaaaaa")


def test_stopping_condition_precedence():
    assert stopping_reason(10, 10, failed=True) == "requested_limit_reached"
    assert stopping_reason(5, 10, timed_out=True) == "timeout"
    assert stopping_reason(5, 10, failed=True) == "request_failure"
    assert stopping_reason(5, 10, no_progress=True) == "no_progress"
    assert stopping_reason(5, 10) == "channel_exhausted"


def test_scroll_instructions_wait_before_documented_scroll_action():
    import json

    instructions = json.loads(scroll_instructions(2))
    assert instructions[0] == {"wait": 2000}
    assert instructions[1] == {"scroll_y": 10000}
    assert instructions[2] == {"wait": 1000}
