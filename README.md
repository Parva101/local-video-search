# Local Video Search

Search your own video archive. Point the app at a folder of recordings — CCTV exports, doorbell clips, meeting footage — or upload from the browser. It indexes them locally, then answers text or image questions with timestamped, model-checked intervals you can play and verify yourself.

## What it does

- **Import**: folder scans and streamed browser uploads; durable, resumable indexing jobs; source files stay read-only.
- **Three search paths**: visual embeddings (SigLIP2), generated descriptions (hosted Gemma/Qwen), and speech transcripts (local Whisper ASR or supplied SRT/VTT subtitles), with hybrid fusion and optional local reranking.
- **Reference-image questions**: attach a picture to any search.
- **Calendar scoping**: per-recording capture dates, today/this-week/this-month scopes, and date-filtered searches.
- **Occurrence counting**: budget-bounded scans that count verified events and honestly report partial coverage.
- **Evidence you can check**: every answer links to source footage at the cited time; saved traces; explicit "not proven absent" limits everywhere.
- **Sample questions**: a catalog of practical questions with the exact API JSON — see [docs/SAMPLE-QUESTIONS.md](docs/SAMPLE-QUESTIONS.md).

## Quick start

Requires Docker with Compose. Copy `.env.example` to `.env`, set `VIDEO_DIRECTORY` to an existing folder of videos, then:

```sh
docker compose up --build -d --wait
docker compose run --rm --no-deps worker python -m video_search.encoder download
```

Open http://localhost:8000, upload or import a video, index it, and ask a question. Model setup for descriptions, speech, and reranking is described below; no GPU is required.

**Honest scope**: a local, single-user service. Answers come from sampled frames and transcript estimates — they are evidence to check, not proof of absence or exact counts. Your API key stays on your server; media never leaves your disk except sampled frames sent to the vision service you configure.

## Research log — recent results

**Full test is complete:** six 100-epoch runs and all eight 3,720-query comparisons passed their coverage checks. Baseline mean R@1 at IoU 0.5 is **60.04%**; IoU-quality training reaches **58.80%**, so that change is rejected. The released reference reproduces **60.19%** at its native batch size. See [full results and limits](research/trained-head-results-2026-11-14.md) and [aggregate JSON](evaluation/trained-temporal-full-test-results.json). These are processed-author-release results, not a SOTA claim. The next reference is SDST; input preparation and runtime checks come before more training.

The selected experiments, evidence, current results and Sol procedure are in [the performance campaign](research/performance-campaign-2026-11-14.md). The first offline caption decoder uses no new model calls. On the previously exposed 69-query pilot, its train-selected setting reaches 43.48% R@1 at IoU 0.5 and 40.66% mean IoU, versus 42.03% and 35.89% for reranked retrieval. The recall gain is one query and its confidence interval includes zero. This is not a full-benchmark or SOTA result.

The new research path is separate from the app. `scripts/compare_temporal_decoders.py` selects a small grid with `develop`, then requires that freeze for `evaluate`; output files cannot overwrite old results. [Aggregate results](evaluation/caption-curve-pilot-results.json) contain no raw queries. The decoder estimates intervals from caption relevance; it does not prove absence, repeated-event counts or observed boundaries.

`scripts/sol/prepare-temporal.sbatch` prepares the pinned UniVTG release in a separate research directory. `scripts/sol/train-temporal.sbatch` runs a GPU smoke by default. Set `TEMPORAL_ACTION=train` only after the smoke passes to train baseline and IoU-quality foreground conditions for seeds 2018, 2019 and 2020. Each uses 100 epochs, a fixed train-video-disjoint validation split and resumable checkpoints. Use the verified course account with `sbatch --account=class_cse59889474fall2026`. Set `TEMPORAL_ROOT` to the research directory and route logs there. These jobs use isolated research packages, not new app dependencies.

`scripts/evaluate_temporal_head.py` is a separate full author-test driver for frozen checkpoints. It requires the pinned labels and checks source/config identities. The author metadata differs from canonical annotations, and the released checkpoint used the authors' selection procedure; report those limits. Training speed, adaptation gains and full-benchmark reproduction must come from completed runs.



A local video archive search project. Import recordings and search source intervals with visual embeddings, generated descriptions, or speech transcripts. Hosted Gemma or a configured Qwen service can inspect candidate source frames. Reference-image questions, calendar scoping and occurrence counting are supported; counts and speech are labelled experimental.



## Upload a video and ask questions



Set `VISION_PROVIDER=gemma` and `VOYAGER_API_KEY` in your private `.env`. The ASU endpoint defaults to `https://openai.rc.asu.edu/v1`; use an account with access to `gemma4-31b-it`. Keep `VIDEO_DIRECTORY` set to the same absolute source directory used by this database.



Run `docker compose up --build -d --wait`, then open [Local Video Search](http://localhost:8000). Download the description text encoder once if it is not in your model cache:



```sh

docker compose run --rm --no-deps worker python -m video_search.text_encoder download

```



Choose a video and select **Upload & index**. The server stores the completed upload, imports its timing, and queues Gemma description indexing. Progress and errors appear on the page. Work continues if you close or refresh the page. Select a ready video, enter a question, and inspect the model's observations and source timestamps. The page searches descriptions and checks up to three candidate intervals with the vision model. This does not prove that an event is absent from the rest of a recording.



Videos stay in the persistent Docker `uploads` volume. Sampled image frames are sent to ASU for model inference; the API key stays on the server. The initial upload limit is 2 GiB (`UPLOAD_MAX_BYTES`). Browser playback needs a supported source codec; MP4 with H.264 is a good test format. Speech search runs locally; occurrence counting is experimental.



The original source folder remains read-only. Uploaded source references use an internal `/__uploads/` marker and resolve to a separate read-only mount. Original library paths remain relative, so a source folder with that name still works. Only the API has a writable upload mount. Keep the database, model and upload volumes when restarting; `docker compose down -v` deletes them. Different providers have separate index specifications, so old Qwen results stay stored but are not mixed into Gemma searches.



The [saved acceptance check](evaluation/gemma-upload-e2e-results.json) records the real browser flow and its quality limits. The model found the cup action in the test clip; some negative explanations were weak or inconsistent. Check answers against the footage.



## Run



Install Docker with Docker Compose and start its Linux engine. No GPU or API key is needed for this CPU baseline. The first build downloads PyTorch, the application packages, FFmpeg, and PostgreSQL with pgvector. The separate model setup downloads about 1.54 GB to a persistent cache.



1. Copy `.env.example` to `.env`.

2. Set `VIDEO_DIRECTORY` to the absolute path of an existing folder. Use forward slashes on Windows, for example `D:/Videos`; on Linux/macOS, use a path such as `/home/your-name/Videos`. Paths with spaces are supported. Relative paths are rejected to prevent a moved checkout from reusing another folder's source references.

3. Run:



```sh

docker compose up --build -d --wait

```



Open [the API interface](http://localhost:8000/docs). The API binds to this computer only. The database has no published port. Directory imports use the configured source folder read-only. Browser uploads create a separate local copy in upload storage.



Submit `POST /imports` with:



```json

{"path": "."}

```



The path is relative to `VIDEO_DIRECTORY`. You can select a subfolder or one file, for example `{"path":"meetings/week-1.mp4"}`. Use forward slashes. The response lists persistent job IDs. The worker hashes and probes each file, then records overlapping logical windows. It does not encode a separate clip for every window.



Use `GET /jobs` or `GET /jobs/{id}` to check progress. A successful job returns `result.recording_id`. Use `GET /recordings/{id}`, `/recordings/{id}/windows`, and `/recordings/{id}/media` for metadata, time intervals, and the original media. The media endpoint supports byte ranges. Browser playback depends on the original codec; previews and transcoding come later.



For a command-line import:



```powershell

Invoke-RestMethod -Method Post -Uri http://localhost:8000/imports -ContentType application/json -Body '{"path":"."}'

Invoke-RestMethod http://localhost:8000/jobs

```



Or on Linux/macOS:



```sh

curl -X POST http://localhost:8000/imports -H 'Content-Type: application/json' -d '{"path":"."}'

curl http://localhost:8000/jobs

```



## Visual indexing and search



Install the pinned encoder once:



```sh

docker compose run --rm --no-deps worker python -m video_search.encoder download

docker compose run --rm --no-deps worker python -m video_search.encoder smoke

```



The encoder is [Google SigLIP2 base](https://huggingface.co/google/siglip2-base-patch16-224), revision `75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2`. Model files stay in the `models` volume. Requests load local files only. Missing model files cause a clear error; there is no automatic model download or provider switch.



After import succeeds, submit `POST /recordings/{recording_id}/visual-index`. This returns a job with `index_build_id`. Check `GET /visual-indexes/{index_build_id}` for its state and completed/total windows. Indexing is explicit; importing a file does not start model inference.



When the build is `ready`, use `POST /search`:



```json

{"query":"a person wearing a red shirt","limit":5}

```



Optional fields are `recording_ids` (a nonempty list), `start_seconds`, and `end_seconds`. Times are source-relative seconds and apply to each selected recording. Time filters select overlapping windows; they do not trim or regenerate the window embedding. Calendar/camera filters are not implemented yet.



Results include source and window IDs, sampled frame timestamps, cosine similarity, source availability, model specification, and a playback URL. They are **unverified visual candidates**. A high similarity score does not establish that an action happened. This still-image baseline cannot reliably distinguish actions with similar appearances or prove that an event is absent.



`coverage` reports indexed windows for the requested scope, plus a count and up to 100 details for incomplete builds. An empty result list with no ready windows means the index is unavailable, not that the event was absent. Changed or missing source files are marked in results and cannot be played as unchanged evidence.



The baseline samples three slots per window, at one-sixth, one-half, and five-sixths. It selects the first frame at or after each slot. If no later frame exists within that window, it uses the first frame inside the same window and records that selection. Empty windows fail explicitly. Every slot retains its actual presentation timestamp; repeated frames keep their separate sample records.



Frames are reduced to a maximum side of 512 pixels, then processed with the checkpoint's native image processor. L2-normalized frame vectors are averaged and normalized to one 768-dimensional window vector. Search uses the matching text encoder and exact pgvector cosine distance. Each build records the model revision, preprocessing, sampling, pooling, and runtime specification. Different specifications cannot mix during search.



CPU/float32 inference uses four threads with bounded frame batches. Each process loads one model on first use, so the first query includes loading time. The API and worker can each hold a model in RAM. GPU inference and model switching are later work. The query limit is 64 model tokens; longer text is rejected rather than silently cut.



Window checkpoints survive worker interruption and explicit retry. A build becomes searchable only after every registered window completes. Repeating the same index request reuses its job. A failed build stays visible; use the job retry endpoint after fixing the cause.



Startup upgrades earlier schemas to v5 in a transaction and keeps existing imports and indexes. Back up the database before upgrading; older application versions cannot use v5. The [recorded visual smoke result](evaluation/visual-smoke-results.json) is not a public benchmark score.



## Description search and source inspection



This path uses a separate vision service. For Qwen set `VISION_PROVIDER=qwen`; for hosted Gemma use the upload setup above. The initial model is Qwen/Qwen3.6-27B, pinned to revision `6a9e13bd6fc8f0983b9b99948120bc37f49c13e9`. Set `QWEN_BASE_URL` (including `/v1`) and `QWEN_API_KEY` in the ignored `.env`, then recreate API and worker containers. Docker Desktop can reach a host service at `http://host.docker.internal:18360/v1`. The service receives sampled images; select an endpoint you trust with your footage. Missing or failed endpoints produce explicit errors. Model redirects are rejected to keep keys and frames at the configured endpoint.



Install the separate text encoder once:



```sh

docker compose run --rm --no-deps worker python -m video_search.text_encoder download

```



This downloads pinned `sentence-transformers/all-MiniLM-L6-v2`, revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, to the same persistent model cache. It runs locally on the CPU. No paid API is required if you supply your own vision service.



Submit `POST /recordings/{recording_id}/description-index`, then check its job and `GET /description-indexes/{description_build_id}`. The worker sends eight ordered source frames per window and stores a summary, actions, objects, uncertainty, actual timestamps, and request trace. Completed windows survive retries. Only fully ready builds enter search.



Use `POST /search` with an explicit path:



```json

{"query":"a robot moves a cup under a coffee machine","path":"hybrid","limit":5}

```



Paths: `visual` (existing default), `description`, or `hybrid`. Description search combines exact 384-dimensional summary similarity and PostgreSQL full-text search over summary, actions, and objects. Hybrid search combines visual and description ranks. Both use reciprocal rank fusion with constant 60 and bounded candidate lists. Coverage is reported for each selected path. Stored description search does not need the vision service to remain online.



Inspect a returned source interval with `POST /verify`:



```json

{"recording_id":"RECORDING_UUID","query":"A robot moves a clear cup under the machine.","start_seconds":16,"end_seconds":22,"context_seconds":0}

```



Inspection accepts up to 30 seconds, with optional context of up to five seconds on each side (default two). It rechecks the source hash, samples eight frames from the expanded interval, and returns `match`, `no_match`, or `insufficient_evidence`. A match includes validated source-relative intervals. `GET /verifications/{id}` returns the saved result and trace.



Search results remain unverified candidates. A saved model check is not human proof. Eight frames can miss short actions, small details, or occluded objects. `no_match` applies to the supplied evidence; it does not prove absence throughout unsampled footage. This stage does not count all events or identify people.



Sol setup scripts are in `scripts/sol`. Preparation builds the immutable container on node-local temporary storage and keeps the completed image and checkpoint on scratch. Serving requests one 80 GB A100 for a 20-minute test and requires a private `server.env` containing `VLLM_API_KEY`. Specify your course account when submitting. Python user-site packages are disabled so home packages cannot replace container packages. The pinned vLLM 0.20 runtime uses xgrammar with compact JSON output; this prevents an observed whitespace loop in interval replies. The policy is part of each index specification. The server endpoint lasts only as long as its Slurm job; an SSH tunnel and matching client key are needed. These scripts are a runtime test, not an always-on hosted service.



The [real Qwen test](evaluation/qwen-runtime-results.json) passed on one 80 GB A100, with a total GPU peak of 71.835 GiB including caches. Three windows of a 22-second recording took 51.45 seconds to index. [Retrieval results](evaluation/qwen-coffee-smoke-results.json) were visual 0/2, description 1/2, hybrid 0/2; both source checks passed. These provisional labels and five successful requests do not establish general quality or throughput. The initial failures are retained separately. The test GPU and tunnel are stopped. Saved indexes and source-check records remain usable locally; new descriptions or source inspection require a live configured service.



## What this stage stores



- File hash, original path, size, and modification time.

- Video duration, stream time base, and source timestamp origin when present.

- Separate recording occurrences for identical content at different paths.

- Ten-second logical windows with two-second overlap, bounded to the source duration.

- Job state, attempts, lease ownership, structured errors, and result references.



Window offsets are seconds relative to the selected video stream. Add `source_start_seconds` to map them to its media presentation timeline. File modification time is used to detect changes; it is not a capture date. No camera date, timezone, transcript, or event count is inferred.



An import job's `succeeded` state means import succeeded. Recording metadata reports `search_index_status` as `not_built`, `partial`, `failed`, or `ready` from its visual and description builds. Inspect each build for path-specific coverage. This is processing status, not proof of event detection accuracy.



## Restart and failures



```sh

docker compose logs --tail 100 api worker

docker compose restart worker

docker compose down

docker compose up -d --wait

```



The database lives in a persistent Docker volume. Ordinary `down` keeps it. An interrupted import is reclaimed after its 60-second lease expires. The worker refreshes the lease while processing. After three abandoned attempts, the job fails visibly. An expired worker cannot commit over its replacement.



Import recovery restarts the current file; completed files keep their results. Visual and description index recovery skips completed windows. There is no byte-level hash checkpoint. Expected inference errors fail their job visibly; unexpected worker exits have a bounded container restart policy.



Corrupt files, missing sources, changed files, and probe errors produce failed jobs. They do not become empty or successful recordings. After fixing a temporary problem, explicitly retry a failed job with `POST /jobs/{id}/retry`. If the file changed, submit a new import instead. Repeating an unchanged import returns the same job.



Use one database per video root. The database records the configured directory identity. Changing `VIDEO_DIRECTORY` while keeping that database causes startup to fail, which protects old source references. To index another root, create a separate Compose project, for example with `docker compose -p another-library ...`; stop the first API before reusing port 8000. Renaming the root also needs a deliberate migration, which is not part of this stage.



In this workspace, `.env` points to the generated demo in the workspace `media` folder. For your own footage, run `docker compose down`, change `VIDEO_DIRECTORY` in `.env`, then use `docker compose -p my-videos up --build -d --wait`. This gives your footage a separate database and keeps the demo intact.



Do not change source files during import or playback. Playback detects size/mtime changes, but it does not rehash an entire video on each range request. The stored import hash is not a guarantee that a host-side replacement preserving both values will be detected. Keep originals stable.



Folder scans accept up to 10,000 supported files per request and reject links/junctions. Unsupported files in a folder are ignored. Supported extensions: MP4, MKV, MOV, AVI, WebM, M4V, MTS, M2TS, MPEG, MPG. Probing has a 120-second limit per subprocess. Containers that lack stream duration need a packet-timing scan. A source needing more than 100,000 windows fails explicitly. Long job lists expose the latest 1,000 items at most in this stage.



This is a local development service. The bundled database credentials are local defaults. Do not publish its ports or use it as a shared hosted service without access control.



## Operations

**Where the data lives.** Three Docker volumes hold all app state: `database` (PostgreSQL: recordings, jobs, embeddings and saved traces), `models` (the pinned encoder caches) and `uploads` (browser uploads). Your source folder stays outside Docker, mounted read-only. `docker compose down` keeps these volumes; `docker compose down -v` deletes them.

**Backup.** The database has no published port, so dump it inside the `db` container. A dump contains descriptions and traces of your footage; treat it as private data.

```sh
docker compose exec db pg_dump -U video -d video -f /tmp/video-backup.sql
docker compose cp db:/tmp/video-backup.sql ./video-backup.sql
```

**Restore.** Restore into a fresh database volume; this replaces the current database. Keep the same `VIDEO_DIRECTORY` in `.env`: the database records that directory identity, and startup fails on a mismatch by design.

```sh
docker compose down
docker volume rm local-video-search_database
docker compose up -d --wait db
docker compose cp ./video-backup.sql db:/tmp/video-backup.sql
docker compose exec db psql -U video -d video -f /tmp/video-backup.sql
docker compose up -d --wait
```

With a custom Compose project name (`docker compose -p`), prefix the volume name with that project. The `models` and `uploads` volumes need no dump: keep them, or download the pinned models again.

**Monitoring.** A Windows scheduled task, `VideoSearchSolMonitor`, polls every 10 minutes for long-running Sol research jobs via [scripts/monitor_sol_jobs.ps1](scripts/monitor_sol_jobs.ps1). It appends to `.codex-backups/sol-monitor/monitor.jsonl` and writes an `ALERT.md` with a log tail when a watched job needs attention. It does not watch the app containers; for those, use the log commands in [Restart and failures](#restart-and-failures).



## Tests



Run the tests in the supplied Linux environment:



```sh

docker compose run --build --rm test

docker compose stop test-db

```



Tests use a separate temporary PostgreSQL service. They do not erase the application database. Each integration test gets an isolated schema. Test media is generated with FFmpeg; there are no paid model calls or external video downloads.



To include the real encoder integration test after model setup:



```sh

docker compose run --build --rm -e RUN_MODEL_TESTS=1 test

```



Without that flag, real embedding-model cases are explicitly skipped. With it, missing model files fail the tests. Download both embedding models and the optional reranker first; the full model test run checks all three local models. Tests use a local HTTP fixture for the Qwen protocol; they do not start or prove real Qwen inference. They cover structured output, errors, retries, description checkpoints, hybrid search, saved source checks, and the earlier visual/import cases. The [visual smoke manifest](evaluation/visual-smoke.json) and [real-video smoke manifest](evaluation/qwen-coffee-smoke.json) describe engineering checks, not public benchmark scores.



Checks include source path limits, real corrupt media, non-zero timestamps, variable frame rates, duplicate content, concurrent claims, stale-worker commits, abrupt process death and recovery, failed-job retry, byte-range playback, and changed-source detection.



For host development, use Python 3.12 or later and install FFmpeg/ffprobe. Create a virtual environment, install the appropriate PyTorch build, then run `python -m pip install -c constraints.txt -e '.[test,vision]'`. Set `DATABASE_URL`, `MEDIA_ROOT`, and `MODEL_CACHE` before starting `uvicorn video_search.api:app`; run the worker with `python -m video_search.worker`. Integration tests require `TEST_DATABASE_URL` pointing to a separate database named `test`; without it, those tests are skipped explicitly. `constraints.txt` records the tested Linux/Python 3.12 package versions; container base and OS package updates can still change between builds.



## Next stage



Freeze a larger independently reviewed evaluation set and measure candidate recall, ranking, and costs before tuning or training. Add timestamped speech and test Decider Flash against explicit all-path search later. See [PLAN.md](PLAN.md) and the [full project draft](research/full-project-draft-plan.md). No benchmark gain is established.


## Bounded evidence search and optional reranking

`POST /evidence-search` searches candidates and checks their source frames on the server. The browser offers a ranked baseline, distinct-time selection with one denser follow-up check, and the same policy with optional local text reranking. These are experiments; they do not establish complete event coverage or reliable counts.

```json
{"query":"a person opens the drawer","path":"description","recording_ids":["RECORDING_UUID"],"limit":12,"max_checks":3,"policy":"adaptive","rerank":false}
```

The API accepts up to 24 candidates and 1–6 source checks. Each check uses eight sampled frames. Both policies stop at the first model-supported match. The adaptive policy defers overlapping intervals and can spend one check on a denser half of an uncertain interval. It keeps the other candidates. A source or model error stops the request; completed source-check IDs remain available in the error details.

The result contains the original retrieval, each check and its saved ID, inspected intervals, policy version, stop reason and work used. `calls` and `frames` count completed logical checks and input frame slots; repeated source images remain separate inputs. `http_attempts` and `sent_frame_slots` also include transient retries. Failed-attempt provider compute and token usage are unknown. Sparse samples never establish continuous coverage. Use **Save search trace** to download the result, including its query and model observations; treat that file as private footage data.

Optional reranking needs one explicit download of about 92 MB:

```sh
docker compose run --rm --no-deps worker python -m video_search.reranker download
```

Select **Local reranking and follow-up checks** in the browser, or add `"rerank":true` to description search. The server reranks up to 24 retrieved descriptions with the pinned `cross-encoder/ms-marco-MiniLM-L6-v2` checkpoint. It records the revision, text recipe, original retrieval rank and raw score. These scores are not probabilities. Reranking requires description search and at most 24 returned results. Missing weights and query/text pairs above 512 tokens produce explicit errors. Runtime requests use local files only.

The [reranker model card](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2) describes its training task and Apache 2.0 license. The default search API remains unchanged unless reranking is requested. Reranking does not rebuild an index. The ranked policy is available for comparisons with the same source-check cap. The current browser uses description search; visual/hybrid paths remain available through the API.

## Reference-image questions

Attach a picture to a question. In the browser, use **Attach a reference image**; the API accepts `image_base64` (PNG, JPEG or WebP, at most 10 MiB decoded) on `/search` and `/evidence-search`:

```json
{"query":"this counter and the machine","path":"hybrid","image_base64":"<base64 image>","limit":5}
```

The image is decoded, converted to RGB, shrunk to a maximum side of 512 pixels and embedded with the same pinned SigLIP2 image tower that built the window vectors. With an image, the visual query vector is the normalized sum of the unit text and image vectors (`unit-sum-text-image-l2-v1`); the response records this recipe and the `pil-rgb-max512-v1` preprocessing. Window frames are scaled by ffmpeg and query images by PIL; both are max-512 before native SigLIP2 preprocessing, and the recipes are recorded separately.

An image requires the `visual` or `hybrid` path and a ready visual index, so the library shows **Build visual index** for recordings that lack one. The browser switches to hybrid automatically and disables the reranked and event-extent methods, which need the description path. Source checks are unchanged: the model verifies the text query against sampled source frames.

Honest limits: the reference image steers retrieval only. The verifier never sees the image, and image similarity is not proof of identity or action. Checks remain bounded samples, not proof of absence. A [real end-to-end run](evaluation/image-query-e2e-results.json) attached a frame of a fresh upload and found the cup action at 17.88–20.14 seconds in one check.

## Calendar scoping

Questions like "today" or "this month" need capture dates. Each recording has an optional capture date: set it per recording in the library, or press **Use file dates** to derive dates from each file's stored modification time at your browser's time-zone offset. A user-set date is never overwritten.

The question form has a **Time scope** selector (All time, Today, Yesterday, Last 7 days, Last 30 days, Custom range). The words "today", "yesterday", "this/last week" and "this/last month" in a question select a scope automatically, and the applied dates are always shown with the answer. Scoped searches skip recordings without a capture date and report them in coverage. The API accepts `start_date` and `end_date` (YYYY-MM-DD) on `/search` and `/evidence-search`:

```json
{"query":"a person at the door","path":"description","start_date":"2026-11-01","end_date":"2026-11-30","limit":12}
```

Honest limits: a capture date is a calendar day, not an instant; a recording spanning midnight counts on its start date. File modification times approximate capture time and can be wrong for copied files. A [real end-to-end run](evaluation/calendar-scoping-e2e-results.json) proved both directions: a "today" question found the cup action, and a yesterday scope returned no candidates with an honest note.

## Speech and subtitle search

The third search path is spoken content. In the browser, press **Index speech (local ASR)** on a recording with audio; the pinned [Whisper base](https://huggingface.co/openai/whisper-base) checkpoint (`e37978b90ca9030d5170a5c07aadb050351a65bb`) runs locally on your CPU, with no cloud call. Then pick **Speech and subtitles** as the search path. The API equivalents are `POST /recordings/{id}/transcript-index` and:

```json
{"query":"the bread came out of the oven","path":"speech","limit":6}
```

Supplied subtitles are supported directly: `POST /recordings/{id}/subtitles` with `{"format":"srt","content":"..."}` (or `vtt`). Subtitles are parsed, validated against the recording duration, and published as a ready transcript build; importing the same file twice is idempotent. ASR transcripts and supplied subtitles are labelled by their source and share one pinned text embedding space, so both are searched together. Speech search combines dense MiniLM similarity and PostgreSQL full-text ranking with the same reciprocal-rank fusion as descriptions, and it honors the same recording, time and date scopes.

Speech results are transcript matches with playback, not visual verification. The page says so on every card: the source check path stays visual, and ASR text is an estimate that can mishear names and wording. Timestamps assume the audio stream starts at source time zero; recordings with a nonzero audio origin are not offset-corrected yet. A [real end-to-end run](evaluation/speech-search-e2e-results.json) transcribed 150 seconds of real footage audio in 76 wall-seconds and played the top match at 02:27. Speech indexing is explicit and restarts the whole recording on retry.

## Counting occurrences

Tick **Count all occurrences in the selected video (experimental)** and ask, for example, "how many times does the robot arm move a cup". The API equivalent is `POST /count-events`:

```json
{"query":"a person at the door","recording_ids":["RECORDING_UUID"],"max_checks":60}
```

The scan checks the recording's registered intervals one by one with the same visual source check, merges verified occurrences that overlap within half a second into one event, and returns the observed count, each event's span with playback, and how many intervals were checked. Uncertain intervals are counted and reported. A budget (`max_checks`, at most 500) stops long scans; a stopped scan returns a partial observed count, never a silent total. Date scopes work exactly as in search, and undated recordings are skipped and reported.

Honest limits: this is an observed count over checked partitions, not proof of the true number. Sparse frame sampling can miss brief actions; two distinct events less than half a second apart merge into one. A [real browser run](evaluation/event-counting-e2e-results.json) counted the cup action once (3 of 3 intervals) with its two adjacent-window reports merged.

## Repeatable temporal retrieval evaluation

The frozen [public QVHighlights example](evaluation/qvhighlights-public-example.json) is a development smoke test. It records the official target, pinned source revision, media hash and exact duration. Its original annotation rounds the duration to 150 seconds. It is one query and cannot establish a benchmark lead.

Create a JSON map from the manifest's external video ID to your imported recording UUID. After every selected index is ready, run:

```sh
python scripts/evaluate_retrieval.py --manifest evaluation/qvhighlights-public-example.json --recording-map recording-map.json --output baseline.json --qv-export baseline-predictions.jsonl
python scripts/evaluate_retrieval.py --manifest evaluation/qvhighlights-public-example.json --recording-map recording-map.json --rerank --output reranked.json --qv-export reranked-predictions.jsonl
```

Outputs preserve raw responses and the manifest hash. Existing output files are never overwritten. Failed requests, incomplete indexes and unavailable sources stop evaluation. Target intervals are used only for scoring; retrieval receives query text and the declared video scope. A saved-prediction run is also supported with `--predictions`. The tool reports diagnostic temporal Recall@K, target coverage and all-target coverage at IoU 0.3/0.5/0.7. Use the pinned author evaluator for official QVHighlights mAP. `--task corpus` tests the full mapped collection; supplied-video retrieval is the default.

See [checked research](research/chat-followup-evidence.md) for the paper evidence and the limits of current comparisons. Before a larger claim, freeze independent queries and media, reproduce a comparable baseline, include index construction and query costs, and run an untouched evaluation split. Boundary completeness, missed brief actions, speech and repeated-event coverage remain open work.


The [latest public engineering result](evaluation/evidence-search-public-smoke-results.json) records the fixed-pool retrieval comparison, source-check limits, official metric check and browser proof. Reranking improves this one example; final event boundaries still fail the tested complete-event overlap thresholds.


Gemma description generation and source verification have separate prompt versions. The description index uses `visible-evidence-gemma-json-v2`; compact source checks use `visible-evidence-gemma-verification-json-v2` in their saved run specification and trace. Verification accepts an evidence point with equal start/end times; the browser labels it at that time. It does not invent a duration. Changing verification instructions does not require rebuilding the description index. Strict output schemas and token caps remain active; a truncated reply remains an error.


## Event start and end estimates

Select **Event start and end with local reranking (experimental)** in the browser. The API equivalent is `"policy":"extent","rerank":true` on `/evidence-search`. The default policy is unchanged.

The v5 task labels each sampled frame as present, absent or unknown. The model returns four fields; code derives status from new frame labels only and records that rule in the trace. A positive reference frame alone cannot produce a new-frame match. Full-query support covers all supplied context, including that reference, and its scope is recorded in the trace. Negative neighbor evidence can bracket an edge but cannot upgrade a partial query to complete. Old replies are not repaired. The wire schema is selected from the input role: a seed has no reference and returns not applicable; a neighbor can return same event, different event or unknown. Unknown includes no visible new target. The schema excludes not applicable for a neighbor before decoding. A match seeds an event estimate. If an edge stays open, the controller can inspect nearby footage at the same frame density. Each neighbor check includes seven new frames and one exact reference frame. Positive extensions require the model to link the same event to that reference; unknown links do not extend it. An observed absent/present transition brackets an edge. The displayed timestamp is the bracket midpoint, not an exact observed transition.

Results keep raw source checks separate from `proposals`. A proposal records onset/offset brackets, query support, unresolved edges, source-check IDs and its scope limits. A single point has null span bounds. `complete` means both model-estimated edges are bracketed for one supported event; it does not certify continuous visibility or all events in the video. Gaps and repeated events remain limits. The saved trace includes both input slots and actual HTTP attempts, including retries.

For a controlled comparison, `"policy":"uniform_extent"` uses the same frame-labeling task with fixed neighbor order. `"spend_budget":true` continues into distinct seeds after a bounded event; it is an evaluation option for extent policies only. It does not repeat requests to fill an unused budget. Each API request allows at most six logical checks; the benchmark below fixes this at three checks and 24 frame slots.

## Private Charades-STA pilot

The pilot tests supplied-video temporal grounding. It selects 20 development videos (53 queries) and 25 held-out videos (69 queries) with a fixed source-ID hash rule. The downloader fetches only selected members of the official ZIP64 archive, verifies HTTP range/ETag, CRC, size and SHA-256, and records the pinned VSLNet annotation copy. Raw target bounds and author-preprocessed bounds are both retained. See [access and protocol evidence](research/next-benchmark-access.md).

Keep the destination private. The video license restricts redistribution and commercial use. Do not commit videos, queries, labels, generated descriptions, frame captures or per-query traces. The supplied ignored `.codex-backups/` directory is suitable for this local experiment. Review the recovered license before use.

Example from the project folder (PowerShell), with the app database running:

```powershell
$pilot = (Join-Path (Get-Location) '.codex-backups/charades-pilot')
New-Item -ItemType Directory -Force $pilot | Out-Null
docker compose run --rm --no-deps -v "${pilot}:/benchmark" worker python scripts/prepare_charades.py --output /benchmark
docker compose run --rm --no-deps -v "${pilot}:/benchmark" worker python scripts/run_charades.py --data /benchmark --phase index
docker compose run --rm --no-deps -v "${pilot}:/benchmark" worker python scripts/run_charades.py --data /benchmark --phase development --query-limit 3
docker compose run --rm --no-deps -v "${pilot}:/benchmark" worker python scripts/run_charades.py --data /benchmark --phase development
docker compose run --rm --no-deps -v "${pilot}:/benchmark" worker python scripts/run_charades.py --data /benchmark --phase freeze
docker compose run --rm --no-deps -v "${pilot}:/benchmark" worker python scripts/run_charades.py --data /benchmark --phase test
docker compose run --rm --no-deps -v "${pilot}:/benchmark" worker python scripts/run_charades.py --data /benchmark --phase report --report-split test
```

Use the same `/benchmark` mount on every phase. The runner isolates its PostgreSQL tables from the app library. A durable SQLite gateway reserves every external request attempt before sending it. Indexing, failed attempts and retries share one hard 1,500-attempt cap. The data root pins the run identity and work path; changing `--work` cannot reset the cap. Existing checkpoints are verified and never overwritten. A failed case stops the run and stays recorded; it is not removed from the score.

The point-aware evaluation has three conditions with the same reranked candidate pool and two-check/16-slot cap: fixed ranked verification, uniform extent inspection, and missing-edge extent inspection. Development uses all 53 queries with the main extent method at one check for reliability and behavior checks. It is not a paired development quality comparison. The earlier frozen three-check run stopped after 63 of 207 cases on a repeated point-only baseline reply. That run stays incomplete. The new run records the prior protocol hash and is exploratory after test-input exposure; it is not a pristine held-out test. All earlier attempts remain charged. Reports show actual work and matched-work comparisons. Raw and reranked retrieval are separate diagnostics. The evaluation phase requires a frozen full development grid and exact source/prompt/runtime hashes. It writes `context-localization.freeze.json` and separate source snapshots, preserving earlier `point-aware.freeze.json` and `test.freeze.json`. A valid clip-support claim with no supporting sample timestamp returns a logged localization abstention, with raw judgments preserved and no event span. Raw source evidence points remain in saved data. They are not interval hypotheses: remove them before assigning interval ranks, then keep the remaining nonzero spans in model/check order. A mixed reply uses its first nonzero interval at R@1. A point-only reply remains in the query denominator as an abstention with zero IoU. It cannot use a query limit. Aggregate reports include R@1 at IoU 0.3/0.5/0.7, mean IoU, boundary diagnostics, abstentions, latency, and video-group paired bootstrap intervals. R@5 is diagnostic, not an exact reproduction of legacy TALL NMS.

This small pilot cannot establish full-dataset SOTA or novelty. The hosted Gemma revision is unpinned; its fingerprint is checked but does not prove unchanged weights or absence of training-data overlap. Speech, exact counts, image references and Decider routing remain separate unbuilt stages.


For an existing point-aware parent run, `--phase reuse-context-cache` validates a narrow compatible interpretation fix before copying cached cases to the new protocol. It checks the complete model-source AST, request functions, prompts, schemas, other source hashes, runtime, scope, budgets, and saved database evidence. Every copied case must avoid the changed branch. Raw responses, timestamps, latency and measured work stay unchanged; parent protocol and case hashes are saved. Unfinished or failed cases run fresh. The old files remain intact. Reused model calls were already charged to the same durable ledger: costs across parent and child runs overlap and must not be added twice. A fresh installation does not need this migration phase.


## Measured exploratory pilot, 8 November 2026

The complete [aggregate result and audit](evaluation/charades-point-aware-pilot-results.json) covers 69 evaluation queries from 25 source videos, with three methods and 207 completed cases. All three source-check methods used exactly two checks and 16 frame slots per query. They share the same reranked candidate pool and hosted Gemma model. Figures below are percentages.

| Method | R@1, IoU 0.5 | R@1, IoU 0.7 | Mean IoU |
| --- | ---: | ---: | ---: |
| Raw candidate retrieval | 39.1 | 5.8 | 37.0 |
| Reranked candidate retrieval | 42.0 | 4.3 | 35.9 |
| Fixed ranked source verifier | 1.4 | 0.0 | 8.9 |
| Uniform event inspection | 30.4 | 10.1 | 26.6 |
| Missing-edge event inspection | 33.3 | 13.0 | 28.9 |

The new boundary method does not beat the stronger candidate-retrieval baseline at IoU 0.5 or mean IoU. It improves stricter IoU 0.7 localization on this pilot, while abstaining on 37.7% of queries. Its IoU 0.5 gain over uniform inspection is only 2 of 69 queries: +2.90 percentage points, with a video-group bootstrap 95% interval of [0, 7.69]. Mean IoU improves by 2.24 points over uniform, with interval [0.64, 4.29]. These are exploratory observations, not a general accuracy or SOTA result.

Event completeness remains unreliable. Of 11 top-one proposals labelled model-complete by their sampled brackets, 6 have IoU below 0.5. This is a localization-error proxy, not human-labelled semantic false-completeness. Do not treat `complete` as proof of a whole event, continuous coverage, or a count of every event. The UI calls these model estimates and keeps them separate from raw source checks.

The first frozen three-check run stopped after 63 of 207 cases on a repeated point-only baseline reply. The next point-aware run stopped after 87 cases on an overstrict context/localization assumption. Those runs remain incomplete and unchanged. The final protocol records both parent hashes and is explicitly exploratory after test-input exposure. A source/AST/database audit reused all 53 development cases and 87 evaluation cases whose raw results cannot change under the narrow interpretation fix. The remaining 120 cases ran fresh. No failed response was repaired into an answer. All 207 final cases completed without errors, and no query was dropped.

The durable ledger has 1,460 unique external attempts under its 1,500 cap: 186 for indexing; 4 for public controls and the exact-source probe; 53 for development evidence; 414 for final evaluation evidence; and 803 for earlier work not reused in the final result. Final evaluation evidence includes 174 already charged cached attempts and 240 fresh attempts. Parent/child protocol costs overlap and must not be added twice. Latency describes original successful source-check/controller invocations, excluding shared retrieval and indexing; cached cases keep their original measured time.

Validation: 377 model-enabled regression tests passed, with two existing warnings. Real-model controls, browser empty input/double submit, trace download, timestamp playback, refresh and mobile checks passed. Labelled network fixtures checked point display and localization-abstention notices without model calls or database writes. All 281 original description rows match the pre-benchmark backup; the 205-window ready index and earlier 48-window build remain intact.

The media are short indoor clips (16.7 to 42.8 seconds in evaluation). This does not validate long CCTV, absent-event queries, counts, speech, identity search, or multiple-video corpus retrieval. The hosted model revision is unpinned. Novelty and SOTA remain unproved. The stronger retrieval baseline and the high boundary error rate point to temporal perception/localization and coverage as the next quality bottlenecks. Keep the new event method optional while collecting independent evidence.
