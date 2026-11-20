# Full project research and draft plan

Status: user mandate, 19 November 2026 — build the complete product autonomously (no per-step approval) until the full system works end to end and is tested with real uploads and questions. SDST is skipped; both its runtime jobs failed on libGL (nncore reintroduced the GUI OpenCV wheel; see DECISIONS.md). The research goal is an honest best-in-class result for the local pipeline on an accessible benchmark. App state: 518-test model-enabled regression green; original indexes and the 1,460-attempt ledger intact. See the master plan below; history follows it.

## Master plan — 19 November 2026

Goal: a downloadable local system. Point it at a folder (or upload) of CCTV/doorbell-style recordings; index visual and description evidence; ask text or image questions; get timestamped, model-verified intervals with playback; ask count questions over a day or a month. Then prove the system is best in class for its comparison class, honestly.

| Stage | Deliverable | Proof |
| --- | --- | --- |
| 1. Reference-image queries | /search and /evidence-search accept an image with text; same SigLIP2 embedding space as window vectors; browser image control | Model-enabled API tests with a real frame image; browser image query on demo footage; no schema change expected |
| 2. Capture dates and calendar scoping | Recording capture dates (explicit or mtime-labelled), date filters on search, deterministic today/this-week/this-month mappings | Additive migration keeps all data; date-filter tests; browser quick filters |
| 3. Speech and subtitle search | Pinned local Whisper through the existing transformers runtime; durable transcript jobs and segments; speech search path; mixed queries | Additive migration; exact-phrase retrieval and playback tests; missing/silent-audio cases |
| 4. Scoped event counting | Explicit scope and event definition; partition verification; event records; count from records only; coverage and uncertain intervals reported | Count precision/recall on generated multi-event fixtures; duplicate-boundary and gap cases |
| 5. Corpus UX and release polish | Folder-wide search default, coverage in the UI, result export; fresh-machine Compose instructions | Fresh-project Compose run; restart/restore test; docs review |
| 6. Real end-to-end campaign | Real uploads of long mixed footage; every acceptance query type; negative queries | Saved traces; browser checks; honest limits recorded |
| 7. Fresh benchmark evaluation | Untouched Charades-STA selection plus negative/long-video cases; frozen protocol; one-shot evaluation | Aggregate report with costs and confidence intervals; comparison class stated |

Acceptance queries (full-project draft plus the user's examples): find an action; find a spoken topic; combine speech and appearance; find all occurrences; count events with attributes (visitors today, packages this month); reference image plus text; absent-event questions answered honestly.

Rules kept under the mandate: targeted tests first, model-enabled regression, browser proof, honest limits, DECISIONS/LESSONS updated, no random trial and error.

### Stage 1 complete — reference-image queries, 19 November 2026

Implemented and proved end to end. `/search` and `/evidence-search` accept `image_base64`; the image is PIL-prepared (`pil-rgb-max512-v1`), embedded with the pinned SigLIP2 image tower, and combined with the text vector (`unit-sum-text-image-l2-v1`). Images are rejected on the description path and with reranking. The browser gains the attach control, auto-switches to hybrid, disables incompatible policies, and offers an explicit **Build visual index** control (indexing stays explicit, matching the import design).

Proof: 3 focused tests passed; full model-enabled regression **521 passed, 2 private-checkout skips, 2 existing warnings**. Real browser flow: fresh 22-second upload → hosted Gemma description index → visual index → frame image plus "A robot moves a clear cup under the machine." → one source check, **match at 17.88–20.14 s** → playback seek 17.88 s readyState 4, zero console errors. Evidence: `evaluation/image-query-e2e-results.json`.

Known limits: the image steers retrieval only; verification checks the text against sampled frames and never sees the image; similarity is not proof. Static assets now carry `?v=0.2` cache-busting after a stale-`app.js` browser-cache trap during the check. Next: stage 2, capture dates and calendar scoping.

### Stage 2 complete — calendar scoping, 19 November 2026

Schema v5 (additive capture-date columns, live upgrade proved). Per-recording dates plus a bulk file-dates action at the browser's time-zone offset; user dates never overwritten. `/search` and `/evidence-search` take `start_date`/`end_date`; coverage reports undated recordings instead of hiding them. Browser scope selector with deterministic, visible keyword detection.

Proof: focused 8 passed; full model-enabled regression **524 passed, 2 private-checkout skips, 2 existing warnings**; real DB upgraded with all data intact; browser proof both ways — a "today" question matched at 17.88–20.14 s, a yesterday scope honestly returned no candidates. Evidence: `evaluation/calendar-scoping-e2e-results.json`. Next: stage 3, local speech and subtitle search.

### Stage 3 complete — speech and subtitle search, 19 November 2026

Schema v6 (transcript builds/segments; live upgrade proved). A pinned local Whisper base transcribes recordings with audio through the existing durable job system; supplied SRT/VTT subtitles import directly and both sources share the pinned MiniLM embedding space. `/search` gains the `speech` path (dense + lexical RRF over segments, same recording/time/date scopes); speech results are honest transcript matches with playback and no visual verification. The browser gains an **Index speech** control, a speech search path, and transcript cards.

Proof: speech suite 5 passed including a real ASR test on generated speech; full model-enabled regression **529 passed, 2 private-checkout skips, 2 existing warnings**. Real browser run: the 150-second pizza clip transcribed locally in 76 wall-seconds (6 segments), and "the bread came out of the oven at the market" returned the real line "It literally just came out of the oven" at 02:27.1–02:29.0 with playback seek to 147.08 s; zero console errors. Evidence: `evaluation/speech-search-e2e-results.json`.

Known limits: audio-origin assumption (stream start = zero), ASR text is an estimate, transcript jobs restart whole recordings on retry, no speech verification.

### Stage 4 complete — scoped occurrence counting, 19 November 2026

`POST /count-events` walks a recording's registered windows with the existing visual source check, merges verified occurrences that overlap within half a second, and returns observed counts with per-event spans, verification IDs, checked/uncertain/undated partition reporting, and a `max_checks` budget (1-500). Partial scans return partial observed counts, never silent totals. The browser gains a **Count all occurrences** mode.

Proof: count suite 6 passed ungated against the labelled local VLM fixture (validation, adjacent-window merge, separate events, partial budget, uncertain partitions, date-scope skip); full model-enabled regression **535 passed, 2 private-checkout skips, 2 existing warnings**. Real browser run on the coffee upload: "the robot arm moves a cup" → **1 occurrence, 3 of 3 intervals checked**, the two adjacent-window reports merged into one event spanning 00:16.4–00:20.1, zero console errors. Evidence: `evaluation/event-counting-e2e-results.json`.

Known limits: observed counts only; half-second merge rule; sparse sampling can miss brief actions; long scans are budget-bounded. Next: stage 5, corpus UX and release polish, then the GitHub release.

### Stage 5 complete and released — 19 November 2026

Corpus UX: **Search every indexed video** toggle posts searches without a recording scope; the gate accepts any ready index. Asset version bumped to v0.6. README restructured with a product intro, feature list and quick start; MIT LICENSE added; `.gitignore` re-checked (no `.env`, media or `.codex-backups` staged).

Released: repository initialized on `main`, committed, and pushed to **https://github.com/Parva101/local-video-search** (public, MIT). Remote verified in sync at `b328011`.

Proof: full model-enabled regression **535 passed, 2 private-checkout skips, 2 existing warnings**; live database upgraded v4→v5→v6 with all data intact; browser checks for image queries, keyword-detected "today" scope, yesterday exclusion, real Whisper ASR search with playback, real occurrence counting with merge, and all-videos search — all with zero console errors; evidence in `evaluation/`.

Remaining honest gaps for later sessions: a true fresh-machine Compose run (second project, clean volumes) is recommended before public announcements — every test already proves fresh schema creation, and the live DB proves in-place upgrades, but the end-to-end fresh-docker flow has not been run on another machine; the ASR audio-origin assumption; supervised-benchmark claims (stage 7) remain future work under the 19 November mandate's honest-comparison framing.

### Fine-tuned system model campaign — started 20 November 2026

Base pinned: `Qwen/Qwen3-VL-4B-Instruct` @ `ebb281ec70b05090aa6165b016eac8ec08e71b17` (Apache-2.0, 4.4B, ~8.9 GB). Why: LoRA-trainable on one A100, small enough to serve later on a 16 GB laptop GPU, and it plugs into the app's existing OpenAI-compatible Qwen client as a pinned revision with zero application changes. It replaces the unpinned hosted model dependency if it passes the gate.

Supervision exported from the live database: 284 description rows and 32 verification rows with full samples and payloads (`​.codex-backups/finetune-data/`, no-BOM JSONL, hashes verified on both machines). Charades-STA grounded positives and same-video hard negatives join at dataset-build time from the licensed pilot.

Steps, in order, for the next session:
1. Prep job **2068865** (CPU) downloads and hashes the checkpoint. Check: `sacct -j 2068865 --format=JobID,State,ExitCode,Elapsed`. Log: `/scratch/psheta12/video-search-finetune-20261120/logs/prepare-finetune-2068865.log`. Manifest: `base-model-manifest.json`.
2. Dataset builder: extract frames at recorded sample times from the licensed pilot and demo media; tasks are the description JSON schema (distillation) and the verification schema (status + intervals), with in-interval positives and same-video out-of-interval hard negatives. Keep sources distinct and hashed.
3. LoRA training script with the campaign's gates: short smoke before any long run, resumable checkpoints, isolated research packages, no app dependency changes.
4. One A100 job within the 960-minute class QoS; report the job ID and leave it running.
5. Honest acceptance gate: match or beat hosted Gemma on the frozen coffee fixtures and pilot controls at equal tasks, with pinned weights. Keep the hosted path on failure and record the negative result. No SOTA wording; the claim target is best-in-class among local pinned systems for this pipeline.

### Campaign progress — 20 November 2026

Prep job 2068865 COMPLETED in 38 s: all 12 pinned checkpoint files downloaded and hashed (base-model-manifest.json verified; shards 4.97 + 3.91 GB). Media assembled locally: the four uploaded source videos copied from the Docker volume (225 MB) plus the workspace coffee demo; 284 description rows and 32 verification rows reference them. Dataset builder (`scripts/build_finetune_dataset.py`, committed) extracts the recorded sample frames and emits chat samples with the app's Qwen-serving prompt text; coffee rows plus every tenth window are held out for eval. LoRA trainer and Slurm job committed (`scripts/sol/finetune_vlm.py`, `finetune-vlm.sbatch`): isolated peft/trl installs, smoke-first (20 steps), adapters saved per run.

Next, in order: (1) dataset build completes locally (frame extraction running); (2) scp `dataset/` to `$FINETUNE_ROOT` on Sol; (3) submit the smoke job (`FINETUNE_MODE=smoke`, one A100, 2 h wall), verify its log, leave any long run for the user to check; (4) after smoke passes, submit the full run (`FINETUNE_MODE=train`, 8 h wall); (5) eval the adapter on the held-out coffee fixtures against the hosted Gemma records — the acceptance gate.

### Dataset built and smoke submitted — 20 November 2026

Dataset complete locally in 280 s: **258 train / 58 eval** chat samples, 316 frame groups (2,528 JPEGs at the recorded sample times), coffee fixtures plus every tenth window held out. Transferred to Sol as one 78 MB tar (untarred and hash-verified: train/eval/manifest SHA-256 match; frame count 2,528 confirmed). Trainer scripts hash-verified on both machines. **Smoke job 2073664** submitted (one A100, 1 h wall, `FINETUNE_MODE=smoke`): installs pinned isolated peft/trl/accelerate/datasets, loads the verified base, attaches LoRA, runs 20 steps on a 64-sample slice, and writes `runs/finetune-v1/smoke-gate.json`. The smoke exists to catch package-version incompatibilities explicitly before any long run; under the two-failure rule, a failed smoke stops for re-planning, not silent retry. Check: `sacct -j 2073664 --format=JobID,State,ExitCode,Elapsed`; log: `logs/finetune-smoke-2073664.log`. If the gate passes, submit the full run with `FINETUNE_MODE=train` and an 8-hour wall, then run the acceptance eval.

### First smoke failed; re-planned and resubmitted — 20 November 2026

Smoke 2073664 FAILED 1:0 after 10:15 — the gate caught a real contamination: `pip install --target` pulled its own torch into the target directory, and PYTHONPATH shadowing broke the container's compiled torchvision ops (`operator torchvision::nms does not exist` → transformers could not import `PreTrainedModel`). The poisoned `$ROOT/python` target was removed.

Re-plan (second and final attempt under the two-failure rule): the sbatch now creates a **venv with `--system-site-packages` inside the container**, so the container's torch 2.11.0+cu129 and transformers 5.6.2 satisfy the requirements, and `training-constraints.txt` pins both so an incompatible peft/trl fails at install time instead of shadowing compiled packages. The trainer also switched to the documented `AutoModelForMultimodalLM` class. Fixed scripts committed (`0bec695`), hash-verified on both machines, and the re-planned smoke is submitted as **job 2079044** (one A100, 1 h wall). Check: `sacct -j 2079044`; log: `logs/finetune-smoke-2079044.log`; pass marker: `runs/finetune-v1/smoke-gate.json`. If this attempt fails, stop and re-plan the training environment rather than resubmitting.

### Second smoke failed on a new cause; re-planned fix submitted — 20 November 2026

Smoke 2079044 FAILED 1:0 after 4:08, and the monitor caught it automatically. The log shows the venv re-plan worked: torch 2.11.0+cu129, transformers 5.6.2, peft 0.22.0, trl 1.18.2 with CUDA all loaded; the base checkpoint loaded (713 weights) and LoRA attached (**40,271,872 trainable params, 0.9%**). The single failure: trl 1.18's SFTTrainer requires an HF `Dataset`, and the trainer passed plain lists (`TypeError: train_dataset must be a Dataset or IterableDataset, got list`).

Honest two-failure reading: the two smoke failures have different, precisely diagnosed causes — the first was environment contamination, the second a container type. This is a designed re-plan for a newly identified cause, not a blind third retry: the fix converts the loaded rows with `datasets.Dataset.from_list` (datasets 5.2.0 is already in the venv), committed as `7b4f48c` and hash-verified on both machines. **Smoke attempt 3: job 2080864** (one A100, 1 h wall). The monitor watch list now tracks 2080864; the alert for 2079044 clears on the next healthy poll. Check: `sacct -j 2080864`; log: `logs/finetune-smoke-2080864.log`; pass marker: `runs/finetune-v1/smoke-gate.json`. If this attempt fails on a further cause, stop and re-plan the training stack itself (for example a purpose-built training image) instead of iterating on the same one.

### Third failure bit the rule; training stack re-planned — 20 November 2026

Smoke 2080864 FAILED 1:0 after 1:50 on a third distinct cause: `datasets.Dataset.from_list` crashed inside Arrow schema inference over the heterogeneous chat content parts (image parts carry an `image` key, text parts a `text` key; Arrow needs uniform structs). Per the rule recorded in PLAN, iteration on the trl/datasets integration stops here.

Re-planned stack, committed `c9c401c` and hash-verified on both machines: the trainer is now a **plain PyTorch loop** — peft LoRA (proven: 40.3M trainable params), a collator we control, prompt-masked labels with right padding, OneCycleLR, gradient clipping, epoch checkpoints — with **no trl and no datasets anywhere in the path**. The whole integration-failure class is removed rather than patched a fourth time. Smoke limit raised to 192 samples so the 20-step gate is reachable in one epoch.

### Fourth failure: my own path bug; ground-up audit and local pre-flight — 20 November 2026

Smoke 2093596 FAILED 1:0 after 2:48 on a fourth distinct cause, this one mine: the dataset was built on Windows, so image paths in the JSONL carried backslashes, and the loader also joined the `frames/` prefix twice (`dataset/frames/frames\00009\00.jpg`). Per the escalation rule, this triggered the ground-up audit rather than another patch-and-pray:

- Source fixed: the builder now emits posix paths (`as_posix()`).
- Loader made platform-proof: any separator is normalized, the frames prefix stripped, paths resolved against the dataset root, and the run **refuses to start if any image does not resolve**.
- File-handle pressure fixed too: images open lazily per batch and close after the processor call.
- **Local pre-flight added**: the exact `load_rows` code ran against the local dataset copy before submission — all 258 train + 58 eval rows load and every path resolves. Data-path issues can no longer reach Sol; if anything is off, the job fails in seconds on the CPU, before the GPU is touched.

Committed `7c2815f`, hash-verified on both machines. ### Attempt 5 failed at 08:59; Sol SSH outage blocks diagnosis — 20 November 2026

Smoke 2094734 FAILED 1:0 after 2:34 (recorded by the monitor at 08:59). Diagnosis is blocked: Sol's SSH endpoint stopped answering (banner-exchange timeouts from both the monitor's scheduled polls and direct attempts), so the log tail on scratch is unreachable until ASU recovers. The failure after a passing local path pre-flight points at the next untested stage — batch construction or the first forward pass.

A real monitor bug was found and fixed (`8c54568`): the old script cleared ALERT.md whenever a poll failed, which silently erased the 08:59 failure alert during the outage. Failed polls now preserve any existing alert, and three consecutive failures announce monitor blindness. The first successful poll after recovery re-raises the attempt-5 alert with its log tail, because 2094734 stays in the watch list.

Next, in order: when Sol answers, fetch `logs/finetune-smoke-2094734.log`, diagnose the fifth cause, and apply the escalation rule honestly — a fifth distinct cause in my own loop means the smoke is still doing its job, but the campaign pauses for a written decision on whether the plain-loop approach needs a different base plan rather than another fix.

### Fifth cause diagnosed; probe-verified fix; smoke attempt 6 — 20 November 2026

The fifth cause: my batch-key whitelist dropped `mm_token_type_ids`, which Qwen3-VL's multimodal RoPE requires. Written decision per the escalation rule: the plain-loop plan stands; the flaw was guessing processor output keys, so the trainer now passes the processor's full tensor contract through, and a new `--batch-probe` mode builds one batch on CPU and records the exact keys and shapes before any GPU is requested.

**Batch probe job 2103006 COMPLETED 0:0 in 1:06** on the exact container versions: `input_ids` [2, 2509], `attention_mask` [2, 2509], `mm_token_type_ids` [2, 2509], `pixel_values` [9216, 1536] (16 images of 8 per sample), `image_grid_thw` [16, 3], and masked `labels` [2, 2509]. The interface is proven with evidence, not assumption. Committed `39b8b8c`; the pre-flight ladder now runs: local path check → CPU batch probe → GPU smoke.

**Smoke attempt 6: job 2107653** (one A100, 1 h wall), tracked in the watch list. Check: `sacct -j 2107653`; log: `logs/finetune-smoke-2107653.log`; pass marker: `runs/finetune-v1/smoke-gate.json`. The probe's passing shapes mean the remaining unknown is only the forward/backward/optimizer path itself.

### Heartbeat protocol — 20 November 2026 (user requirement)

The agent cannot self-wake; a session turn needs one message. So the user's role is reduced to a single-word heartbeat, and any session receiving it executes this playbook in order without asking anything:

1. Read `.codex-backups/sol-monitor/ALERT.md` and the tail of `monitor.jsonl`.
2. If smoke 2080864 (or its successor) is **running or queued**: report the state; nothing else to do.
3. If it **passed** (`runs/finetune-v1/smoke-gate.json` exists): verify the gate, then submit the full run — `cd /scratch/psheta12/video-search-finetune-20261120 && FINETUNE_ROOT=$PWD FINETUNE_MODE=train sbatch --account=class_cse59889474fall2026 --time=08:00:00 project/scripts/sol/finetune-vlm.sbatch` — add the new job to `watch.json`, report job ID, log path and check command, and leave it running.
4. If it **failed**: diagnose from the alert's log tail; a third distinct cause means stop and re-plan the training stack (purpose-built image) instead of resubmitting.
5. When the full run completes: fetch the adapter hashes, run the acceptance eval (held-out coffee fixtures and pilot controls against the hosted records), record the verdict honestly in PLAN/DECISIONS, and only on a pass wire it into the app's Qwen client as a pinned revision.

### Automated Sol monitoring — 20 November 2026 (user requirement)


Long jobs are never left unwatched. `scripts/monitor_sol_jobs.ps1` (committed) polls the jobs in `.codex-backups/sol-monitor/watch.json` and is registered as the Windows scheduled task **VideoSearchSolMonitor** (every 10 minutes, 30-day repetition). Each poll appends to `monitor.jsonl`; any watched job reaching a state needing attention (FAILED, COMPLETED, TIMEOUT, CANCELLED, OUT_OF_MEMORY, NODE_FAIL) writes `ALERT.md` with the job's log tail and clears itself when all watched jobs are healthy. Rule recorded in AGENTS.md item 7 and RULES.md: any new session reads `ALERT.md` first, diagnoses from the tail, records the fix in PLAN.md, and resubmits only under the two-failure rule. New long jobs get added to `watch.json`. The monitor proved itself on the night of 19-20 November: it caught smoke failure 2079044 automatically, with the log tail ready for diagnosis.

## Current request: upload a video, index it, ask questions

### Reported failure: long-video index stops at48/205

Status: fix approved by "do it". Implement and test the explicit Gemma prompt, then test the failed interval before deploying. Private evidence is in .codex-backups/index-failure-inspection and .codex-backups/gemma-prompt-fix; do not publish the user's video descriptions or frames. Keep the old failed build unchanged.

Evidence: upload/import succeeded. Description indexing failed at384–394seconds. Gemma returned HTTP200 with finish_reason=length and1024 output tokens. Its summary is exactly600characters, followed by1276 consecutive whitespace characters. The client correctly rejects the incomplete JSON. A local HTTP replay through the real client reproduces invalid_vlm_response. Pending-window lookup starts at384seconds;48 completed windows remain saved,157 are unfinished.

Hypotheses checked: a constrained-decoding whitespace loop is supported by the saved reply; a simple output-budget shortage does not explain the whitespace run; local schema/transport errors do not explain the provider's length termination. One standalone request tested vLLM's structured_outputs disable_any_whitespace option with the same interval, schema, prompt and output budget. It also returned length and failed validation. HTTP200 does not prove the gateway applied that option. Stop this route after the original failure and failed compact trial; do not blindly raise tokens or retry the whole job.

Approved re-plan:

1. Give Gemma explicit JSON field names, a compact example and shorter target text lengths in the description prompt. Keep the current strict schema and token bound. Proof: captured failure remains rejected; protocol tests check the new prompt and unchanged validation.
2. Test the failed interval and nearby intervals before production use. Proof: finish_reason=stop, all required fields, bounded strings and no whitespace run. If two trials fail, stop and revise; do not repair responses or skip windows.
3. If proved, version the Gemma prompt/build specification and create a separate full index for this recording. Keep the failed build and its48 windows unchanged; copying them would mix generation policies. Proof: complete205-window build, saved request traces, working browser query and source playback. Run relevant regression tests and show the result in the UI.

Open: whether the shorter explicit prompt fixes this hosted model. A new versioned build must repeat the first48 windows; no mixed-policy reuse is proposed. Stop after two failed trials on a step and record the revised plan before more calls.

Status: approved by "build"; implemented and running at http://localhost:8000. The browser upload, durable indexing, queries and timestamp playback passed live checks with hosted Gemma. Original recordings and indexes remain stored. [Acceptance evidence](evaluation/gemma-upload-e2e-results.json).

1. Connect hosted Gemma to the existing client, settings, API and worker. Keep model/build identity explicit and the API key on the server. Proof: protocol/config tests, separate Gemma builds, existing regression checks.
2. Accept a streamed browser upload in a dedicated persistent area. Preserve the read-only source library; validate names, file type and size; publish only complete uploads. Queue import and description indexing durably so they do not depend on the browser staying open. Proof: valid/corrupt media, interrupted/oversized upload, duplicate submit, restart and failed-job checks. Use the existing job system; no new broker.
3. Add one local browser page: upload, progress, recording selection, text query, answer and timestamped playback. Search Gemma descriptions, then use the existing source check on the top candidate intervals. Show model observations and evidence status; do not present candidates as verified events or claim full-video absence. Proof: real upload-to-answer run with the public coffee clip, a negative query and saved traces.
4. Start Docker services and verify the page at localhost:8000. Proof: empty input, double submit, refresh, errors, playback and index persistence; run the existing regression suite. Update setup instructions and decisions. No new frontend framework or dependency unless inspection proves it necessary.

Initial scope: visible actions and objects in one selected video per question. Speech search, reliable event counts and archive-wide answer synthesis remain separate work. Only sampled frames go to the configured ASU model; the uploaded video stays in local storage. Explain this on the upload page.

Current choices: 2 GiB streamed upload limit, dedicated persistent uploads volume, original library read-only, server-persisted follow-on description job, three candidate intervals per query. Open: larger quality evaluation, speech search and reliable counts. Caption and explanation errors remain a quality risk.

Build checks: Gemma/config focused tests passed (34). Upload checks stopped after two failed attempts: first used pytest's reserved request parameter and ran before static files existed; second passed 29 tests but exposed a disconnect mislabeled as a storage failure and a simulated downgrade fixture retaining v4 columns. Re-plan: narrow filesystem error handling, correct the downgrade fixtures, wait for UI assets, then rerun focused checks. Preserve raw evidence in .codex-backups.

Re-plan proof: 47 focused backend tests passed, then 19 upload cases passed. First full suite passed 127 tests with two existing SentencePiece warnings. First service start failed because Docker cannot create a nested volume mountpoint inside a read-only bind mount. Fix source resolution for the reserved upload prefix to use a separate read-only upload mount; the original folder stays unchanged. Review also reproduced an HTTP redirect key leak with dummy credentials; reject all model redirects. Focused client/config checks passed after that fix. Rebuild and rerun before live checks.

Final review found that a relative upload prefix could shadow an existing library folder. Replaced it with the internal absolute /__uploads/ marker, which original relative library paths cannot produce. Collision and escape tests pass; reviewer confirmed the fix. Corrected only the newly created demo record/jobs to that marker, with database backup. All three original records retain their IDs, paths, hashes, sizes and modification times.

Final checks: `docker compose run --rm -e RUN_MODEL_TESTS=1 test` -> **136 passed in 44.57 seconds**, exit0; two existing SentencePiece warnings. Browser checks passed: real upload, double submit, refresh during indexing, three indexed windows, blank/whitespace query, positive/negative queries, timestamp seek at17.88 seconds with readyState4, 390px layout without horizontal overflow, and zero final console errors. Nine source checks and three descriptions are saved with request/frame traces. Restart preserved the ready index and source range playback. Model redirects fail closed. Test database stopped; API, worker and application database remain running.

Limits: the cup query retrieves a useful match; red-shirt checks return no_match but literal insufficient_evidence explanations. Keep that conflict visible. This is one22-second recording, not proof of CCTV accuracy or full-video absence. A multi-gigabyte live upload was not run; bounded streaming and rejection paths are tested with small fixtures.

## Previous follow-up: hosted Gemma trial complete; integration proposed

User approved trying hosted Gemma. The standalone API trial is complete. Application code and database records are unchanged. Integration still needs code-edit approval under AGENTS.md.

1. Reuse the pinned container's source sampler, eight-frame inputs, schemas and frozen coffee cases. Verify source hash and save request hashes. No database writes.
2. Call gemma4-31b-it through ASU with reasoning_effort=none, named-model selection, helper add-ons off, bounded output and request time. Save each reply/error, timing, model identity and gateway correlation ID. Up to five ordered-frame cases, plus one separate native-video compatibility probe. Retry only transient service errors with backoff; two failed attempts on one step stop for review.
3. Validate description shape, status/interval consistency and source bounds. Compare source-check cases with their frozen expectations. This is an engineering smoke test, not a benchmark.
4. Save and review evidence, then present the smallest adapter plan for approval before editing application code. Results: five valid frame replies, two expected verification statuses, 7.71–15.23 seconds per request. All five frame-hash lists match the saved Qwen inputs. See evaluation/gemma-voyager-smoke-results.json.

Read-only review confirmed counts, frame hashes and latency. Prompt instructions and schemas match, but bound text uses integers in this trial and floats in the application; do not claim byte-identical prompts.

Quality limits: two descriptions leave action/object arrays empty. One action string ends mid-sentence at its field limit. The absent-person case returns no_match but explains it as insufficient_evidence. Contract validity and expected status alone do not establish useful or correct answers. No Gemma retrieval score was measured.

The separate 22-second base64 MP4 probe failed with HTTP413, Payload Too Large (6,145,362 request bytes). Preserve the response; do not retry or silently change formats. This does not establish whether video_url is accepted for smaller inputs. The ordered-frame path succeeded independently.

Proposed next steps, pending approval:

1. Add an explicit hosted-Gemma choice to the existing vision client and settings; pass the existing private key through Compose. Keep Qwen settings available. Proof: config and HTTP fixture tests for identity, authentication redaction, decoding parameters, timeout and errors.
2. Use the tested ordered frames, JSON schemas, reasoning_effort=none and helper-addons-off request. Record the actual hosted identity, unknown revision and gateway request ID; give Gemma a separate build specification. Proof: existing builds remain stored and incompatible model builds never mix.
3. Build a separate Gemma description index and repeat the frozen retrieval and source checks through the real API/worker. Proof: saved rankings, validated source intervals, errors and latency, plus the existing regression checks. Retain incomplete fields and conflicting answers in the evidence; no silent repair.

Open: approval to edit application code; retrieval quality; hosted checkpoint stability; caption/explanation reliability. Native-video input is not required for this integration.

Docker was stopped at the first check. Started the installed engine and reused the original frame/runtime environment. The standalone trial containers exited; application services were not started.

User requested hosted inference instead of another Qwen serving job on Sol. This is an access/capability check, not approval to edit the adapter.

1. Check official hosted API and vision/schema candidates. Proof: exact model IDs and capability examples. Done; see DECISIONS.md.
2. Read the account's authenticated /v1/models catalog. Proof: both requested models are BF16/native vision; Gemma schema enforcement true, Qwen false. Done after the user supplied a key in .env; key not shown.
3. Propose the smallest client change, then request code-edit approval. Proof: model identity, reasoning settings, timeout and index version remain explicit. Proposal above; code unchanged.
4. Standalone trial approved separately and completed before integration. Proof: five real frame replies and one rejected video upload; no self-hosted GPU job. Application integration remains pending.

Benchmark comparison completed in research/hosted-video-model-comparison.md. Results are mixed; Gemma was the first hosted trial for its competitive video scores and advertised schema enforcement. Qwen remains a comparison model. Eight-image input and output-contract validation passed; direct-video acceptance and CCTV quality remain unproved. No application code, keys or GPU jobs were changed by the agent during this check.

## Completed implementation: Qwen descriptions and verification

Authorized by “lets do it” after the five-step Qwen plan. Scope: short one-GPU Sol test, an explicit Qwen-compatible model endpoint, timestamped descriptions with durable jobs, keyword/dense description search, rank fusion, and source-frame verification. Preserve the working visual path. No fine-tuning, speech model, or Decider in this stage.

| Step | Proof | Status |
| --- | --- | --- |
| Inspect code, allocation, and runtime | Current callers reviewed; Voyager account/node/runtime checks | Done |
| Start bounded Sol test | Job 589241, one 80 GB A100, actual memory and replies recorded | Done; GPU stopped |
| Add model client and source input | Real HTTP requests, validated outputs, retries, and source-time checks | Done |
| Add durable description index and hybrid search | Migration preserves imports; restart/checkpoint/filter tests | Done |
| Add source verification and evaluate | Fixed cases across three paths; real source checks and failures saved | Done; quality limits recorded |
| Review and hand off | Regression tests, actual model run, costs and limits, updated docs | Done |

Final proof: `docker compose run --build --rm -e RUN_MODEL_TESTS=1 test` -> **100 passed in 32.84 seconds**, process exit 0. Two SentencePiece deprecation warnings remain. Tests use real PostgreSQL, FFmpeg, SigLIP2, MiniLM and an HTTP protocol fixture. Separate real Qwen calls below prove the Sol integration. Independent reviews found no remaining blocker after the recorded fixes.

Real run: pinned Qwen3.6-27B, vLLM 0.20.0+cu129, BF16, one A100-SXM4-80GB. Model load used 51.08 GiB; observed total GPU peak 71.835 GiB including caches. The compact runtime indexed three windows / 24 frame slots in 51.45 seconds. Five successful model calls took 4.90–16.39 seconds each. These are small-run timings, not throughput claims. [Runtime evidence](evaluation/qwen-runtime-results.json) and [GPU accounting](evaluation/qwen-gpu-accounting.json) record versions, settings, code hashes and job times. Total GPU allocation across three attempts: 1307 seconds (21 minutes 47 seconds), never more than one GPU at a time.

Quality: [frozen manifest](evaluation/qwen-coffee-smoke.json), [final results](evaluation/qwen-coffee-smoke-results.json), and [initial failures/results](evaluation/qwen-coffee-initial-results.json). On two provisional positive queries at temporal IoU >= 0.3, Recall@1 was visual 0/2, description 1/2, hybrid 0/2. The coding assistant reviewed 1 fps contact sheets; labels have no independent human review. This is one 22-second recording with only three windows, not a benchmark. Equal rank fusion lost the cup window that description search ranked first. Caption hallucination and missed action phases remain quality concerns.

Source checks passed under the final compact policy: cup action match at 16.38–20.14 seconds; red-shirt person no_match with no intervals. This checks supplied frames, not absence throughout unsampled time. The schema now forces status/interval consistency, and source bounds remain checked locally. No reply repair or hidden model fallback was added.

Cleanup and restart proof: GPU589241 stopped after checks; Voyager reports zero active Sol jobs. The test tunnel is stopped and QWEN endpoint/key cleared from the local .env. API/worker/database remain healthy at http://localhost:8000/docs. Saved description search and verification records work after recreation without Sol; new model calls return503 vlm_not_configured. The test database is stopped. Both original recordings and their earlier visual index survived the v3 migration; old/new description builds remain separate. A database backup is under ignored .codex-backups/qwen-docs.

Next plan: freeze a larger independently reviewed evaluation set; measure candidate recall and ranking at fixed source/frame budgets; then test improved ranking before training. Speech and Decider remain later work. Open questions: public benchmark/media access, independent labels, and recall/cost targets. Voyager submission still needs its separate token; established SSH access handled these authorized jobs without another manual sign-in.

### Runtime work log (historical observations; later entries record corrections)

CPU preparation job 584644 is building the pinned vLLM 0.20.0 CUDA 12.9 image on scratch. No GPU job has started. A database dump is saved under ignored .codex-backups/qwen-docs before the live v3 migration. The real-video smoke manifest is frozen in evaluation/qwen-coffee-smoke.json before Qwen inference; its 22-second MIT dataset excerpt was manually reviewed. No public benchmark score is claimed.

Live v3 migration passed: both earlier recordings and the existing visual build remain. The coffee excerpt imported and completed all three visual windows. Frozen visual Recall@1 at temporal IoU >=0.3 is 0/2; both queries ranked the middle window first. Keep those results unchanged when measuring descriptions and hybrid search. Results are in evaluation/qwen-coffee-smoke-results.json and marked partial.

Container extraction is slow but active. Submitted separate checkpoint download job 585595: one CPU, 8G, one hour, no GPU, same pinned model and scratch cache. It uses the older image only to download checkpoint bytes, never for Qwen inference. Preparation still requires the new runtime compatibility check before GPU submission. This overlaps independent CPU work within the two-running-job class limit.

Download job 585595 completed successfully in 234 seconds. The active preparation process has exactly four allowed CPUs in its Slurm affinity. Its APPTAINER_MKSQUASHFS_PROCS setting is not a supported Apptainer 1.4 variable; corrected the saved script to use the installed build command's --mksquashfs-args with explicit processor and memory limits. Do not restart the active extraction just for this script correction; Slurm already confines it to its four allocated CPUs. The installed build help confirms the argument. Reference: https://apptainer.org/docs/user/1.4/build_a_container.html.

At about 31 minutes, shared-scratch conversion remained very slow (low CPU use, PRoot in I/O wait, squashfs output 43,055 bytes after several minutes). Stop job 584644 and explicitly replan the same pinned image build onto node-local /tmp, then move only the completed SIF to scratch. The model and OCI caches stay on scratch. This changes temporary storage, not the model/runtime. Node /tmp had 333G free. Apptainer recommends local temporary storage: https://apptainer.org/docs/admin/latest/installation.html. Use the existing four-CPU/32G request and supported mksquashfs limits. No GPU job has started.

New preparation job 586649 runs on local temporary storage; extraction completed in under four minutes and compression uses the four allocated CPUs. GPU test job 587144 is submitted with afterok:586649. This revises the earlier submission order while keeping the resource gate: Slurm cannot start or allocate its GPU unless preparation, version checks, and checkpoint checks succeed. Requested one 80GB A100, eight CPUs, 96G, 45 minutes. Server authentication comes from a private environment file, not a key in command arguments.

Stopped this runtime route for diagnosis: 586649 built its SIF successfully but failed the version gate, again reporting vLLM0.11.2/Transformers4.57.6/Torch2.9.0. This conflicts with the selected image. Cancel dependent GPU job587144; it never allocated a GPU. Do not assume another image download is needed. Inspect the SIF labels, actual Python package paths, and user-site behavior in a small CPU diagnostic job before another preparation or GPU attempt. Possibilities: host-home Python packages shadow container packages, or the selected digest is incorrect. Latest local proof:98 tests passed, process exit0; no real Qwen inference yet.

Root cause proved by CPU diagnostic587811: default Python loads all three packages from /home/psheta12/.local/lib/python3.12/site-packages. PYTHONNOUSERSITE=1 instead loads container packages from /usr/local/lib/python3.12/dist-packages: vLLM0.20.0+cu129, Torch2.11.0+cu129, Transformers5.6.2. Thus earlier claims that a version check proved an old container were wrong; it measured home packages. The selected image digest is correct. Preparation and serving now explicitly disable Python user-site packages. Reuse the completed SIF and checkpoint; rerun the preparation gate, with no image/model download. Job587144 was cancelled without a GPU allocation.

Preparation587887 succeeded (cached checkpoint+SIF hash check about11s), recording container SHA256 56027dde1469ff1b6a0b11916277977469924797b49ea14a9ca052c112fa9cf7. GPU job587931 initially showed a long resource wait; reducing its pending limit from45 to20minutes enabled an earlier start on sg029. It allocated one A100-SXM4-80GB (81920MiB), driver615.71.09, then failed after20s before model load: vLLM0.20 rejects --disable-log-requests. Inspect the installed complete CLI help in a CPU job before fixing/resubmitting. No real inference yet; retain this failure evidence.

CPU CLI check588190 failed because this CUDA vLLM build initializes device configuration even for help on a CPU node. Stop that check route; do not fake a GPU platform. Read the pinned official v0.20.0 argument source instead: AsyncEngineArgs declares enable_log_requests=False and argparse.BooleanOptionalAction, so --no-enable-log-requests is the supported explicit flag. Other requested arguments passed parsing in587931. Saved serving script now requests20minutes to retain the smaller backfill request. Source: https://github.com/vllm-project/vllm/blob/v0.20.0/vllm/engine/arg_utils.py.

GPU588274 loaded Qwen3.6-27B successfully on one A10080GB: 51.08GiB model memory, weights122.90s, authenticated API ready. Three real description windows completed and persisted. Frozen initial Recall@1 at IoU>=0.3 remained0/2 for visual, description, and hybrid; retain evaluation/qwen-coffee-initial-results.json. Do not claim an accuracy gain. Captions also contained a false action involving a static white marking.

Two verification attempts failed. First: model said match but returned empty intervals; the backend rejected it. Replaced a Python-only status/interval consistency validator with a JSON-schema union (match minItems1, other statuses maxItems0), preserving the flat API shape. All100 tests passed, process exit0; review found no blocker. Second real attempt accepted that schema but repeated whitespace inside the interval array until its token limit. Stop this route and replan before another request. Preserve both failures. Use the pinned vLLM's supported xgrammar compact JSON setting (disable_any_whitespace=true), not output repair or relaxed validation. Add a new structured_output_policy to the model/index specification so old/new windows cannot mix. Stop588274, start a new bounded20-minute test, build a separate description index, and repeat the fixed cases. Pinned source: https://github.com/vllm-project/vllm/blob/v0.20.0/vllm/config/structured_outputs.py.

Submitted preparation job 584427 through the existing SSH key: course allocation, public/class, 4 CPUs, 32G, one-hour limit, no GPU. It checks the ASU-shared CUDA 12.9 vLLM container and downloads Qwen3.6-27B revision 6a9e13bd6fc8f0983b9b99948120bc37f49c13e9 to scratch. GPU serving is not submitted until preparation succeeds.

Job 584427 failed before download: the container provides python3, not python. A light container path check confirmed /usr/bin/python3 and /usr/local/bin/vllm. Preparation now uses python3 and a clean container environment with the required job/cache variables passed explicitly. No GPU was used. Re-run preparation after this specific fix.

Second preparation attempt 584566 failed its explicit compatibility check: ASU's shared image contains vLLM 0.11.2, below Qwen3.6's required0.19.0. After two failed preparation attempts, stopped this route and replanned. Use a new immutable vLLM0.20.0 CUDA12.9 image, Docker digest51fdfe717fa0505c177dddc46bd38c22fc1f2156ba14d1b1cd63f78eaa60fd32, pulled in the scheduled CPU job with cache/tmp on scratch. No model/provider fallback or GPU work occurred.

## Sol access verified

Preferred interface: Voyager MCP, as requested by the user. Its allocation and active-job tools work; its separate Sol submission token is currently missing. Use the existing SSH key for unsupported operations such as file transfer, rather than requesting another manual login. No job or token was created during this connector check. See [the access decision](DECISIONS.md).

Key-based SSH now works in batch mode from this laptop. Checked identity, full account names, class QoS limits, queue, and available runtime modules through read-only commands. Account and key-path metadata are saved in the ignored .codex-backups/sol-access directory; no password or private key was saved there.

Sol lists a course allocation and a default group allocation. Specify the course account explicitly for course jobs rather than rely on that default. The class QoS reports 24-hour maximum wall time, 32 CPUs/4 GPUs/320G per job, two running jobs, ten submitted jobs, and 960 GPU running minutes per user. Thus two GPUs permit an eight-hour request when no other running job consumes that allowance. These are scheduler limits, not a total project compute budget.

The queue was empty at the check. sbatch, Apptainer 1.4.5, and mamba/latest are available. No remote environment was installed, no project files were uploaded, and no job was submitted. GPU availability, model compatibility on Sol, and measured GPU performance still need a scheduled test.

## Active implementation: visual retrieval baseline

Authorized by “lets do next.” Scope: pinned SigLIP2 image/text embeddings, source-linked frame samples, versioned per-recording visual builds, resumable index jobs, exact pgvector search, recording/time filters, and a small reproducible retrieval smoke evaluation. Existing imports and recordings must survive the schema migration.

| Step | Proof | Status |
| --- | --- | --- |
| Inspect import path and check encoder contract | Existing callers reviewed; model revision and official preprocessing identified | Done |
| Add migration and leased index checkpoints | v1 upgrade, stale writes, incomplete builds, and vector/filter tests | Done |
| Add source-frame sampling and real encoder | Non-zero/VFR timestamps and actual pinned checkpoint smoke run | Done |
| Add indexing/search API and worker | Folder import -> ready visual build -> text query -> source candidate | Done |
| Evaluate and review | All import tests, retrieval smoke metrics, measured costs, independent review | Done |

Initial encoder: google/siglip2-base-patch16-224 at 75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2. CPU/float32 is an explicit first runtime, with four inference threads and bounded batches. No automatic CPU/GPU fallback. This tests the backend and still-image retrieval; it does not establish motion understanding or a public benchmark win. Checkpoint files total about 1.54 GB, downloaded to persistent model storage once.

Verified: downloaded the pinned checkpoint, ran local CPU inference, and upgraded the running database from schema v1 to v2 without losing its original recording. Completed visual windows persist independently; incomplete builds cannot enter search. Indexing verifies the source hash before/after processing. Search uses exact cosine distance, one specification, explicit scope, and bounded coverage details.

Final tests: `docker compose run --build --rm -e RUN_MODEL_TESTS=1 test` -> **65 passed in 19.68s**. Two SentencePiece binding deprecation warnings remain; no skips or failures. Tests include the real model and all import regressions. Review found no remaining blocker after inference-error handling, zero-vector checks, preprocessing version, and bounded coverage fixes.

Live smoke: [fixed manifest](evaluation/visual-smoke.json) and [recorded results](evaluation/visual-smoke-results.json). A generated 24-second red/blue/green recording produced three visual windows. All three queries selected the correct window at IoU >= 0.5, with mean IoU 0.8667. This is a synthetic engineering check, not benchmark accuracy. The corpus also contains the earlier unindexed demo; the response reports that missing index coverage.

Diagnostic timings: about 8.26 seconds for first indexing, including model load; about 4.42 seconds for the first query after API restart; median 0.089 seconds and maximum 0.105 seconds over nine warm queries. Initial indexing shared the machine with a test-image build. Do not use these small-sample costs as throughput claims. The result file records model/runtime, source hash, code hash, intervals, scores, sample PTS, and timing conditions.

Restart check: both API and worker restarted; the same ready build remained searchable from the persistent cache and database. The API, worker, and main database remain running. The temporary test database is stopped. A Docker Compose provenance warning remains for the model volume created during setup; model reads and persistence work.

Next: obtain an accessible rights-cleared real-video evaluation subset, freeze its retrieval manifest, and measure missed events before tuning. Then add generated-description and timestamped speech retrieval. Public benchmark media access, a video verifier, API budget, project license, and exact Sol permissions remain unresolved. Decider has not been run.

## Completed prior stage: durable video import

Scope: package and Compose setup, PostgreSQL schema, folder import API, source probing/hashing, logical windows, leased worker jobs, status and source playback, tests, and run instructions. No retrieval/model inference in this first stage.

| Step | Proof | Status |
| --- | --- | --- |
| Inspect workspace and tools | No existing source; Python and FFmpeg found; Docker engine initially stopped | Done |
| Build import storage and worker contracts | Transaction tests for idempotency, expiry, and stale ownership | Done |
| Build media and API path | Real video probe; unsafe paths and corrupt media rejected | Done |
| Package and run local stack | Compose health, import -> windows -> source playback | Done |
| Review and hand off | Independent review, actual test output, setup/status notes | Done |

Verified: Docker Desktop 4.60.1 / Engine 29.2.0, Compose 5.0.2; application runs under Python 3.12 in Linux containers. PostgreSQL 17 with pgvector 0.8.7. Tested package versions are in constraints.txt.

Final check: `docker compose run --build --rm test` -> **44 passed in 5.57s**, no warnings or skips. Real PostgreSQL tests cover concurrent claims, stale leases, abrupt process exit/recovery, idempotency, and retries. Real FFmpeg fixtures cover corrupt media, non-zero PTS, and variable frame rates. The running API accepted a generated three-second video, returned range playback (206), reused its job on reimport, and retained the same recording after service recreation.

Running API: http://localhost:8000/docs. The ignored .env points to the absolute workspace media folder. It now contains the generated implementation-demo.mp4 and visual-smoke.mp4. Tests use a separate temporary database service; it is stopped after checks. Normal API/worker/database remain running.

Import-stage review fixes: pin each database to an absolute host library path; limit window count; reject stale commits; return 503 for wrong schema; document the size/mtime playback check. That stage used no model or paid API; visual model checks are recorded above.

The visual encoder and baseline are now implemented as recorded above. QVHighlights remains a proposed external dataset; no public benchmark score is claimed.

Main deliverable: [full project draft](research/full-project-draft-plan.md).

Supporting evidence: [pipeline research](research/pipeline-research-review.md) and [benchmark strategy](research/benchmark-strategy-review.md).

## Research work and proof

| Step | Status | Proof |
| --- | --- | --- |
| Review existing decisions and architecture | Done | Draft separates confirmed choices from proposed changes. |
| Check primary papers and benchmark protocols | Done | Linked research reviews distinguish tasks, input settings, and access limits. |
| Prepare complete design and staged evaluation | Done | Draft covers ingestion, retrieval, verification, counts, costs, release, and later training. |
| Review the draft for conflicts and unsupported claims | Done | No blocking conflict found. Added per-query-type routing checks, source-seconds/frame budgets, and stale-worker lease protection. |

## Proposed build order and proof

1. Confirm data/model access and freeze evaluation. Proof: official evaluator fixture and real model smoke run.
2. Build durable import and visual retrieval. Proof: source timing, restart, duplicate-import tests, and baseline metrics.
3. Add description and speech search. Proof: branch ablations, mixed-query evidence, and missing-modality checks.
4. Add source verification and playback/export. Proof: reviewed source intervals and invalid-output tests.
5. Test temporal sampling and bounded refinement. Proof: fixed-budget comparison and error analysis.
6. Test Decider against all-path search. Proof: recall/cost results including GPU load and swap time.
7. Add complete-scope event search and counting. Proof: event matching, duplicate handling, and visible coverage gaps.
8. Package the local release. Proof: fresh install, restore, and folder-to-evidence test.
9. Train only for a measured failure. Proof: held-out gain over the frozen base and a successful resumed run.

## Open decisions

- First public benchmark and raw-media access: QVHighlights proposed, TVR next.
- Whether all-path search becomes the default if Decider fails its cost/recall test.
- First video verifier, model access, and optional API budget.
- Rights-cleared product test recordings and event definitions.
- Draft success thresholds and actual Sol permissions.

## Earlier classifier experiment, retained within the full plan

Selected: [`perplexity-ai/pplx-decider-flash-v1.2`](https://huggingface.co/perplexity-ai/pplx-decider-flash-v1.2), 4B. Initial test choice; no measured fit, speed, or accuracy.

Status: classifier experiment not started. Docker and the import application now pass the checks above. Model access, CUDA execution, fit, speed, and route accuracy remain untested.

## Read-only evidence already reported

- Laptop: 16 GB RTX 3080; about 32 GB RAM.
- Docker 29.2 client and server now work; the engine was started for implementation.
- WSL entries include Ubuntu and docker-desktop.
- Host Python 3.13.5 has torch; huggingface_hub is absent.
- CUDA inside the intended runtime and actual checkpoint access remain untested.

## Steps and proof

| Step | Work | Proof |
| --- | --- | --- |
| 1 | Check Docker server, GPU exposure, runtime compatibility, and model access. | Record versions, successful server/GPU checks, and checkpoint-access result. Report blockers explicitly. |
| 2 | Load the official decision runtime and run a short-input smoke test. | Save valid fixed-label or yes/no output, cold-load time, and peak VRAM. |
| 3 | Define a small labelled route set: visual, visual-description text, spoken text, mixed queries, count queries, and unavailable modalities. Fix expected decisions before evaluation. Separate threshold tuning from held-out tests. | Save versioned cases, expected outputs, route policy, and separate tuning/test cases before the test run. |
| 4 | Evaluate routing and report results. | Report route accuracy, per-path recall, median and p95 warm latency, peak VRAM, and errors, with the model revision and runtime settings. Do not invent pass thresholds or latency targets. |

Compare end-to-end evidence recall with an all-path baseline only after retrievers exist. Until then, routing scores do not establish pipeline evidence recall.

## Open questions

- Which labelled cases, expected route policy, and thresholds should the benchmark use?
- Can the checkpoint be downloaded and run in the chosen runtime within available memory?
- What measured routing quality and latency justify keeping this initial model?

## Autonomous follow-up authorized by user
1. Finish long-video indexing fix and preserve the prior build. Proof: three live probes, full index, source checks, regression tests.
2. Verify chat.md research and inspect current retrieval limits. Proof: primary-source notes and code-backed findings.
3. Implement the smallest complete evidence-search improvement with fixed budgets and explicit limits. Proof: targeted tests, saved baseline comparison, UI checks.
4. Add reproducible external evaluation support where data is accessible. Proof: official metric agreement, real measured runs; no SOTA claim without a comparable held-out result.
5. Review changes and record results, cost and remaining limits.
Runtime restart note: Docker was stopped at continuation. First probe command used an unsupported compose flag; corrected command found engine unavailable. No model trial has run yet. Restore Docker before model trials.

Gemma fix proof: all three live interval probes passed (384-394, 376-386, 392-402); 54-107 completion tokens. Full regression: 139 passed, two existing warnings, 46.04s. Deployed prompt v2 and queued a separate 205-window build; IDs saved privately in .codex-backups/gemma-prompt-fix/new-index-job.json. Old failed build remains preserved.

Continuation 2026-11-08: Docker restarted; long index resumed at75/205, public example19/19ready. Old48 rows match original database dump exactly. New evidence API/UI and evaluator passed182tests; API deployed without restarting long worker. Public query8056: description R@1@.5=0, R@3@.5=1. Ranked/adaptive source checks both use2calls16frames and return matching sub-action intervals too narrow for annotated event (all tested final interval recalls0). Do not claim adaptive gain. Optional fixed-recipe local cross-encoder trial moved112-122 fromrank2to1 (IoU0to.625),0.15swarm CPU; implement opt-in with provenance and unchangedbaseline. Also explicit source-status evaluator guard and exact media duration150.016533 vs roundedannotation150.

Optional reranker implementation and API/CLI/UI wiring complete. Full model-enabled suite198passed in69.96s, two existing warnings; additional real reranker API integration2passed5.71s. Same19candidate pool live: baseline rank1IoU0, rerank.625; officialR1check agrees. Source checks ranked/adaptive2calls16frames; reranked1call8frames. All finalintervalIoU recalls0: record localization limit. Browser whitespace/doublesubmit/download/seek116.382933ready4/refresh/mobile375=scroll375/zeroerrors passed. Sanitized result evaluation/evidence-search-public-smoke-results.json. Waiting full long index (162/205 lastcheck), then source-check originalfailedsection and finalworkerrecreate.

Final review: source-status scoring bug fixed with regression tests; logical checks now separate HTTP retry attempts and sent frame slots. The first independent review passed source scope/duplicate/error design; the follow-up reviewer hit an account usage limit. Root reviewed the optional reranker and API/CLI wiring directly, then ran the model-enabled tests and live browser/API proof. No separate final independent reranker review completed.

Latest wait checkpoint: 194/205 windows. All code edits and 198-test regression are complete. Final API integration passed with real local reranker; public browser query/download/playback/refresh passed. Monitor is append-only at .codex-backups/gemma-prompt-fix/progress.jsonl. Next: once ready, execute validate-complete.py inside API, save private proof, recreate idle worker to current image, test original video in browser, update top status/AGENTS and final handoff.

Browser final selection re-plan: the polling list replaced a captured element reference; a raw run-code snippet then failed because current CLI expects a function. No query was submitted to the wrong video. Read run-code --help, then use a file containing the documented async(page) function and observed role/name locators.

## Final acceptance, 8 November 2026
- Full long-video build ready:205windows,1640frame slots,205distinct request traces, correctpromptv2, sourceSHA checked. Every saved description and timestamp is valid. Maxsummary181characters; maxcompletion119tokens. Old48 rows still equal the original database dump.
- Idleworker recreated to current image. API and database healthy; testdatabase stopped. No Sol jobs started.
- Code/tests:198model-enabled regression tests passed69.96s, two existing warnings. Extra real local reranker API test2passed5.71s. Browser public query double-submit produces1request, trace downloads, seek116.382933ready4, refresh and mobile checks passed. Deliberate API restart produced3polling network errors; a fresh page load has0consoleerrors.
- Equal19candidate pool: reranker changes rank1 temporalIoU0to.625; source checks2to1. Adaptive selection alone ties ranked. Full-event modelinterval recall remains0on the known public query. No general benchmark gain, complete counts, event absence, or novelty claim.
- Reproducible public evidence: evaluation/evidence-search-public-smoke-results.json; source-linked research:research/chat-followup-evidence.md. Private footage/evidence stays in ignored backups.
- Remaining research: freeze independently reviewed held-out media/queries and compare complete-event recovery at the same actual frame/call budget. No further approval question is pending for this completed implementation stage.

## Final browser verification failure: follow-up fix
The full205-window description index is ready and preserved. The first full-video browser query failed during source verification at248-258seconds:HTTP200, finish_reason=length, response prefix truncated at4096chars; no completed checks. Preserve .codex-backups/evidence-integration/original-verification-failure.json. Do not treat it as an index failure or successful absence result.
Plan:1) Add failing protocol/rejection tests;2) make Gemma verification JSON fields/short text explicit, retain schema and2048tokens, give verification its own trace/spec prompt version (leave description build unchanged);3) test exact failed query/window and public controls before deployment; stop and re-plan after two failed trials;4) regression, deploy and repeat original browser query. Preserve previous public experiment as the old-verifier result if prompt changes; do not merge comparisons across prompts.

## Final follow-up acceptance: verification fix complete
201 tests passed in71.96seconds with two existing warnings. Exact failed verification query/window and public positive/negative controls pass with explicit short JSON instructions and unchanged strict schemas/token caps. Verification prompt identity is persisted correctly; the description build remains v2and205/205ready. All three public source-check policies were rerun with the new verifier: ranked/adaptive2checks16frames; reranked1check8frames. Complete-event IoU remains a measured limit. Earlier results are retained with the previous verifier identity.
The original full-video browser query now succeeds:1check,8frame slots,9.56seconds, saved trace and correct verification version. Playback opens249.882966seconds with readyState4; final browser console0errors. Private trace is saved under .codex-backups/gemma-verification-fix; browser captures are ignored by git. API/worker/database remain running; test database stopped after checks. No further implementation or approval step is pending in this stage. Broader held-out benchmark and novelty claims remain future work.

## New request: broader benchmarks, full events, speech and counts

Status: inspection and primary-source research only. The replacement AGENTS.md requires approval before code changes. No new application edits, model jobs, package installs or bulk downloads in this stage yet.

Evidence:
- Current source-check policy stops at its first match and has no event-edge state. It cannot claim full-event extent.
- On the known public example, target106-122 is16s long; a10s window has maximumIoU0.625. Current model interval116.382933-120.153366 hasIoU0.235652. Improving ranking alone cannot remove that structural limit.
- No transcript tables, speech jobs or event-count records exist. media.probe stores only has_audio, not audio-stream origin/time base.
- QVHighlights raw media is a143.7GB tar.gz. Confirmed byte-range support does not provide random member extraction through gzip. The small public clip remains a development example, not a held-out test. Alternative benchmark access is under investigation.

Proposed staged work, awaiting approval:
1. Freeze accessible benchmark media, IDs, source-group split, prompts and a hard model-call/frame budget before new policy tuning. Baseline: current ranked and reranked retrieval/checking. Proof: official evaluator agreement, all selected files indexed, complete query accounting, no labels in model input, paired per-source results and costs. A subset result must name the subset and cannot be called full-dataset SOTA.
2. Add optional full-event inspection: retain a match as a retrieval seed; inspect adjacent windows at unchanged frame density when onset/offset remains open. Save observed/open/unknown edge state with source samples; return unresolved bounds when evidence is missing. Keep verified sub-action intervals separate from complete-event proposals. Proof: equal3checks/24frame slots first;6/48 is a separate condition. Test clipped events, repeated adjacent events, gaps, start/end-of-file and multi-action questions. No description re-index or schema migration is expected for this versioned verification operation.
3. Add speech search: timestamped supplied subtitles, then explicit local ASR with the existing Transformers/FFmpeg runtime if its capability check passes. Reuse MiniLM and keyword search; label visual descriptions, supplied captions and inferred speech separately. Add durable transcript jobs/builds/segments and an additive migration. Record audio-video time origin. Proof: exact phrase/name retrieval, timestamp playback, missing/silent audio, nonzero audio offset, resume and mixed visual/spoken queries. Compare WER and retrieval separately. A pinned Whisper-base CPU checkpoint is a starting candidate, not a quality decision; faster-whisper remains an alternative if measured need justifies a new dependency.
4. Add scoped event counting: require an explicit event definition and camera/time scope. Persist scanned partitions, evidence-linked events and uncertain intervals. Count event rows in code; never count retrieved windows or inferred identities. Proof: one-to-one event precision/recall, countMAE/exact-count rate, boundary duplicates, simultaneous events, gaps and restart. Full computational coverage does not prove semantic completeness. Stop-before-complete must return a partial observed count, not an exact total.
5. Research claim gate: test whether inspection based on missing action/edge/coverage evidence improves complete-event recall at equal total cost over reproduced baselines. Report regressions and abstentions. This is a hypothesis; novelty requires a specific distinction from existing methods and a controlled held-out gain.

Open questions: accessible benchmark subset and media terms; first counted event (door visit, doorway crossing or another defined action); actual ASR fit/quality on this laptop. The first approval can cover benchmark and boundary implementation while later event semantics remain open.

### Concrete first-stage proposal

Data candidate: Charades-STA on author-linked Charades indoor videos. Root independently confirmed HTTP206 for the final64bytes of the16,339,546,533byte official ZIP64 archive and valid end records. The research agent parsed the directory and recovered the license; inspect its report before any media download. Fetch only selected members with bounded ranges, exact Content-Range, length, CRC and final source hashes. Keep licensed media and generated annotation manifests private; commit download code, source references and aggregate results only. DiDeMo is a reserve route with its own evaluator, not a silent substitute.

Proposed pilot: up to20videos and40queries, selected deterministically from official development/train and test source groups before predictions. Keep entire source videos in one group. Freeze actual query count and media hashes before tuning. Hard limits:1GBmedia and500hosted model calls including indexing and evaluation; compute the full run budget from real durations before inference. If it cannot fit, revise the declared scope before starting instead of dropping failed queries afterward. No new GPU job or training in this slice.

Compare current ranking, optional reranking and event-extent inspection. For the controlled policy comparison, use the same candidate pool, verifier/backbone, frame size and actual3checks/24frame slots; baseline must spend the same inspection budget rather than stop early. Keep the current stop-on-first-match product baseline as a separate cost/quality point. Six checks/48slots is a separate condition. Preserve model version/fingerprint, prompts, offline index cost, requests and errors. Hosted model revision is not pinned; final model-comparison claims need that limitation resolved or stated.

Count success by official temporal metrics plus start/end bracket error, complete-event coverage, false-complete rate and actual work. Do not stretch predicted timestamps to annotation edges. Keep the original index and current UI policy working. First-stage files: vlm.py, analysis.py, evidence.py, api.py, small UI controls, evaluation adapter/runner and their tests; existing versioned verification JSON avoids a DB migration. Later speech/count stages need separate additive migrations and data contracts.

Novelty hypothesis: choose the next source inspection from missing action evidence and unresolved event edges, then refuse a complete-event claim if the budget ends with unresolved evidence. Compare with uniform neighbor inspection as well as the existing adaptive policy. Existing papers already use repeated retrieval and memory; those ingredients alone are not a novelty claim.

Unresolved for first approval: accept this benchmark/boundary scope and call/download caps. Unresolved for later counting: which event is counted. No application code has been changed for this proposal.

### Updated first-stage scope after access verification

The checked report is research/next-benchmark-access.md. A deterministic source-group pilot is available:20train/development files53queries,25test files69queries,45videos122queries total. Exact selected compressed media is78,400,663bytes. Use the pinned VSLNet paper-author annotation copy, record its hashes, and state that it was not byte-compared with unavailable original TALL downloads. All selected members exist in the official ZIP64 directory. Complete member decode/CRC is still a required preparation gate.

This supersedes the earlier20video/40query/500call estimate. Proposed full pilot caps:45videos,122queries,1GB local media and1500hosted model calls including indexing, controls and every ablation. Before inference, compute actual window and call totals from source durations. If the frozen run cannot fit, stop and revise scope before any test prediction. A tiny access/protocol gate precedes the full download and experiment. No new dependency, GPU job, model training, bulk archive download, description rebuild of the user's video, or counting/speech schema change belongs to this first slice.

Root independently fetched the complete1177byte license from official Charades.zip through a bounded1981byte HTTP206 range, inflated its558byte payload and verified CRC32=4255669424. It permits research/evaluation use and restricts commercial use and data redistribution/public modification. Retain all licensed media, queries, normalized labels, frame traces and generated descriptions in ignored local storage. Publish code, selection rule, source references/hashes and aggregate results. Do not redistribute data or annotation derivatives with the open-source project.

Approval request: implement this benchmark and event-boundary slice first, then use its measurements to scope speech and the first explicitly defined counting event. The broader roadmap above remains proposed. Novelty/SOTA are success goals, not completion claims or guaranteed outcomes.

## Approved implementation: benchmark and event boundaries

Approved by user: "implemnt". Scope:45videos122queries, <=1GBmedia, <=1500hostedrequest attempts including index and experiments. No new training/GPUjob, speech/count implementation or originalvideo re-index.

Work ownership: dataworker prepares selective ZIP64 downloads/manifests; extentworker owns new modeltask/analysis bridge/controller/tests; rootowns API/UI,evaluation adapter/runner,budget enforcement and docs; protocolreviewer reads reference evaluation and reports only. Files are disjoint.

Proof gates:1)data transport+CRC+license+actualdurations and protocol labels;2)newtask protocol/scope/budget tests and developmentsmoke;3)frozenprotocol/sourcegroups/cost calculation;4)durable indexing and resumable paired benchmark;5)sourcegrouppairedmetrics, regressions and failures;6)fullregression/browserchecks and preserveduserindex. Twofailures on a step stopforre-plan.

Protocol correction before any prediction: pinned VSLNet processing clamps rawlabels to its pinned charades.json duration. Some selected rawends exceed that metadata by up to1.42s. Preserve rawlabels and explicitly use the author reference preprocessing for main comparable metrics; never clamp to ffprobe or modify predictions. Store reference annotation duration and actual playable duration separately. This is a sourced benchmark-protocol choice, not a tuned result.

Budget design: isolate benchmark records in a new PostgreSQL schema using the tested search_path pattern; user app records stay in public. A local benchmark-only HTTP gateway with a durable standard-library SQLite call ledger will reserve each external attempt before forwarding (including retries); cap1500 cannot be exceeded. Store no credentials in logs. Pipeline clients and their retry behavior stay unchanged; no output repair or provider fallback. Completed cases and model run identities persist for resume.

### Implementation gate status
45 videos,122 queries and186 windows prepared and indexed. Media79,522,570bytes. Index used186/1500 external attempts, allHTTP200. Full model-enabled regression318passed; latest runner6passed. First development start failed before model requests because manually created run-binding used CRLF; original saved, identical JSON canonicalized to LF bytes. No identity, ledger or limit changed. Next:3development-query live protocol gate, then complete development, freeze and held-out test.

Live gate:9/9 development cases passed strict task and trace validation. Small gate has no R1@.5 gain; no tuning claim. Browser whitespace/double-submit/trace/playback/refresh/mobile passed on public control via shared gateway;0console errors. Two public controls used2 external attempts. Full development159case grid running, reusing9 gate cases. Code hashes fixed for this run. Original public jobs idle; original205ready+48failed build counts unchanged before deployment.

Deployment:API/idleworker recreated from current image. localhost8000 browser confirms new option and enabled uploads. First deployment probe assumed selection from another origin and timed out; corrected probe checks actual selected ready video and passed. No model call came from deployment checks. Browser control service stopped cleanly; full development continues. Test database stopped after318pass regression.

### Development protocol failure and revised plan
V1 stopped after56/159 completed cases,359 externalattempts total. Failed57th case had7absent newframes and1present repeatedanchor but redundant modelstatus=match; strict validator correctly rejected it. Preserve all v1 cases/errors and ledger. Root cause: asking model to repeat a deterministic new-frame summary introduces role/status contradictions. V2 removes status from the wire schema, derives it from validated non-reference labels, and records the derivation in the trace. This is a new task protocol, not reply repair. Keep strict role/duplicate/all-support validation. Tests and small live gate precede a complete v2 development rerun. Upper bound359+477+621=1457attempts; all old attempts remain charged. No test prediction has run. Uncertainty: perception quality is unchanged and not established by protocol reliability.

V2 protocol tests59passed, API+runner8passed. Reviewer confirms strict four-field contract, no outputrepair, guards retained. Code now final for full regression and a new development gate. The fix used a role/status contradiction only; no target temporal labels were used. Retain explicit v1->v2 chronology in results.

V2 acceptance gates:85VLM/controller tests passed;8API/runner passed; full model-enabled regression326passed156.32s with2existing warnings. Live3-query gate9/9cases passed,386totalattempts; zero v2errors. API/worker deployedv2. Full v2development started, reusing9same-protocol cases. Upper bound1457total attempts unchanged. Oldv1folder remains56cases+1error and all359previous attempts charged.

### Second live failure: stop and re-plan before more inference
V2 stopped after44completedcases at493totalattempts. Failed neighbor had anchor_index7, all8labelsabsent, query_supportunknown, anchor_relationnot_applicable. The validator wrongly required an event relation whenever a reference slot existed, even when neither frame set showed a target. V3 accepts not_applicable when no positive new/reference pair exists; positive-pair link requirements and strict schema remain. Preserve raw reply unchanged; no fallback or outputrepair.
A full3condition development rerun would exceed1500. Revised pre-test design:all53developmentqueries,2extentconditions,3checks/24slots each; all69heldoutqueries,all3conditions,same3checks/24slots. No query or source is dropped. Development tests controller behavior against uniform extent; fixedranked comparison is heldout only. Worst total493+53*2*3+69*3*3=1432,leaving68retryattempts. Freeze this design before any test prediction. Proof:negative-pair N/A passes, positive-pair N/A fails, full regression,9casebudgetforecast, complete new development grid and untouched test. Openquestions:nonewithinthisapprovedcap.

V3 model/controller94tests passed75.12s;API/runner8passed14.93s. New3-query gate6/6cases passed,511totalattempts, zero v3errors. Full v3development106casegrid running with all53queries;6gatecases reused. Full regression running. Reviewer confirmsN/Aapplicabilityguard and unchangedpositiveextensionrequirements.

Full v3 model-enabled regression335passed162.95s;2existingSentencePiecewarnings. DeployAPI/idleworker to this image and stoptest-db. OriginaldescriptionGemmav2specunchanged; no re-index. Remaining:complete106devcases,freeze,test207cases,aggregate/costpublicationandfinalapp/integritychecks.

Read-only integrity probe needed pg_restore --file=- to select stdout; first command failed before output. Added that explicit target. Sorted original public description COPY rows equal the pre-benchmark dump; proof saved privately. No database restore/write occurred.

### V3 stopped: response schema must enforce input role
At616totalattempts, v3stopped40completedcases. Failed positive new/reference pair returnedrelationN/A. Existing wire schema still allowed all4relationvalues; prompt-only role constraints did not guide constrained decoding. V4 selects strict seed versus neighbor response schema before the request:seedrelationconstN/A;neighborenum same_event/different_event/unknown, with unknown for no new target or uncertain linkage. Keep raw replies unchanged; reject invalid wire values, no repair/fallback. Status stays derived from newlabels; duplicate andall-support guards remain.
Re-plan before code/inference:all53developmentqueries with mainextent at3checks(159max), thenall69held-out queries withall3methods at3checks(621max). Every selected query/source remains. Development is now reliability/behavior validation, not a paired quality comparison. Held-out primary comparison remains unchanged and untouched. Max616+159+621=1396,104headroom. Preserve v1/v2/v3 folders and ledger. Proof: outgoing per-role schema test, strict rejection,94+tests andfullregression, livegate, all53devqueries, frozen3conditiontest. Questions:noneinsideapprovedcaps.

V4 gates:99VLM/controller tests passed80.86s;8API/runner passed14.93s. Live3-query gate3/3passed with0errors,625totalattempts. Full53query development nowrunning,3gatecasesreused. Full regressionrunning. Seed/neighbor JSONschemas are testedonoutgoingrequests. Reviewerfoundnoblocker.

Final v4 fullregression340passed167.89s;2existingwarnings. API/worker deployedv4;test-db stopped. No pipelinecodechangesarepending. Complete53developmentcases, freezeexactcode, execute207held-outcases andpublishaggregates. Historical protocolfailuresremainprivateandcharged.

### V4 stopped: separate context support from new-frame presence
V4stopped8cases at642attempts. Neighbor index0referencepresent,all7newabsent,querysupportall,relationunknown. The model evaluated full-query support over suppliedcontext while contract requirednew-onlysupport. V5 explicitly makesquery_support cover all suppliedorderedframes(includingreference), while deterministic status and intervals still coverNEWframesonly. Guardallrequiresatleastoneinputpresent; referencealone nevernewmatch. Negative neighbors cannotpromoteparentpartialquerysupport (controller onlypromotesinsidepositive same_eventextension). Add regressionforthisguard. Rawv4reply remainsrejected underoldprotocol;no reinterpretation/repair. KeepV4per-roleschemas.
No gridchange:all53devqueriesmainextent3checks thenall69testqueries3conditions3checks. Worst642+159+621=1422leaves78. No testpredictionyet. Code+tests+livegatebeforefulldevrestart. Questions:nonewithinapprovedscope.

V5focused102tests passed84.07s,scope/negativeclosurepersistencetested. Reviewerfindsnoblocker. Livegate3/3passed,651totalattempts. Full53devqueriesrunningunderfinalv5hash;gatecasesreused. Fullregressionrunning. No held-outpredictionyet.

Finalv5fullmodel-enabledsuite343passed171.82s,twoexistingwarnings. DeployAPI/idleworkerv5 andstoptest-db. Development6/53successfulasof662totalattempts. Allcontextsupport/newstatusscopeexplicit; no codechangespending. Remainingfull53dev, optionalbudgetedUIcontrol, freezeand207testcomparisons, aggregatepublication/integrityproof.

Fullv5development53/53successful,159requests,801totalattempts,zeroerrorsandretries. All4historicallyfailedqueriespassedmainextentunderfinalcontract. Nextbudgetedbrowsercontrolthenfreezeexacthashesandall207held-outcomparisons. No pipelinecodechangeafterdevelopment.

Finalv5browserpassed:emptyinputrejected,double-submit1request,tracev5+contextscopepersisted,playback116.382933ready4,390pxnooverflow,refreshpassed,0pageerrors. Paidcontrol1attempt(total802);controlserverstopped. Normal8000browseruploads+newoptionpassed. Freezecompletedwith14sourcehashesmatchinghostfiles;full53devreportstored. Test207casesstarted;noquality-driveneditsafterfreeze. Maxremaining621<=698attemptsavailable.

Reportingnote:caseelapsedtimebeginsaftersharedretrieval;labelp50/p95as source-check/controller-stage latency,notfullend-to-endquerylatency. Raw/reranked retrieval timing livesinsavedretrievalresponses;offlineindexcostandallhistoricalfailedprotocolattemptsareseparate. Finalpublicartifactmustincludeallglobalcosts,notonlysuccessfulfinalcases. Do notreadtestqualitybeforecompletegrid.

Held-out run stoppedafter63cases at990attempts:ranked_fixed firstcheck modelHTTP200/finishstop returnedmatchinterval[6.9,6.9],rejectedbyexistingnonzerointervalschema. Preserveerrorandallcases. No code/promptchange permittedinsidefrozenrun. One explicit operationalresume underEXACTsamehash/inputs (existingresumableCLI),allfailedattemptsremaincharged; reportfailed-overheadseparatelyanddonotcalleffectiveper-queryworkequalforanyrecoveredcase. Ifsamefailure repeats,stopandreportrunincomplete,notSOTA. No qualityscoresreadortarget-basedchange.

### Frozen v5 run incomplete; do not repair or relabel it
Samebaselinepointreply[6.9,6.9]repeatedat991attempts. Originalteststopswith63/207completedcases,2errors;samefrozenhash,promptsandinput. NeverclaimthiscompleteorSOTA. No qualityscoresread.
Rootcause:sourceverificationtreatsvalidinstantaneousevidenceasaninvalidinterval; newextenttaskalreadykeepspointsspanless. Approvedbackendfix:acceptorderednondecreasingevidencetimes,makepointmeaningexplicitwithnewGemmaverificationprompt/specversion;UIlabelsat-time;evaluationfilterszero-durationpointsasexplicitlocalizationabstentions,neverstretchesduration. Preserveallrawfailedreplies. No fallback/outputrepair.
New exploratoryprotocolaftertestinputexposure,notpristineheldout:all53developmentqueriesmainextent1check;all69evaluationqueries3methods2checks/16slots. Allselected122queriesremain. Storeseparatepoint-awarefreezeandnewcodehashfolders;oldfreezeuntouched. Max991+53+69*3*2=1458,42headroom. Exactfailedsourceprobe/GUIwithincapifneeded. Proof:pointat0/nonzeroallowed,reversed/outofboundsrejected,pointonlyzeroIoUabstention,nonzerointervalmetricsunchanged,strictcompletegrid/costcaps,fullregression,fresh53dev,lockprotocol,full207caseexploratoryevaluation. Questions:noneinsideapproved1500cap.

Pointawaregates:VLM+description88passed1modeltestskip48.68s;comparison49passed0.42s. Fullmodel-enabledsuiteincludingthatembeddingcasebuild/runningnow. Exactfailedsource+queryundernewverifyv2returnedvalidinsufficient_evidence,1attempt(total992). No durationinvented. Updatedmax992+53+414=1459,41headroom. Safetyreviewernoblocker;sourcefilesfinalfornewrun.

Point-awarefullmodel-enabledsuite370passed177.41s,2existingwarnings. DeployAPI/idleworkerpointcontract,stoptest-db. New53developmentqueries1checkrunning;fullnewsourcehashnooldcasemixing. Oldv5freeze/63testcases/2errorspreserved. NextUIpointfixture(noexternalcalls),freshdevelopmentcomplete,newfreeze(linkspriorhash),all207exploratorycases2checks.

Point-awarefreshdevelopment53/53passed,1checkeach,53requests,total1045. UIHTTPfixturepassedAt01:56.4seekready4,external0/database0; browserreloadedtocleartestanswer. Freeze newpoint-awareprotocol next;oldtestfreeze remainsimmutable. Evaluation207cases2checkcapplanned414<=455remaining,41headroom. Everyselectedqueryretained.

Pointawarefreezecompleted;14hostsourcehashesmatchandpriorfreezebyteSHAverified. Newstatus exploratory-after-prior-protocol-exposure,dev1/eval2checks,verificationGemmaJSONv2/pointsschemav3,extenttaskv5. Full207caseevaluationstarted;no pipelineeditsuntilcompletion. Oldfrozen3checkrun63cases2errorsstillseparate.

### Point-aware run stopped87cases: clip support is not localized evidence
At1220attempts,extentseed query_supportall withall8samplelabelsabsent,referenceNone. Wire outputvalid; two modelheads disagree or recognize orderedcontextwithoutalocalizabletimestamp. Guardincorrectlyturnsnonlocalizablecontextintoaprotocolerror. Newinterpretationretainsrawfields, logsstructuredwarning, derivesinsufficient_evidence (nevermatch/absence/interval) whenqueryallbutnoinputpresent. Duplicate-timestampcontradictionsstillraise. Prompts/schemas/requestgenerationunchanged. Oldpoint-awarefreeze/87cases/errorpreserved. No qualityscoresread.
Budget-compatiblecachemigration:proveVLMdiffonlyoldall-supportguard -> explicituncertaintybranch;allnormalmodelrequest/outputcodeASTidentical;allotherinference/evaluationfilesunchanged. Everycachedsuccessfulcase mustnothitnewbranch;validatefullsource/scope/budget/modelidentityandcopyALL53dev+87evalcases withparentcaseSHA/protocolprovenance. Raw model results/costs/latencyunchanged. Do notreplayfailedresponseasanswer; rerunmissing120casesfresh at2checks. Newfreeze referencesoriginalv5andpoint-awareparenthashes; no overwrites. Worst1220+120*2=1460<=1500,40headroom. Final414model-attemptcost includes174reusedalreadychargedattempts;globalledgercountsuniqueattemptsonce. No held-out/SOTAclaim. Proof:uncertaintynevermatch/complete,duplicatesstillreject,ASTcompatibilityrejectsanyprompt/unrelatedlogicchange,cacheimmutability+wholegridproof,370+fulltests,freezeandcomplete207caseexploratoryrun. Questions:nonewithinapprovedcaps.

Context-localizationfullsuite377passed182.81s,2existingwarnings. API/idleworkernewruledeployed;test-db stopped. Realcachemigrationexit0,0newrequests(total1220),53dev+87evalcasescopied. RootindependentlyverifiedEVERYrawresultidenticalandparentcaseSHA;oldfilesunchanged. Newcontext-localization.freezecompletedwithpriorpoint/v5hashchain. Full207caseevaluationresumed,87cached/120fresh. Max1460total;40headroom. No source/promptchangesafterthisfreeze.

FINALmodelruncomplete:207/207canonicalcases,69queries25evaluationvideos,3methods2checks/16slots;0currenterrors,0transientretries.87cachedresponses+120freshcases(240requests). Global1460/1500uniqueexternalattempts,40remaining;53developmentcases53cachedrequests. Allpreviousfailuresandprotocolsretained. Scoring/publicaggregateandindependentreviewnext;nomoremodelcallsneeded.

## Final acceptance of this implementation slice

The exploratory pilot is complete: 53 development queries, 69 evaluation queries from 25 videos, and all 207 comparison cases. Each method used two checks and 16 frame slots per evaluation query. There are no errors in the final run. The ledger has 1,460 unique external attempts under the 1,500 cap, with 40 unused. The current model-enabled suite passed all 377 tests, with two existing warnings.

Independent review recomputed all metrics and confidence intervals. It checked all 140 reused raw results, parent hashes, source hashes, unique request accounting and public-file privacy. No blockers remain. The public artifact is evaluation/charades-point-aware-pilot-results.json. Old failed runs and freezes remain unchanged. The result is explicitly exploratory after test-input exposure; cached work is counted once.

The new method does not beat strong retrieval: R@1 at IoU 0.5 is 33.33%, versus uniform inspection at 30.43% and reranked retrieval at 42.03%. Mean IoU is 28.86%, versus 35.89% for reranked retrieval. Stricter R@1 at IoU 0.7 improves to 13.04%, versus 4.35%. The controller gain at IoU 0.5 has a confidence interval that includes zero. Six of eleven model-complete proposals fail the IoU 0.5 localization check. No SOTA, novelty or reliable full-event claim is supported.

Final app checks: health is ready; no public jobs are active; uploads and the new option work; a fresh browser has no console errors. Real-model browser checks passed. Labelled point and abstention UI fixtures made no model calls or database writes and were cleared by refresh. All 281 original description rows match the backup; the 205-window ready build and older 48-window build remain intact. API, worker and database stay on. Test database and temporary control services are off. No Sol job, training run or new dependency was added.

Remaining broader goals: independent long-video and negative-query evaluation; better temporal perception and coverage; speech/subtitle search; reliable counts for a defined event; Decider and reference-image queries. These remain unbuilt or unproved. Do not start another implementation slice without the inspection and approval process in AGENTS.md.

## Research-led performance campaign — 14 November 2026

The user now authorizes research, the selected experiments, implementation and longer Sol training. This replaces the previous slice's no-training scope for this campaign. The old pilot and its 1,500-request ledger stay closed and unchanged. No new hosted calls are planned. Keep the working app and original indexes intact.

Evidence: extent loses to caption retrieval at IoU 0.5 and mean IoU. Papers support ordered relevance curves, motion features and learned boundaries. See research/retrieval-experiments-2026-11-14.md and research/temporal-model-options-2026-11-14.md. Paper scores are not our scores.

1. Audit current candidate coverage and rank errors from saved outputs. Test a small score-curve grid on 53 development queries; freeze before scoring the old 69-query exploratory set. Prove: identical cache hashes, all queries retained, decoder edge tests, paired source-video intervals. Interpolated caption scores are estimates, not dense visual observations.
2. Prepare the pinned UniVTG release in separate Sol research storage. Verify downloads, feature arrays, source-disjoint splits and the four-row training-label discrepancy. Prove: artifact hashes, exact complete-grid counts, finite arrays, no missing-feature substitution. Keep dataset files private. Use isolated research packages; no application dependency changes.
3. Train the unchanged UniVTG head from scratch as a control, then an IoU-quality foreground adaptation with identical features, architecture and initialization. Three seeds, 100 epochs, train-video-disjoint validation; no test-based epoch selection. Prove: short allocated-GPU smoke, finite loss/gradients, saved optimizer/scheduler/RNG state, resume test, measured throughput and peak memory. Start with one GPU; these feature heads do not require model parallelism.
4. Compare complete frozen runs with the official full-test protocol and a strong released checkpoint. Preserve the old exposed 69-query subset label, and report remaining unseen-query diagnostics separately. Select no new settings from test scores. Prove: source/model/code hashes, complete predictions, R@1 at IoU 0.3/0.5/0.7, mean IoU, video-group confidence intervals, training and inference cost.
5. Next conditional experiments: dense frame plus motion fusion; local Yes/No-logit refinement; verified negative-aware calibration. Implement only when the first error analysis supports the cost. Check refined TimeLens boundaries as a separate protocol, then long-video/corpus cases. These are hypotheses, not novelty or SOTA claims.

Sol policy: course account class_cse59889474fall2026, class QoS. Verified current limits: two running jobs, 10 submitted, four GPUs/job, 32 CPUs/job, 320GB RAM/job, 960 GPU running minutes/user, 24-hour wall maximum. Two unrelated user jobs already exist; do not change or cancel them. Use checkpointed jobs within the actual shared limit. Once a long run starts, report job ID, expected duration, checkpoint/log paths and status command, then leave it running for the user to check. Do not keep tailing it.

Questions: none required to begin these approved experiments. A benchmark win cannot be promised. Stop and re-plan after two failures on one step; retain the error evidence.

### First evidence and operational re-plan

Score-curve selection and all 69 evaluation queries are complete, with zero new model calls. R1@.5 is 43.48% versus 42.03%; mean IoU 40.66% versus 35.89%. The recall confidence interval includes zero. Report all six conditions and the IoU .3 loss; do not tune again on these scores. Aggregate: evaluation/caption-curve-pilot-results.json.

Sol preparation 1480741 completed 0:0 in 8m7s. Full author train metadata passes strict validation; source-disjoint split is 11,116 train / 1,288 validation queries. Record the distinct processed-label release, not just a four-row discrepancy: 24 training and seven test strings differ as well. Boundary equivalence remains unproved.

Smoke 1484086 failed before training because the container lacks Git. Driver v2 uses pinned runtime-file hashes instead. TEF parse and recoverable epoch journal are tested. A retry submission using the already purged preparation dependency was rejected with no job created. Revised launch: verify completed preparation in accounting, submit fresh short smoke without that stale dependency, then use its measured speed before the eight-hour training job. Failed logs/protocol stay intact. First model-enabled Docker regression: 451 passed, one skipped (private upstream checkout absent), two existing warnings. Final v2 regression follows source changes.

### Stop and re-plan: complete the epoch gate before another long job

V2 smoke 1485684 passed both 20-step variants on an A100-SXM4-80GB: baseline 0.05987s/step, quality 0.04837s/step; peak allocated 2.35GiB. Its batch-only projection is 3.14h for all six 100-epoch runs. V2 full Docker regression passed 452 tests, two skipped private-checkout checks (both passed separately on the host), two existing warnings.

Long job 1486462 failed 1:0 after 70 seconds in first development scoring. No successful epoch checkpoint was written. The first smoke did not exercise validation. Exact CPU reproduction: duration 30.38035 clamps through float32 to 30.38035011291504, then the author's 4dp output becomes 30.3804; the validator wrongly uses double-duration 4dp 30.3803. Three development queries have that duration. Preserve predictions and author postprocessing; validate against the same float32+4dp endpoint envelope. Values beyond that envelope and non-finite values still raise, with detailed context.

Do not submit another long run yet. Driver v3 smoke must complete 20 training steps, all 1,288 development queries and full-state checkpoint save/load for each condition. Unit tests reproduce the rounding failure and reject a larger endpoint. Keep old protocols, logs and launches. New output namespace: runs/strict-head-v3. Only after this complete gate passes, launch the six-run job and leave it for the user to check. No official-test scores select this fix or configuration.

### V3 accepted; handoff for the long run

Gate 1487482 completed 0:0: both conditions passed 20 training steps, all 1,288 validation queries and full-state checkpoint round trip. About 0.05s/step, 2.35GiB peak allocation on A100-SXM4-80GB. Batch+validation projection 3.05h for all six runs; expected wall 4–7h with startup and checkpoints. Final v3 Docker regression: 454 passed, two skipped private-checkout tests, two existing warnings; private tests pass separately on host. Independent review has no blocker after the live gate.

Submitted long job **1488158**, one A100, four CPUs, 32GB host RAM, eight-hour wall, course account/class QoS. Script forwards the allocated GPU mask into Apptainer. Source hashes and launch/smoke evidence are in ignored .codex-backups/outperform-20261114/v3-training-launch.json. Do not edit those sources mid-run or keep tailing this job.

User check: `sacct -j 1488158 --format=JobID,State,ExitCode,Elapsed` on Sol. Log: /scratch/psheta12/video-search-temporal-20261114/logs/train-1488158.log. Run root: /scratch/psheta12/video-search-temporal-20261114/runs/strict-head-v3. On completion, verify all six histories/checkpoints and frozen source/data/split identities. Then run full author-test comparisons against the released reference and each trained condition, with video-group intervals and three-seed variability. Keep canonical-label and processed-release protocols separate. Full benchmark gains and novelty/SOTA remain unproved.

Final one-time start check: job 1488158 is RUNNING on sg040. Baseline seed 2018 completed epoch 1 (348 batches and all 1,288 development queries); mean train loss is finite. Both latest.pt and best.pt exist at about 498MiB each. Epoch compute/validation was 23.09s. Launch source hashes still match; instructions above Lessons are byte-identical to the backup. Test database stopped; app/database/worker remain healthy. Leave the job running now. No further monitoring in this turn.


### Follow-up status check — 14 November 2026

Job 1488158 remains RUNNING, observed elapsed 2h44m. Three runs completed100epochs: baseline2018,quality2018,baseline2019. Quality2019 reached61/100; both2020runs await their turn. Complete ordered histories checked:361/600epochs overall. Completed seed2018 best train-only validation R1@.5:baseline61.96%,quality62.89% (+0.93points). These are validation scores, not full-test results. Expected remaining roughly1.5–2h at current pace. One squeue configuration request timed out; sacct and live histories independently confirmed progress. No source/model changes or new jobs. Leave running; evaluate full test only after all six complete.

### Training complete; frozen full-test comparison

Job1488158 COMPLETED0:0 in4h35m4s. All six ordered100-epoch histories, checkpoint existence and no pending commits verified. Data, train/development split and training-source hashes match across all runs. Validation-selected epochs: baseline2018=20,quality2018=37,baseline2019=31,quality2019=26,baseline2020=32,quality2020=24. No test-based model selection.

Review found batch-padding dependence in the unchanged author model: two extra masked steps changed valid outputs in an actual model CPU check. Author opt.json uses evaluation batch4; our original driver uses32. Freeze before any full-test predictions: run all six trained models and released reference at32, plus a separate released-reference batch4 reproduction check. Explicit batch-size/timing fields enter a new evaluation-driver hash; trained source/checkpoints stay frozen. Validate3720queries/1334videos, all grid members, checkpoint/config/source/data hashes and metric recomputation. Report paired seed/video confidence intervals and all seeds, not just a winner. Processed author labels remain separate from canonical/TimeLens protocols.


### Full-test decision and SDST reference preparation - 15 November 2026

Completed: training1488158 and evaluation1527713 both exited0. Full3720-query test: baseline three-seed mean R1@.5=60.04%, quality=58.80%; released native reference=60.19%. Reject quality loss. See evaluation/trained-temporal-full-test-results.json. No benchmark win.

Approved continuation, isolated from app and frozen runs:
1. Verify SDST preparation code, source/checkpoint identity and real complete-response headers. Proof: focused tests, independent review, bounded header probe, host-generated tracked-source hashes.
2. Prepare Charades features with one CPU job. Proof: immutable full archive, exact directory/labels, every CRC and finite NPZ shape, complete query/source coverage. Reserve100GiB for retained failures.
3. Prepare pinned Torch2.2.1/CUDA12.1 runtime with a separate CPU job. Proof: SIF hash, package manifest and import checks. OpenCV OS-library needs remain uncertain; fail explicitly.
4. After both preparations pass, run a short A100 build/numeric/checkpoint/feature gate. No training before all gate stages pass.

Changes reach research-only preparation scripts/tests, Docker test inputs and handoff docs. Existing app/indexes and six frozen runs stay intact. Long preparation jobs must be reported and left running. Questions: none needed within the approved campaign.


Initial SDST launches: data1608962 FAILED1:0 in36seconds beforearchivebytes; a second HTML page appeared afterGoogleconfirmation onSol. Three boundedHTTPattempts retained failure manifests, no publisheddata. Local boundedprobe previouslypassed; inspect the Sol response before retrying. Independent runtime1609074 submitted:CPU4/16GiB/2h, noGPU. Estimate20-60minutes dependsimage/network; leave longworkrunning. Sourcehashes andlogs: .codex-backups/sdst-launch-20261115.


### Stop and re-plan: artifact network access

Data1608962: bounded same-SIF reproduction proves a Google Drive quota page (HTTP200, text/html2040bytes), not an archive/parser size bug. Keep exact content/length/directory/CRC/tensor checks. Author README only lists Google Drive; reviewed author issue1 requests Hugging Face hosting and offers no alternate artifact. No mirror is verified.

Runtime1609074 FAILED255:0 in25seconds and1609248 FAILED255:0 in17seconds: Docker registry TLS handshake timeout before image layers. Two failures on this step: STOP further identical build submissions. Preserve both logs. Diagnose endpoint/transport access and write a new plan before another runtime launch.

Next independent transport: a bounded local data probe previously succeeded. F:/codex-private/video-search-sdst-20261115 has509GB free, enough for the100GiB failed-stream reserve. If the new local probe passes, download one complete unchanged archive, verify with the existing frozen helper, transfer into unique names onSol, publish exclusively, and submit existing CPU data validation. No weak-ETag range assembly, feature replacement or skipped queries. This explicit transport change does not change dataset semantics. Persist local process/state/log and later Sol job ID.

Verification now complete: Docker model-enabled518passed,2private-checkoutskips,2existingwarnings,182.66seconds; both skipped tests passed separately onhost7.43seconds. Test database stopped. No application source/default/index change. Frozen training/evaluation sourceSHA256 values still match.


### Revised network plan: exact-image mirror and one delayed data retry

The local Windows data probe now also returns the quota page. The private transport runner stopped before a full download, transfer or background job. It compiled and passed its self-check; full transport is unrun. Keep F: empty of archive data. Google says access may take up to24hours; schedule one CPU data retry after24hours, not a polling loop. Retain all original checks and log the new job ID.

Runtime explorer verified fromSol login05: originalDocker registry401/auth200, while compute Apptainer had timed out. Root cause of that compute/client-path difference remains unknown. Explicitly change only the source registry to mirror.gcr.io/pytorch/pytorch at the SAME SHA25642204bca460bb77cbd524577618e1723ad474e5d77cc51f94037fffbc2c88c6f. Mirror manifest and config SHA values match the original; all16layerHEAD requests return200 and exact manifest lengths. No layer payloads were fetched by the probe. This is a new tested transport plan, not a third identical submission or an automatic fallback. Back up old wrappers/helper, run focused identity tests and shell syntax, verify uploaded hashes, submit one CPU preparation and leave it running. An image/CPU import pass still does not prove the GPU/model path.


### Current handoff - new plan submitted

Runtime job1609446 uses the exact-digest Google mirror. CPU4/16GiB/2h; estimate20-60minutes, not measured. Data job1609447 is delayed with --begin=now+1day, to allow the Google quota to clear. It uses the existing frozen data script, CPU4/16GiB/2h; estimate30-90minutes after eligibility, unmeasured. Neither job uses a GPU. The quota may still block the delayed attempt. No automatic job retry loop.

Check onSol: sacct -j1609446,1609447 --format=JobID,State,ExitCode,Elapsed. Logs: /scratch/psheta12/video-search-sdst-20261115/logs/runtime-1609446.log and prepare-1609447.log. Reports required before a model gate: runtime/runtime.json, runtime/files.json, runtime-images/image.sha256 and preparation.json. Private revised-launch.json stores source hashes. Do not edit submitted sources or keep tailing these jobs. No training before complete CPU preparation and the allocated GPU gate.

The later local data probe also hit quota. No download, transfer or local background process is running. Private transport self-check and compile passed; full transport is untested. Full Docker regression passed518/2private-checkoutskips/2existingwarnings before the mirror-host-only change; both skips passed onhost. Four focused runtime tests passed after that source-URI change.


One-time start check: runtime1609446 RUNNING after1m2s, started15November14:09:24 America/Phoenix, at OCI fetch stage. Data1609447 PENDING with delayed eligibility, startUnknown. Neither state is a completed preparation pass. Leave jobs now; no further monitoring this turn. After completion, verify immutable reports and import checks, then implement/run the short A100 gate before training.

### Sol check, runtime fix and new submission — 19 November 2026

Checked both jobs on Sol by read-only sacct and log reads. Runtime 1609446 FAILED 1:0 after 17:01: the mirror route worked (9.0 GB SIF built, image.sha256 saved, all pinned packages plus CLIP installed), and the failure is the documented missing OS library — importing cv2 requires libGL.so.1, absent from the pinned Torch 2.2.1 image. Data retry 1609447 FAILED 1:0 after 21 seconds: Google returned the same 2,040-byte quota page on all three attempts; the 24-hour delay did not clear it. Failure manifests stay on scratch. Neither job used a GPU.

Approved and implemented: opencv-python-headless==4.9.0.80 replaces opencv-python in scripts/sol/prepare_sdst_runtime.py; no other pin, image or CLIP commit changed. PyPI confirms the headless pin exists (Linux x86-64 wheel). Four focused runtime tests passed in Docker after the change; test-db stopped after the run. Remote source identity was verified before upload (f174a63... matched the launch record) and after upload (dd7b34f28ce8cd9d3175e03bc789e107244615b36f59ab159a4f094b42834ce2). Job 2067143 was submitted without the log convention and was cancelled while pending (no compute used); job 2067147 is the same submission with logs/runtime-%j.log.

New job: 2067147, CPU only, fresh stage, reuses and re-verifies the existing SIF. Check: sacct -j 2067147 --format=JobID,State,ExitCode,Elapsed. Log: /scratch/psheta12/video-search-sdst-20261115/logs/runtime-2067147.log. Reports required before any GPU gate: runtime/runtime.json, runtime/files.json, runtime-images/image.sha256. Leave the job running; do not tail it.

Data path: open. Google Drive remains the only verified host of the 27.3 GB SDST archive, and its per-file traffic quota blocked every attempt from Sol and locally. No retry loop. The user has not yet chosen the next data route (longer delayed retry, author mirror request, alternate reference, or pause).

## Side task — scheduled ENTER sender, 20 November 2026 (approved, complete)

User request: a program that presses ENTER in a chosen app window at a set time, for a message typed in advance when the app has no scheduled send. Tool lives outside this repo at `D:\projects\send-enter\`; no video-project code was touched. Python with ctypes only; no new dependencies.

Steps, each with its proof (all done):

1. Time input, both forms — `--at` clock (a past time asks before moving to tomorrow) and `--in` countdown. Proof: `--help`; `0m` and `25:00` rejected; past `--at` answered "n" aborts with "no ENTER was sent", exit 1.
2. Window match by title part; console and cloaked windows skipped; exact title preferred. Proof: `--list` returned exactly one match, "Untitled - Notepad".
3. Send-time behavior: find again, restore, focus, verify the foreground window, then one ENTER; any failure sends no key; system sleep blocked while waiting. Proof: real run `--in 6s` — window found, focused, "ENTER sent" at the target second. One bug fixed on first retry: SetThreadExecutionState is a kernel32 export, not user32.
4. Honest limits given: PC on and unlocked, terminal left open, hands off the keyboard at send time.
5. Live test on the OpenCode desktop app, 20 November 2026 ~01:06: armed `--in 2m` against "Scheduled keyboard Enter sender — OpenCode"; the log proves focus and ENTER at 01:06:01; the user's "hi got the msg?" arrived as the next turn after the fire. One finder change was required and made for this test: terminal windows are valid targets (only the tool's own console is skipped). End-to-end proof completes when the user confirms that text was the unsubmitted input-box content.
6. Title-mutation failure and fix, 20 November 2026: the 01:50 clock-time run refused to send (log: no window matches the arm-time title; OpenCode had renamed the same window, hwnd unchanged). Fix, user-approved: pin the handle at arm time, use it at send time while alive, fall back to title search only if the pinned window is gone. Proof: reproduced the failure on a sacrificial window renamed mid-countdown from "PinTestWindow-1234" to "PinTestWindow-9999" — the tool used the pinned handle, focused the renamed window, and the window's own keydown log recorded "ENTER received 07:49:19.339" at the fire second. Re-arm for the real payload is on hold for the user's word.
