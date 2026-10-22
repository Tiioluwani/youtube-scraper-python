# Article test results

Tests were run on October 22, 2026 with Python 3.12.10. The pinned packages were requests 2.34.2, python-dotenv 1.2.4, isodate 0.7.2, Playwright 1.64.0, youtube-transcript-api 1.2.4, yt-dlp 2026.10.21, apify-client 3.3.0, and pytest 9.1.1.

These were small functional checks against fixed public samples, not reliability benchmarks. Live raw responses, credentials, comments, commenter data, raw Apify items, and signed caption URLs are not included in the repository.

## Video metadata routes

The fixed sample in `metadata_sample_10.json` contains ten public videos from Blender's official channel.

| Route | Observed result | Attempts and timing | Field coverage | Observed or documented cost |
|---|---|---|---|---|
| Zenrows Fetch + Extract, earlier run | 10 records returned successfully | All ten succeeded on their first attempts | Every shared-schema field was present | Exact returned cost headers were retained locally; their units were not converted |
| Zenrows Fetch + Extract, later comparison | HTTP 422 `no_data_extracted` for all ten videos | Ten first attempts, no retries, 29.696s | 0 records | Observed `X-Request-Cost: 0` for every failure |
| Zenrows final entry-point check | Both the single-video command and comparison path returned HTTP 422 `no_data_extracted` | One request through each path | 0 records | Observed `X-Request-Cost: 0` for both |
| YouTube Data API | 10 records returned | One first-attempt `videos.list` request, 1.247s | Every shared field present | One quota unit is documented; no quota-usage header was observed |
| yt-dlp | 10 records returned without downloading media | Ten first attempts, 24.544s | Every shared field present | No billing surface |
| Apify `streamers/youtube-scraper` | One actor run returned 10 records after local client compatibility fixes | Actor run 48.912s; actor reported two internal request retries and zero failed pages | Every shared field present | Observed USD 0.04: 10 result events and zero transcript, AI, or date-filter events |
| Plain requests baseline | Initial HTML returned HTTP 200 for one sample video | One request, 4.059s | Embedded ID, title, description, duration, view count, and author were usable | No billing surface |

Descriptions returned by the successful routes did not end in a detected ellipsis. This establishes that each selected source field was preserved without a terminal ellipsis; it does not independently prove that YouTube exposed the creator's complete original description.

The experimental Zenrows Fetch + Python HTML parser was also checked twice. Its corrected run received ten first-attempt HTTP 200 responses in 279.681s, but the documents yielded only placeholder titles and no usable description, channel, publication, duration, view, or like fields. It was judged unsuitable for the article and moved to a local archive outside the repository.

## Channel discovery

| Route and target | Unique regular videos | Requests or scrolls | Elapsed | Stopping reason |
|---|---:|---:|---:|---|
| Zenrows Fetch, 10 | 10 | 1 request | 20.319s | Requested limit reached |
| Zenrows Fetch, 100 | 30 | 3 requests | 106.214s | No progress; partial |
| Zenrows Fetch, 1,000 | 30 | 3 requests | 48.858s | No progress; partial |
| Browser Sessions, 10 | 10 | 0 scrolls | 24.382s | Requested limit reached |
| Browser Sessions, 100 | 100 | 3 scrolls | 27.512s | Requested limit reached |
| Browser Sessions, 1,000 | 1,000 | 33 scrolls | 128.384s | Requested limit reached |

The 30-video Fetch observations do not establish a general Fetch limit. The returned HTML still contained continuation markers, but scrolling did not load more IDs during those runs.

Browser Sessions exposed no billing headers or bandwidth measurement. The documented schedule recorded at test time was 5 credits per session minute plus 25,000 credits per GB; no actual charge was inferred from that schedule.

## Transcript routes

The fixed four-video sample covered manually supplied English captions, automatically generated English captions, an existing manual French track, and a verified captions-disabled video.

Live transcript retrieval was unsuccessful. youtube-transcript-api was blocked while fetching the three existing tracks; the no-caption video raised `TranscriptsDisabled`. Zenrows exposed the requested existing track metadata but returned empty HTTP 200 timed-text bodies for the three captioned videos. No live transcript was normalized, and descriptions were never substituted for captions.

## Additional checks and limitations

- The public Short `https://www.youtube.com/shorts/EycY6jDFK74`, found on Blender's official Shorts tab, received two bounded transport timeouts in the experimental HTML-parser route. No metadata result was claimed.
- A separate channel-metadata experiment also received two bounded transport timeouts, so no live subscriber count was claimed.
- Count normalization fixtures covered integers, zero, comma-separated numbers, K/M/B abbreviations, and missing values. Abbreviated source text was preserved and marked approximate.
- The Zenrows CLI surface was unavailable locally and was not installed, so it remained untested.
- The configured Zenrows MCP example returned `AUTH003`, so MCP metadata remained untested.
- Later Zenrows Extract failures are reported alongside earlier successes; fixture output is not presented as live evidence.
