# Metadata route comparison — October 22, 2026

This is a functional comparison over the fixed ten-video Blender sample in `metadata_sample_10.json`, not a general success-rate benchmark.

## SEO review rerun — November 3, 2026

At Git revision `08f5f0f11058eb77abece3d47f969cce828fe480`, the normal `youtube_video.py` entry point was invoked once per fixed sample URL, sequentially, with no retries. The unchanged sanitized request was `GET https://api.zenrows.com/v1/` with `mode=auto`, `extract=auto`, the existing metadata-only `extract_fields`, and a 180-second timeout. Credentials were excluded from output and evidence.

| Video ID | HTTP / error | Elapsed | Request ID | Returned metadata fields | Exact observed cost header |
|---|---|---:|---|---|---|
| `sO_lhW8av3U` | 422 `no_data_extracted` | 30.242s | `6ae98871be148034a80cf182d5200c6c` | None | `X-Request-Cost: 0` |
| `SVJiCL3K0j4` | 422 `no_data_extracted` | 2.786s | `6ae9888dfc4856bb2067a22f8e45befa` | None | `X-Request-Cost: 0` |
| `TqP7Hyy_MFo` | 422 `no_data_extracted` | 5.921s | `6ae9889158a7962d8e6ab509e0a4d9f7` | None | `X-Request-Cost: 0` |
| `0wpz3oqb0YA` | 422 `no_data_extracted` | 2.484s | `6ae98897baf02af21904d36a5022b3ea` | None | `X-Request-Cost: 0` |
| `k6l1CK0O_r4` | 422 `no_data_extracted` | 2.093s | `6ae9889ac89d808eb57c151c189bc8d3` | None | `X-Request-Cost: 0` |
| `EJEYFsWwqKk` | 422 `no_data_extracted` | 2.896s | `6ae9889d3e44574f75474b681b914038` | None | `X-Request-Cost: 0` |
| `TXtDfATbe0M` | 422 `no_data_extracted` | 7.637s | `6ae988a07a67770bd10f8fd404ed1045` | None | `X-Request-Cost: 0` |
| `X-zb1FxHuCw` | 422 `no_data_extracted` | 2.211s | `6ae988a8b4ae67df6b04b38229cb762d` | None | `X-Request-Cost: 0` |
| `fQrxjh0jhZM` | 422 `no_data_extracted` | 3.175s | `6ae988ab6d7a9b9150e70d856916e05a` | None | `X-Request-Cost: 0` |
| `7CfDEnHxPWA` | 422 `no_data_extracted` | 5.209s | `6ae988ae03cbcc86504980ff24fe4004` | None | `X-Request-Cost: 0` |

All ten requests reached Zenrows and returned a structured problem response, but none returned `html` or `parsed`. Total measured request time was 64.654 seconds. All shared-schema metadata fields were absent; the canonical URL written by the normalizer was input-derived and is not an extracted field. `X-Key-Credits-Remaining` was not observed.

This rerun's HTTP 422 Extract failures remain distinct from the earlier HTTP 200 Fetch + Extract successes. They are also distinct from the experimental Fetch + Python parser's HTTP 200 responses containing unusable HTML: transport success or an input-derived URL does not establish usable metadata extraction.

## Historical metadata comparison — October 22, 2026

| Route | Actual outcome | Records | Elapsed | Attempts / quota / billing |
| --- | --- | ---: | ---: | --- |
| Plain `requests` baseline | HTTP 200; initial HTML contained `ytInitialPlayerResponse`, `videoDetails`, and usable ID, title, description, duration, view count, and author fields | one inspected page | 4.059s | one request; no billing information |
| yt-dlp 2026.10.21 | Completed without downloading media | 10 | 24.544s | ten first attempts; no retries or billing information |
| Zenrows Fetch + Extract | HTTP 422 `no_data_extracted` for every October 22 comparison attempt | 0 | 29.696s | ten first attempts; `X-Request-Cost` was exactly `0` each time; no retries |
| YouTube Data API | Success; all records returned on the first request | 10 | 1.247s | one request; `videos.list` has a documented cost of 1 quota unit, but no usage header was observed |
| Apify `streamers/youtube-scraper` | Success after fixing local client 3.3 compatibility; one actor submission returned all records | 10 | 48.912s | observed `usage_total_usd: 0.04`; 10 charged `result` events and zero add-on events |

All ten yt-dlp records contained every shared-schema field. Descriptions came from `yt_dlp.description`; none ended in a detected ellipsis. This establishes preservation of that returned source field, not independently that YouTube exposed each creator's entire original description.

The October 22 Zenrows HTTP 422 result is retained separately from the earlier completed run where the same ten videos succeeded on their first attempts. A follow-up request without `extract_fields` also returned `no_data_extracted`, so the evidence does not establish `extract_fields` as the cause. No general route success rate is claimed.

October 22 entry-point verification used `sO_lhW8av3U` from the fixed sample. The single-video CLI and comparison route used the same `fetch_video` implementation, endpoint, parameters, extraction fields, and normalizer; only their timeout values differed. Both returned HTTP 422 `no_data_extracted`, with request IDs `6ada2988586acceadbde2510a2a82a50` and `6ada299bc432e745e88dc0d889715429`, respectively, and both reported `X-Request-Cost: 0`. No implementation regression was found at that stage. The subsequent November 3 ten-video rerun is recorded above.

The YouTube Data API request returned all ten records with every shared-schema field present. Descriptions came from `snippet.description`, and none ended in a detected ellipsis. The API response exposed no quota-usage header; the one-unit value is the documented `videos.list` cost rather than an observed meter reading.

The first Apify client invocation failed locally with `TypeError` before an actor started because client 3.3 uses `run_timeout=timedelta(...)`, not `timeout_secs`. After that confirmed regression was fixed, one actor run processed exactly the ten fixed URLs and returned ten dataset items. The actor internally retried two YouTube requests following HTTP 429/SSL conditions, then reported 10 finished and zero failed pages. A second typed-client compatibility issue occurred while reading the completed `Run` object; the existing successful run and dataset were recovered without starting another actor. All ten normalized records contained every shared field, and no description ended in a detected ellipsis.

Observed Apify billing was `usage_total_usd: 0.04`, with charged events `{result: 10, date-filter: 0, ai-video-description: 0, ai-video-summary: 0, transcribeMinute: 0}`. This is observed run billing, not a derived estimate. The saved actor configuration used exactly ten direct URLs, `transcriptionAndSubtitle: NONE`, subtitle storage disabled, and both AI additions disabled. Raw dataset items and comment-related fields were not saved.

## Browser Sessions transcript findings — November 3, 2026

Two sequential four-video transcript-panel attempts collected zero segments. All four fixed samples reported `transcript_control_missing` at `find_transcript_control`; no language or track type could be selected through the UI, and scrolling could not be evaluated. Session elapsed times were 108.087s and 110.586s. A missing control does not confirm captions are absent. Both sessions were closed in `finally`; actual billing information was unavailable. Per-video timing and requested tracks are recorded in `ARTICLE_TEST_RESULTS.md`. This transcript check does not alter the historical metadata comparison above.

Raw HTML, raw Apify items, comments, commenter data, credentials, request URLs containing credentials, and signed caption URLs are not saved.
