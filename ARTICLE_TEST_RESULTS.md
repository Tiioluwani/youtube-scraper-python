# Article test results

Tests were run on October 22, 2026 with Python 3.12.10. The pinned packages were requests 2.34.2, python-dotenv 1.2.4, isodate 0.7.2, Playwright 1.64.0, youtube-transcript-api 1.2.4, yt-dlp 2026.10.21, apify-client 3.3.0, and pytest 9.1.1.

These were small functional checks against fixed public samples, not reliability benchmarks. Live raw responses, credentials, comments, commenter data, raw Apify items, and signed caption URLs are not included in the repository.

## SEO review rerun — November 3, 2026

On November 3, 2026, the normal `youtube_video.py` entry point was run exactly once for each URL in `metadata_sample_10.json`, sequentially and without retries. The repository revision was `08f5f0f11058eb77abece3d47f969cce828fe480`. Sanitized request settings were `GET https://api.zenrows.com/v1/`, `mode=auto`, `extract=auto`, the existing metadata-only `extract_fields`, and the entry point's 180-second timeout. The API key was loaded locally and was neither recorded nor printed.

| Video ID | HTTP | Error code | Elapsed | Request ID | Extracted metadata fields | Exact observed cost header |
|---|---:|---|---:|---|---|---|
| `sO_lhW8av3U` | 422 | `no_data_extracted` | 30.242s | `6ae98871be148034a80cf182d5200c6c` | None | `X-Request-Cost: 0` |
| `SVJiCL3K0j4` | 422 | `no_data_extracted` | 2.786s | `6ae9888dfc4856bb2067a22f8e45befa` | None | `X-Request-Cost: 0` |
| `TqP7Hyy_MFo` | 422 | `no_data_extracted` | 5.921s | `6ae9889158a7962d8e6ab509e0a4d9f7` | None | `X-Request-Cost: 0` |
| `0wpz3oqb0YA` | 422 | `no_data_extracted` | 2.484s | `6ae98897baf02af21904d36a5022b3ea` | None | `X-Request-Cost: 0` |
| `k6l1CK0O_r4` | 422 | `no_data_extracted` | 2.093s | `6ae9889ac89d808eb57c151c189bc8d3` | None | `X-Request-Cost: 0` |
| `EJEYFsWwqKk` | 422 | `no_data_extracted` | 2.896s | `6ae9889d3e44574f75474b681b914038` | None | `X-Request-Cost: 0` |
| `TXtDfATbe0M` | 422 | `no_data_extracted` | 7.637s | `6ae988a07a67770bd10f8fd404ed1045` | None | `X-Request-Cost: 0` |
| `X-zb1FxHuCw` | 422 | `no_data_extracted` | 2.211s | `6ae988a8b4ae67df6b04b38229cb762d` | None | `X-Request-Cost: 0` |
| `fQrxjh0jhZM` | 422 | `no_data_extracted` | 3.175s | `6ae988ab6d7a9b9150e70d856916e05a` | None | `X-Request-Cost: 0` |
| `7CfDEnHxPWA` | 422 | `no_data_extracted` | 5.209s | `6ae988ae03cbcc86504980ff24fe4004` | None | `X-Request-Cost: 0` |

Total measured request time was 64.654 seconds. Every response was an `application/problem+json` document with top-level keys `code`, `detail`, `instance`, `status`, `title`, and `type`; none returned `html` or `parsed`. Consequently, title, description, channel details, publication time, duration, views, likes, and extracted video ID were all missing. The normalized canonical URL was derived from the command-line input and is not counted as extracted metadata. `X-Key-Credits-Remaining` was not present in the saved headers.

These HTTP 422 Extract failures are separate from both the earlier successful HTTP 200 Fetch + Extract records and the experimental Fetch + Python parser's HTTP 200 responses containing unusable placeholder page content. Neither HTTP 200 parser response nor an input-derived URL is treated as successful metadata extraction.

## Historical video metadata routes — October 22, 2026

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

## Channel discovery — October 22, 2026

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

## Transcript routes — October 22, 2026

The fixed four-video sample covered manually supplied English captions, automatically generated English captions, an existing manual French track, and a verified captions-disabled video.

Live transcript retrieval was unsuccessful. youtube-transcript-api was blocked while fetching the three existing tracks; the no-caption video raised `TranscriptsDisabled`. Zenrows exposed the requested existing track metadata but returned empty HTTP 200 timed-text bodies for the three captioned videos. No live transcript was normalized, and descriptions were never substituted for captions.

### Browser Sessions transcript-panel check — November 3, 2026

Python Playwright 1.64.0 connected to Zenrows Browser Sessions and visited the same four fixed videos sequentially. The exact command was `.\.venv\Scripts\python.exe browser_transcripts.py --sample-file transcript_samples.json`. The first attempt used the existing Browser Sessions CDP setup. Because it failed to find a transcript control on all three videos already known from the frozen sample to have caption tracks, one bounded retry added only consent handling, metadata scrolling, and wrapper-independent visible-text lookup. No Fetch route, transcript API route, metadata comparison, translation, generated transcription, media request, or description fallback was used.

| Video ID | Requested track | First attempt | Corrected retry | Selected track | Segments | Failure stage |
|---|---|---:|---:|---|---:|---|
| `arj7oStGLkU` | English manual | 28.061s | 28.159s | None | 0 | `find_transcript_control` |
| `sO_lhW8av3U` | English automatically generated | 30.650s | 33.247s | None | 0 | `find_transcript_control` |
| `XfezG5M2ICg` | French manual | 21.387s | 23.718s | None | 0 | `find_transcript_control` |
| `aqz-KE-bpKQ` | No track requested | 19.664s | 21.651s | None | 0 | `find_transcript_control` |

Both sessions loaded an attached YouTube watch-page shell for every sample, but no transcript control or transcript panel became visible. The first session took 108.087 seconds and the corrected retry took 110.586 seconds, for 218.673 seconds total, within the ten-minute bound. Each browser was closed in `finally`. Browser Sessions exposed no billing headers, actual credit count, or bandwidth meter to Playwright.

These results establish only that the transcript control was missing from the rendered UI available to these sessions. They do not confirm captions were absent, including for the Big Buck Bunny no-caption sample. Because no panel opened, language and manual/generated track type could not be independently verified through the UI, transcript scrolling could not be tested, and no segment or timestamp was collected. The unsuccessful experimental script and its fixture tests were not retained as a working repository route; both sanitized attempt records remain locally under ignored `artifacts/browser-transcripts-*` directories.

## Additional checks and limitations

- The public Short `https://www.youtube.com/shorts/EycY6jDFK74`, found on Blender's official Shorts tab, received two bounded transport timeouts in the experimental HTML-parser route. No metadata result was claimed.
- A separate channel-metadata experiment also received two bounded transport timeouts, so no live subscriber count was claimed.
- Count normalization fixtures covered integers, zero, comma-separated numbers, K/M/B abbreviations, and missing values. Abbreviated source text was preserved and marked approximate.
- The Zenrows CLI surface was unavailable locally and was not installed, so it remained untested.
- The configured Zenrows MCP example returned `AUTH003`, so MCP metadata remained untested.
- Later Zenrows Extract failures are reported alongside earlier successes; fixture output is not presented as live evidence.
