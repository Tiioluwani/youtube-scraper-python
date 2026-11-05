from browser_channel_discovery import merge_hrefs, video_id_from_href


def test_video_id_from_regular_watch_url():
    assert video_id_from_href("https://www.youtube.com/watch?v=aaaaaaaaaaa") == "aaaaaaaaaaa"


def test_non_watch_and_invalid_ids_are_rejected():
    assert video_id_from_href("https://www.youtube.com/shorts/aaaaaaaaaaa") is None
    assert video_id_from_href("https://example.com/watch?v=aaaaaaaaaaa") is None
    assert video_id_from_href("https://www.youtube.com/watch?v=short") is None


def test_short_id_is_accepted_only_for_shorts_category():
    url = "https://www.youtube.com/shorts/EycY6jDFK74"
    assert video_id_from_href(url) is None
    assert video_id_from_href(url, "shorts") == "EycY6jDFK74"


def test_browser_hrefs_are_deduplicated_and_limited():
    ids = ["aaaaaaaaaaa"]
    added = merge_hrefs(
        ids,
        [
            "https://www.youtube.com/watch?v=aaaaaaaaaaa",
            "https://www.youtube.com/watch?v=bbbbbbbbbbb",
            "https://www.youtube.com/watch?v=ccccccccccc",
        ],
        2,
    )
    assert added == 1
    assert ids == ["aaaaaaaaaaa", "bbbbbbbbbbb"]


def test_browser_short_hrefs_are_deduplicated_and_capped():
    ids = []
    added = merge_hrefs(
        ids,
        [
            "https://www.youtube.com/shorts/EycY6jDFK74",
            "https://www.youtube.com/shorts/EycY6jDFK74?feature=share",
            "https://www.youtube.com/watch?v=aaaaaaaaaaa",
        ],
        10,
        "shorts",
    )
    assert added == 1
    assert ids == ["EycY6jDFK74"]
