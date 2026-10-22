# YouTube Scraper Python

## Description

This repository accompanies a Zenrows tutorial about collecting public YouTube video and channel data with Python. It contains focused examples for one-video metadata extraction, channel discovery, transcript-route checks, and metadata-provider comparisons.

The examples collect public metadata only. They do not download video media or intentionally collect comments or commenter data.

## Features

- Fetches and normalizes one public video's title, description, channel, publication time, duration, views, and likes with Zenrows Fetch + Extract.
- Discovers separate regular-video, Shorts, and stream IDs from a channel with Zenrows Fetch.
- Provides a Playwright Browser Sessions route for scrolling a channel's regular-video grid.
- Compares a fixed ten-video sample across Zenrows, YouTube Data API, yt-dlp, Apify, and a plain HTTP baseline.
- Checks existing caption tracks with `youtube-transcript-api` and Zenrows without downloading media or generating transcription.
- Preserves missing fields as `null`, keeps raw count strings where applicable, and qualifies description completeness.
- Saves filtered local evidence without raw HTML, comments, credentials, or signed caption URLs.

## Prerequisites

- Python 3.12 or later
- A Zenrows API key
- Optional `YOUTUBE_API_KEY` for the YouTube Data API comparison
- Optional `APIFY_API_TOKEN` for the Apify comparison

The separate Browser Sessions route uses the pinned Playwright Python package and connects to Zenrows remotely; it does not require a locally downloaded Playwright browser.

## Installation

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

## Configuration

Copy `.env.example` to `.env` and replace only the credentials needed by the routes you plan to run:

```dotenv
ZENROWS_API_KEY=replace_with_your_zenrows_api_key
YOUTUBE_API_KEY=replace_with_your_youtube_data_api_key
APIFY_API_TOKEN=replace_with_your_apify_api_token
```

Alternatively, set the same names as process environment variables. `.env` is ignored by Git, and the scripts do not print credentials or credential-bearing request URLs.

## Project structure

```text
.
├── .env.example
├── .gitignore
├── ARTICLE_TEST_RESULTS.md
├── README.md
├── apify_metadata.py
├── browser_channel_discovery.py
├── channel_discovery.py
├── metadata_common.py
├── metadata_comparison.py
├── metadata_comparison_report.md
├── metadata_sample_10.json
├── plain_requests_baseline.py
├── requirements-dev.txt
├── requirements.txt
├── transcript_comparison.py
├── transcript_samples.json
├── youtube_data_api_metadata.py
├── youtube_video.py
├── ytdlp_metadata.py
└── tests
    ├── fixtures/success.json
    ├── test_browser_channel_discovery.py
    ├── test_channel_discovery.py
    ├── test_metadata_comparison.py
    ├── test_transcript_comparison.py
    └── test_youtube_video.py
```

Local runs write ignored evidence under `artifacts/`. The repository contains fixed sample definitions and sanitized summaries, not live raw responses.

## How it works

`youtube_video.py` canonicalizes a supplied YouTube video URL and calls `GET https://api.zenrows.com/v1/` with `mode=auto`, `extract=auto`, and metadata-only `extract_fields`. It never combines Adaptive Stealth Mode with manual `js_render` or `premium_proxy` parameters. The normalizer reads `parsed.video`, `parsed.channel`, and `parsed.engagement`, records field sources and missing reasons, and converts supported durations to seconds.

When a returned description ends in an ellipsis, the implementation checks decoded `videoDetails.shortDescription` in the in-memory response HTML. Finding that source field without an ellipsis establishes only that the selected source field was preserved; it does not independently prove that YouTube exposed the creator's complete original description. Raw HTML is not saved.

`channel_discovery.py` keeps regular videos, Shorts, and streams separate, deduplicates IDs, and records whether it stopped because the target was reached, the channel was exhausted, progress stalled, a timeout occurred, or a request failed. `browser_channel_discovery.py` is a separate Playwright route that scrolls the channel grid and reliably closes its remote session.

The comparison scripts share the schema in `metadata_common.py` and the frozen sample in `metadata_sample_10.json`. yt-dlp runs without downloading media, Apify disables comments, transcript storage, and AI additions, and the transcript comparison never substitutes descriptions for captions.

## Running the project

Fetch one public video with Zenrows Fetch + Extract:

```powershell
python youtube_video.py "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
```

Discover Blender's regular videos with Zenrows Fetch:

```powershell
python channel_discovery.py "https://www.youtube.com/@BlenderOfficial" --category videos --limit 10 --fetch-metadata-first 10 --metadata-connection-retries 1 --metadata-timeout-seconds 60
python channel_discovery.py "https://www.youtube.com/@BlenderOfficial" --category videos --limit 100
python channel_discovery.py "https://www.youtube.com/@BlenderOfficial" --category videos --limit 1000
```

Use `--category shorts` or `--category streams` to request those tabs without merging categories.

Run the separate Browser Sessions discovery route:

```powershell
python browser_channel_discovery.py "https://www.youtube.com/@BlenderOfficial/videos" --limit 10
python browser_channel_discovery.py "https://www.youtube.com/@BlenderOfficial/videos" --limit 100
python browser_channel_discovery.py "https://www.youtube.com/@BlenderOfficial/videos" --limit 1000
```

Run the fixed transcript comparison:

```powershell
python transcript_comparison.py
```

Run all retained metadata comparison routes or one route at a time:

```powershell
python metadata_comparison.py
python youtube_data_api_metadata.py
python ytdlp_metadata.py
python apify_metadata.py
python plain_requests_baseline.py
```

Run fixture-based checks:

```powershell
python -m pytest -q
```

## Output

Successful one-video runs create ignored timestamped folders containing `response.filtered.json`, `normalized.json`, and `run.json`. Failures are recorded without credential-bearing URLs. Channel, transcript, and comparison scripts likewise save filtered JSON evidence under `artifacts/`.

Observed results on October 22, 2026 were mixed and should not be treated as a reliability benchmark:

- An earlier Zenrows Fetch + Extract run returned complete metadata for the ten fixed Blender videos, and the documented single-video example also succeeded. Later runs against the same sample returned HTTP 422 `no_data_extracted`, including both normal entry points. Those later failures remain the current limitation and are not hidden by the earlier successes.
- Zenrows Fetch channel discovery reached 10 videos, but the 100- and 1,000-video runs stopped at 30 with `no_progress`. This does not establish a general 30-video Fetch limit.
- Browser Sessions reached 10/10, 100/100, and 1,000/1,000 regular videos with 0, 3, and 33 scroll attempts respectively.
- YouTube Data API, yt-dlp, and Apify each returned all ten fixed metadata records in their completed live runs. Apify reported observed billing of USD 0.04 for ten result events; the YouTube Data API exposed no quota-usage header.
- Live transcript retrieval was unsuccessful. YouTube blocked caption fetching for the three captioned samples, while Zenrows returned empty timed-text bodies. The verified no-caption sample reported captions disabled.
- A plain `requests` baseline returned initial HTML containing usable embedded metadata for one sample video, showing that JavaScript rendering was not required for every inspected field.
- The experimental Fetch + Python HTML parser remained unable to recover usable shared-schema metadata and was removed from the repository rather than presented as a supported route.
- A Zenrows CLI metadata example was untested because that client was unavailable. A configured Zenrows MCP example returned `AUTH003`, so MCP metadata was also untested.

See `ARTICLE_TEST_RESULTS.md` for the concise outcome matrix and `metadata_comparison_report.md` for the ten-video metadata comparison.

## Technologies

- Python 3.12+
- Zenrows Fetch, Extract, and Browser Sessions
- Requests
- Playwright
- YouTube Data API
- yt-dlp
- Apify Python client
- youtube-transcript-api
- pytest

Zenrows product overview: https://www.zenrows.com/scrape/youtube

## Related article

YouTube Scraper: How to Scrape Video and Channel Data With Python (2026)

https://www.zenrows.com/blog/youtube-scraper-how-to-scrape-video-and-channel-data-with-python-2026
