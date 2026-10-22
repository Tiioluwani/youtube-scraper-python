"""Discover regular YouTube video IDs through Zenrows Browser Sessions."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from dotenv import load_dotenv
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

CHANNEL_URL = "https://www.youtube.com/@BlenderOfficial/videos"
ALLOWED_LIMITS = (10, 100, 1000)
TTL_BY_LIMIT = {10: "2m", 100: "5m", 1000: "15m"}
TTL_SECONDS = {10: 120, 100: 300, 1000: 900}
MAX_STALLED_SCROLLS = 8
GRID_SELECTOR = "ytd-rich-grid-renderer"
VIDEO_LINK_SELECTOR = f'{GRID_SELECTOR} a[href*="/watch?v="]'


def video_id_from_href(href: str) -> str | None:
    parsed = urlparse(href)
    if parsed.hostname and parsed.hostname not in {"youtube.com", "www.youtube.com"}:
        return None
    candidate = parse_qs(parsed.query).get("v", [None])[0]
    if candidate and len(candidate) == 11:
        return candidate
    return None


def merge_hrefs(ids: list[str], hrefs: list[str], limit: int) -> int:
    known = set(ids)
    before = len(ids)
    for href in hrefs:
        video_id = video_id_from_href(href)
        if video_id and video_id not in known and len(ids) < limit:
            ids.append(video_id)
            known.add(video_id)
    return len(ids) - before


def session_url(api_key: str, ttl: str) -> str:
    return "wss://browser.zenrows.com?" + urlencode(
        {"apikey": api_key, "session_ttl": ttl}
    )


def discover(channel_url: str, limit: int, api_key: str) -> dict:
    ttl = TTL_BY_LIMIT[limit]
    ttl_seconds = TTL_SECONDS[limit]
    ids: list[str] = []
    scroll_attempts = 0
    stalled_scrolls = 0
    stop_reason = "request_failure"
    grid_seen = False
    end_evidence = None
    failure_type = None
    started = time.perf_counter()
    browser = None

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(
                session_url(api_key, ttl), timeout=30_000
            )
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()

            # Media files, images, and fonts are unnecessary for ID discovery.
            def block_heavy_resources(route):
                if route.request.resource_type in {"image", "media", "font"}:
                    route.abort()
                else:
                    route.continue_()

            page.route("**/*", block_heavy_resources)
            page.goto(channel_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_selector(GRID_SELECTOR, timeout=30_000)
            grid_seen = True

            while True:
                hrefs = page.locator(VIDEO_LINK_SELECTOR).evaluate_all(
                    "elements => elements.map(element => element.href)"
                )
                added = merge_hrefs(ids, hrefs, limit)
                if len(ids) >= limit:
                    stop_reason = "requested_limit_reached"
                    break

                elapsed = time.perf_counter() - started
                if elapsed >= ttl_seconds - 15:
                    stop_reason = "session_expired"
                    break

                state = page.evaluate(
                    """() => {
                        const root = document.scrollingElement;
                        const atBottom = root.scrollTop + root.clientHeight >= root.scrollHeight - 5;
                        const continuation = Boolean(document.querySelector('ytd-continuation-item-renderer'));
                        const spinner = Boolean(document.querySelector('ytd-continuation-item-renderer tp-yt-paper-spinner[active]'));
                        return {scrollTop: root.scrollTop, scrollHeight: root.scrollHeight,
                                clientHeight: root.clientHeight, atBottom, continuation, spinner};
                    }"""
                )
                if added == 0:
                    stalled_scrolls += 1
                else:
                    stalled_scrolls = 0

                if (
                    stalled_scrolls >= 3
                    and state["atBottom"]
                    and not state["continuation"]
                    and not state["spinner"]
                ):
                    stop_reason = "channel_exhausted"
                    end_evidence = state
                    break
                if stalled_scrolls >= MAX_STALLED_SCROLLS:
                    stop_reason = "no_progress"
                    end_evidence = state
                    break

                previous_count = page.locator(VIDEO_LINK_SELECTOR).count()
                page.evaluate(
                    """() => {
                        const root = document.scrollingElement;
                        root.scrollTo(0, root.scrollHeight);
                    }"""
                )
                scroll_attempts += 1
                try:
                    page.wait_for_function(
                        "([selector, count]) => document.querySelectorAll(selector).length > count",
                        arg=[VIDEO_LINK_SELECTOR, previous_count],
                        timeout=5_000,
                    )
                except PlaywrightTimeoutError:
                    page.wait_for_timeout(750)

    except PlaywrightTimeoutError as exc:
        stop_reason = "timeout"
        failure_type = type(exc).__name__
    except PlaywrightError as exc:
        elapsed = time.perf_counter() - started
        stop_reason = "session_expired" if elapsed >= ttl_seconds - 15 else "request_failure"
        failure_type = type(exc).__name__
    finally:
        if browser is not None:
            try:
                browser.close()
            except PlaywrightError:
                pass

    elapsed = time.perf_counter() - started
    return {
        "route": "zenrows_browser_sessions_playwright",
        "channel_url": channel_url,
        "requested_limit": limit,
        "unique_collected": len(ids),
        "partial": len(ids) < limit and stop_reason != "channel_exhausted",
        "stopping_reason": stop_reason,
        "elapsed_seconds": round(elapsed, 3),
        "scroll_attempts": scroll_attempts,
        "stalled_scrolls": stalled_scrolls,
        "video_grid_seen": grid_seen,
        "channel_exhaustion_evidence": end_evidence,
        "failure_type": failure_type,
        "configuration": {
            "session_ttl": ttl,
            "session_ttl_seconds": ttl_seconds,
            "grid_selector": GRID_SELECTOR,
            "scroll_container": "document.scrollingElement",
            "max_stalled_scrolls": MAX_STALLED_SCROLLS,
            "blocked_resource_types": ["image", "media", "font"],
        },
        "usage_information": {
            "measured_session_elapsed_seconds": round(elapsed, 3),
            "actual_credits": None,
            "actual_bandwidth_bytes": None,
            "availability_note": "Browser Sessions CDP did not expose billing headers or bandwidth usage to Playwright.",
            "documented_pricing": "5 credits per session minute plus 25,000 credits per GB; not converted into actual usage.",
        },
        "items": [
            {
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
            for video_id in ids
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel_url", nargs="?", default=CHANNEL_URL)
    parser.add_argument("--limit", type=int, choices=ALLOWED_LIMITS, required=True)
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("ZENROWS_API_KEY")
    if not api_key:
        print("ZENROWS_API_KEY is not set.")
        return 2

    result = discover(args.channel_url, args.limit, api_key)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path("artifacts") / f"browser-channel-videos-{args.limit}-{timestamp}"
    run_dir.mkdir(parents=True)
    (run_dir / "discovery.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Saved Browser Sessions run to {run_dir}")
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "requested_limit", "unique_collected", "partial", "elapsed_seconds",
                    "scroll_attempts", "stalled_scrolls", "stopping_reason", "failure_type",
                )
            },
            indent=2,
        )
    )
    return 0 if result["stopping_reason"] in {
        "requested_limit_reached", "channel_exhausted"
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
