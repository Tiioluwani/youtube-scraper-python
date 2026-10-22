# Metadata route comparison — October 22, 2026

This is a functional comparison over the fixed ten-video Blender sample in `metadata_sample_10.json`, not a general success-rate benchmark.

| Route | Actual outcome | Records | Elapsed | Attempts / quota / billing |
| --- | --- | ---: | ---: | --- |
| Plain `requests` baseline | HTTP 200; initial HTML contained `ytInitialPlayerResponse`, `videoDetails`, and usable ID, title, description, duration, view count, and author fields | one inspected page | 4.059s | one request; no billing information |
| yt-dlp 2026.10.21 | Completed without downloading media | 10 | 24.544s | ten first attempts; no retries or billing information |
| Zenrows Fetch + Extract | HTTP 422 `no_data_extracted` for every current first attempt | 0 | 29.696s | ten first attempts; `X-Request-Cost` was exactly `0` each time; no retries |
| YouTube Data API | Success; all records returned on the first request | 10 | 1.247s | one request; `videos.list` has a documented cost of 1 quota unit, but no usage header was observed |
| Apify `streamers/youtube-scraper` | Success after fixing local client 3.3 compatibility; one actor submission returned all records | 10 | 48.912s | observed `usage_total_usd: 0.04`; 10 charged `result` events and zero add-on events |

All ten yt-dlp records contained every shared-schema field. Descriptions came from `yt_dlp.description`; none ended in a detected ellipsis. This establishes preservation of that returned source field, not independently that YouTube exposed each creator's entire original description.

The current Zenrows HTTP 422 result is retained separately from the earlier completed run where the same ten videos succeeded on their first attempts. A follow-up request without `extract_fields` also returned `no_data_extracted`, so the evidence does not establish `extract_fields` as the cause. No general route success rate is claimed.

Final entry-point verification used `sO_lhW8av3U` from the fixed sample. The single-video CLI and comparison route use the same `fetch_video` implementation, endpoint, parameters, extraction fields, and normalizer; only their timeout values differ. Both returned HTTP 422 `no_data_extracted`, with request IDs `6ada2988586acceadbde2510a2a82a50` and `6ada299bc432e745e88dc0d889715429`, respectively, and both reported `X-Request-Cost: 0`. No implementation regression was found, so the ten-video comparison was not rerun.

The YouTube Data API request returned all ten records with every shared-schema field present. Descriptions came from `snippet.description`, and none ended in a detected ellipsis. The API response exposed no quota-usage header; the one-unit value is the documented `videos.list` cost rather than an observed meter reading.

The first Apify client invocation failed locally with `TypeError` before an actor started because client 3.3 uses `run_timeout=timedelta(...)`, not `timeout_secs`. After that confirmed regression was fixed, one actor run processed exactly the ten fixed URLs and returned ten dataset items. The actor internally retried two YouTube requests following HTTP 429/SSL conditions, then reported 10 finished and zero failed pages. A second typed-client compatibility issue occurred while reading the completed `Run` object; the existing successful run and dataset were recovered without starting another actor. All ten normalized records contained every shared field, and no description ended in a detected ellipsis.

Observed Apify billing was `usage_total_usd: 0.04`, with charged events `{result: 10, date-filter: 0, ai-video-description: 0, ai-video-summary: 0, transcribeMinute: 0}`. This is observed run billing, not a derived estimate. The saved actor configuration used exactly ten direct URLs, `transcriptionAndSubtitle: NONE`, subtitle storage disabled, and both AI additions disabled. Raw dataset items and comment-related fields were not saved.

Raw HTML, raw Apify items, comments, commenter data, credentials, request URLs containing credentials, and signed caption URLs are not saved.
