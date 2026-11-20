# Sample questions

Questions this app can answer today, with the exact API JSON for each. The doorbell-camera and meeting-room framing is an illustration: replace the queries, dates and recording IDs with your own. Every answer is evidence to check in the player, not proof of absence or an exact count.

The browser asks the same questions. It detects scope words such as "today" or "this month", and it switches paths when you attach an image. The API examples below show what the browser sends.

Before you ask (setup is in the [README](../README.md)):

- `visual` and `hybrid` need a ready visual index: `POST /recordings/{id}/visual-index`.
- `description` and `hybrid` need a ready description index: `POST /recordings/{id}/description-index`, plus a configured vision service.
- `speech` needs a transcript build: `POST /recordings/{id}/transcript-index` (local ASR) or `POST /recordings/{id}/subtitles` (SRT/VTT).
- Date scopes need capture dates on the recordings.
- `RECORDING_UUID` is the `result.recording_id` of a finished import job.

## 1. Find an action

**1. "Did any delivery driver come to the front door?"** — visual candidates.

`POST /search`

```json
{"query":"a delivery driver at the front door","limit":5}
```

**2. The same question against generated descriptions.**

`POST /search`

```json
{"query":"a delivery driver at the front door","path":"description","limit":5}
```

**3. "Did someone carry a package to the door?"** — both paths fused.

`POST /search`

```json
{"query":"a person carries a package to the door","path":"hybrid","limit":8}
```

**4. One camera only.**

`POST /search`

```json
{"query":"a person at the door","recording_ids":["RECORDING_UUID"],"limit":5}
```

**5. An evening span.** Seconds are relative to the start of each selected recording, not wall-clock time.

`POST /search`

```json
{"query":"a person walks up to the door","start_seconds":68400,"end_seconds":72000,"limit":5}
```

**6. The same question, model-checked on the server.** Retrieval runs first; then the vision model checks up to `max_checks` candidate intervals against sampled source frames.

`POST /evidence-search`

```json
{"query":"a person opens the door and enters","path":"description","limit":12,"max_checks":3,"policy":"adaptive"}
```

**Honest limit:** `/search` results are unverified candidates, and `/evidence-search` checks at most `max_checks` sampled intervals — an unanswered question is not proof that the action never happened.

## 2. Find a spoken topic (experimental)

**7. "Find the meeting where we discussed the budget."**

`POST /search`

```json
{"query":"we discussed the budget","path":"speech","limit":6}
```

**8. "Which recording mentions the broken doorbell?"**

`POST /search`

```json
{"query":"the doorbell is broken","path":"speech","limit":6}
```

**9. One meeting recording only.**

`POST /search`

```json
{"query":"we agreed to move the deadline","path":"speech","recording_ids":["RECORDING_UUID"],"limit":6}
```

**Honest limit:** speech results are transcript matches with playback, not visual checks — ASR text is an estimate that can mishear names and wording, and recordings with a nonzero audio origin are not offset-corrected yet.

## 3. Reference image plus text

Attach a picture (PNG, JPEG or WebP, at most 10 MiB decoded) as `image_base64`. The image requires the `visual` or `hybrid` path.

**10. "Did this person come to my door?"** — with a photo.

`POST /search`

```json
{"query":"this person at the front door","path":"hybrid","image_base64":"BASE64_IMAGE","limit":5}
```

**11. "Find this vehicle in the driveway."**

`POST /search`

```json
{"query":"this vehicle in the driveway","path":"visual","image_base64":"BASE64_IMAGE","limit":5}
```

**12. With source checks on the top candidates.**

`POST /evidence-search`

```json
{"query":"this vehicle pulls into the driveway","path":"hybrid","image_base64":"BASE64_IMAGE","limit":12,"max_checks":3}
```

**Honest limit:** the image steers retrieval only — the verifier never sees it, so image similarity is not proof of identity or action.

## 4. Today and this-month scopes

The browser selects these scopes from question words. The API takes explicit `start_date` and `end_date` values (YYYY-MM-DD, both inclusive). Replace the example dates with your own.

**13. "Who came to the door today?"**

`POST /search`

```json
{"query":"a person at the front door","path":"description","start_date":"2026-11-20","end_date":"2026-11-20","limit":12}
```

**14. "Any vehicle in the driveway this month?"**

`POST /search`

```json
{"query":"a vehicle in the driveway","path":"hybrid","start_date":"2026-11-01","end_date":"2026-11-30","limit":12}
```

**15. The scoped question, model-checked.**

`POST /evidence-search`

```json
{"query":"a person at the door","path":"description","start_date":"2026-11-20","end_date":"2026-11-20","limit":12,"max_checks":3}
```

**Honest limit:** a capture date is a calendar day, often derived from file modification time, which can be wrong for copied files — undated recordings are skipped and reported in coverage, not searched.

## 5. Count occurrences (experimental)

Counting uses the same visual source checks as verification, so it needs the configured vision service. The scan checks the recordings' registered intervals one by one, within a budget of `max_checks` (1–500).

**16. "How many visitors came to the door today?"**

`POST /count-events`

```json
{"query":"a person at the front door","recording_ids":["RECORDING_UUID"],"start_date":"2026-11-20","end_date":"2026-11-20","max_checks":60}
```

**17. "How many times did the dog cross the yard?"**

`POST /count-events`

```json
{"query":"a dog crosses the yard","recording_ids":["RECORDING_UUID"],"max_checks":120}
```

**18. The whole dated library, with one shared budget.** The response reports how many partitions were checked against the total.

`POST /count-events`

```json
{"query":"a person at the front door","start_date":"2026-11-14","end_date":"2026-11-20","max_checks":500}
```

**Honest limit:** the count is observed over checked partitions only — a stopped scan reports a partial count, and two distinct events less than half a second apart merge into one.

## 6. Ask about absence, honestly

No answer in this app proves that an event did not happen. These examples show how to read what was and was not checked.

**19. "Did anyone enter the shed last night?"** — a checked question with no match found. The response lists each check and where the scan stopped.

`POST /evidence-search`

```json
{"query":"a person enters the shed","path":"description","recording_ids":["RECORDING_UUID"],"start_date":"2026-11-19","end_date":"2026-11-20","limit":12,"max_checks":6,"policy":"ranked"}
```

**20. An empty result with no ready windows.** Read `coverage` first: an empty result list with no ready windows means the index is unavailable for that scope, not that the event was absent.

`POST /search`

```json
{"query":"a person in the shed","path":"visual","recording_ids":["RECORDING_UUID"],"limit":5}
```

**21. A partial count says so.** `"stop_reason":"budget_exhausted"` with `"complete":false` means the scan stopped early; compare `partitions.checked` with `partitions.total` before you use the count.

`POST /count-events`

```json
{"query":"a person at the front door","recording_ids":["RECORDING_UUID"],"max_checks":60}
```

**Honest limit:** coverage, source checks and counts describe what was sampled and checked — never the rest of the footage.

## Proof on record

Real browser runs for these capabilities are saved: [image queries](../evaluation/image-query-e2e-results.json), [calendar scoping](../evaluation/calendar-scoping-e2e-results.json), [speech search](../evaluation/speech-search-e2e-results.json) and [event counting](../evaluation/event-counting-e2e-results.json). They are engineering checks on small test footage, not benchmark scores.
