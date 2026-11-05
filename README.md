# YouTube Scraper Python

This repository contains the Python scripts for **YouTube Scraper: How to Scrape Video and Channel Data With Python (2026)**, a Zenrows tutorial about collecting public YouTube video metadata and discovering public channel videos and Shorts.

The examples collect metadata and public video URLs only. They do not download media or intentionally collect comments or commenter data.

## Features

- Fetches and normalizes one public video's title, description, channel, publication time, duration, views, and likes with Zenrows Fetch and Extract.
- Preserves unavailable values as `null` and records missing-field reasons.
- Recovers `videoDetails.shortDescription` when it is available in returned page data and records the description source separately from truncation status.
- Discovers unique regular-video or Shorts URLs from a channel with Zenrows Browser Sessions and Playwright.
- Uses bounded channel limits and records elapsed time, scrolling attempts, partial results, and the stopping reason.
- Saves filtered local evidence without raw HTML, comments, credentials, signed URLs, or media.

## Prerequisites

- Python 3.12 or later
- A [Zenrows API key](https://app.zenrows.com/register)

The Browser Sessions example uses the pinned Playwright Python package but connects to a remote Zenrows browser. It does not require a local Playwright browser download.

## Installation

Clone the repository:

```bash
git clone https://github.com/Tiioluwani/youtube-scraper-python.git
cd youtube-scraper-python
```

Create and activate a virtual environment.

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Windows Command Prompt**

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

**macOS or Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Install the development dependencies to run the tests:

```bash
python -m pip install -r requirements-dev.txt
```

## Configuration

Copy `.env.example` to `.env` and add your Zenrows API key:

```dotenv
ZENROWS_API_KEY=replace_with_your_zenrows_api_key
```

The scripts load a local `.env` file when present. You can alternatively set `ZENROWS_API_KEY` in the process environment. `.env` is ignored by Git, and the scripts do not print the key or credential-bearing request URLs.

## Project structure

```text
.
├── .env.example
├── .gitignore
├── LICENSE
├── README.md
├── browser_channel_discovery.py
├── requirements-dev.txt
├── requirements.txt
├── youtube_video.py
├── youtube_video_article.py
└── tests
    ├── fixtures
    │   └── success.json
    ├── test_browser_channel_discovery.py
    └── test_youtube_video.py
```

- `youtube_video.py` is the complete single-video implementation used by the project tests.
- `youtube_video_article.py` is a shorter standalone version suitable for following the article directly.
- `browser_channel_discovery.py` discovers regular videos or Shorts through a remote Browser Session.
- `tests/` contains fixture-based checks and makes no live requests.
- Local runs write ignored evidence under `artifacts/`.

## How it works

### Fetch one video's metadata

Both video scripts accept a public YouTube watch, Shorts, embed, or `youtu.be` URL. They call the Zenrows Fetch endpoint with `mode=auto`, `extract=auto`, and metadata-only extraction fields.

The normalized record contains:

- video ID, canonical URL, title, and description
- channel name and URL
- publication time and duration in seconds
- view and like counts
- UTC fetch time, route, field sources, truncation status, and missing-field reasons

Descriptions and counts remain `null` when unavailable. No missing numeric value is replaced with zero.

### Discover channel videos or Shorts

`browser_channel_discovery.py` connects Playwright to Zenrows Browser Sessions, waits for the YouTube channel grid, collects unique IDs, and scrolls the document when more results are needed. Regular videos and Shorts use separate URL selectors and canonical URL formats.

Discovery stops when the requested limit is reached, the channel is demonstrably exhausted, loading stalls, the session expires, or the request fails. A stalled page is reported as `no_progress`, not as channel exhaustion.

Every remote browser is closed in `finally` on success or failure.

## Running the project

Fetch and normalize the Big Buck Bunny sample with the complete script:

```bash
python youtube_video.py "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
```

Run the shorter standalone article version:

```bash
python youtube_video_article.py "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
```

Discover Blender's regular videos:

```bash
python browser_channel_discovery.py "https://www.youtube.com/@BlenderOfficial/videos" --category videos --limit 10
```

Discover Blender's Shorts:

```bash
python browser_channel_discovery.py "https://www.youtube.com/@BlenderOfficial/shorts" --category shorts --limit 10
```

The supported limits are `10`, `100`, and `1000`. Larger runs use longer remote-session TTLs and may incur higher usage.

Run the fixture-based tests:

```bash
python -m pytest -q
```

## Output

The video scripts create an ignored timestamped directory under `artifacts/` containing:

- `response.filtered.json`: filtered extraction evidence without raw HTML or comments
- `normalized.json`: the shared normalized metadata record
- `run.json`: status, elapsed time, route, request ID, and available billing headers

Failed runs save sanitized error evidence without credentials or credential-bearing request URLs.

Browser Sessions discovery saves unique IDs, canonical URLs, timing, counts, and its stopping reason under `artifacts/`. A partial list is marked as partial.

Live behavior can change. Earlier Fetch and Extract runs returned complete video metadata, while later tests returned `no_data_extracted` for the same sample. Browser Sessions successfully discovered regular videos and the first ten visible Blender Shorts in the recorded local checks. These observations are functional examples, not reliability guarantees.

## Technologies

- Python 3.12+
- [Zenrows Fetch and Extract](https://docs.zenrows.com/fetch/api-reference)
- [Zenrows Browser Sessions](https://docs.zenrows.com/browser-sessions/introduction)
- Requests
- Playwright
- pytest

Zenrows' YouTube scraping product overview is available at [zenrows.com/scrape/youtube](https://www.zenrows.com/scrape/youtube).

## Usage and limitations

Use these examples only for public data and in accordance with YouTube's applicable terms and policies. Page structure, availability, consent flows, and anti-bot behavior can change. HTTP 200 alone does not establish that usable metadata was returned, and a stalled channel grid does not prove that the channel is exhausted.

## License

This project is available under the [MIT License](LICENSE).

## Related article

[**YouTube Scraper: How to Scrape Video and Channel Data With Python (2026)**](https://www.zenrows.com/blog/youtube-scraper-how-to-scrape-video-and-channel-data-with-python-2026)
