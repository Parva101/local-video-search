# Stage 7 — untouched benchmark evaluation, frozen design

Author: benchmark design engineer (role 37, see `TEAM.md`). Date: 2026-11-20.
Status: design only. Nothing was run for this document. One file, one lane.

This document freezes the protocol for the last stage of the 19 November mandate
(`PLAN.md`, master plan, stage 7: "Untouched Charades-STA selection plus
negative/long-video cases; frozen protocol; one-shot evaluation"). A future
session can execute it verbatim. The integrator freezes it by recording the
file hash in `DECISIONS.md` (see the Freeze record at the end).

## 0. Honesty note on the word "untouched"

The 69 test queries were run before. The record says so and forbids calling
their numbers "untouched held-out" (`DECISIONS.md`, "Explicit point evidence
after incomplete frozen baseline": "Original test exposure is disclosed; new
numbers cannot be called untouched heldout or SOTA";
`evaluation/charades-point-aware-pilot-results.json`, limits:
"Exploratory after prior test-input/protocol exposure").

What was never done, and what this protocol therefore claims as untouched:

- No method was selected or tuned using test scores. The pre-test designs state
  "it does not use test results to choose a method" and "No held-out prediction
  or GT-driven quality tuning" (`DECISIONS.md`, extent v3/v4/v5 sections). The
  one product decision the test results influenced was negative: keep the
  default description path and leave extent inspection experimental
  (`DECISIONS.md`, "Final measured decision: no general benchmark win").
- The acceptance thresholds, the negatives, the protocol and the one-shot rule
  in this document are fixed before any stage-7 inference.

So the claim wording below never says "untouched held-out test". It says
"one-shot, frozen-protocol evaluation with pre-declared thresholds on the
licensed pilot test selection plus newly authored negatives". That is the
strongest claim the record supports.

## 1. Purpose and the exact claim target

Goal: measure whether the delivered local pipeline, with the pinned fine-tuned
adapter, is best in class **among the systems we can honestly compare it
with** — and only those. The claim target is the mandate's own wording: "best
in class among local pinned systems for this pipeline" (`DECISIONS.md`,
"Fine-tuned system model campaign"; `PLAN.md`, fine-tune campaign step 5).

This evaluation produces one report with costs and confidence intervals,
comparison class named (`PLAN.md`, stage 7 proof column). It runs once. A fail
is reported as a fail.

## 2. Comparison class, stated honestly

### 2.1 Systems under test (the class)

All arms run the same product pipeline end to end: description index, dense +
lexical retrieval, local rerank, source-check verification. They differ only
in the system model (the description generator and the verifier).

| Arm | System model | Pinned? | Supervision we gave it |
| --- | --- | --- | --- |
| H — hosted teacher | `gemma4-31b-it` via the hosted ASU endpoint (identity `vllm-0.26.0-tp4-24487d56` recorded in the pilot) | No — hosted, unpinned. Disclosed limit, unchanged from the pilot. | None from us. Unknown pretraining exposure to public Charades. |
| B — pinned zero-shot base | `Qwen/Qwen3-VL-4B-Instruct` @ `ebb281ec70b05090aa6165b016eac8ec08e71b17` (`evaluation/finetune-adapter-eval-v2.json`, run block) | Yes — checkpoint manifest `base-model-manifest.json` (Sol prep job 2068865, `PLAN.md`). | None from us. The reproducible zero-shot baseline. |
| A — pinned adapter | Arm B plus the LoRA adapter that has a recorded acceptance pass. Identity pinned at run time: base revision + adapter safetensors SHA-256 (first adapter: `c5268e8127a3a3cbe6e122e96307996359b7d07a5f416d6c6071ce68e50135d1`, `evaluation/finetune-adapter-eval-v2.json`). If the scaled retrain (job 2126197, hard-negative 364-row dataset) passes its acceptance eval, that newer adapter is arm A; its hash is recorded before inference. | Yes. | Production-trace distillation plus Charades-STA pilot windows: in-interval positives and same-video out-of-interval hard negatives (`DECISIONS.md`, fine-tune campaign section; `PLAN.md`, dataset scale-up). **This is why section 3.3 exists.** |

The adapter is not called "zero-shot". It is task-adapted by us, on our
production contracts and on pilot footage windows. It stays in the class
because it runs the product pipeline at fixed budgets and it is not a
benchmark-metric-trained specialist. Arm B exists to isolate what the adapter
actually adds (A vs B), and arm H is the teacher the product ships with today
(A vs H).

### 2.2 Excluded from the class, on purpose

- **Supervised Charades-STA specialists** (UniVTG, SDST, Moment-DETR,
  FlashVTG, TALL-family). They train on the benchmark's own train split with
  its scoring objective. The record rejects conflating those numbers with our
  pilot (`DECISIONS.md`, 14 November section: "Do not mix their label
  protocols or claim that published full-test numbers are comparable to our
  old 69-query pilot"; mandate section: "Any SOTA wording must name its
  comparison class"). Context only, for scale: our supervised UniVTG
  reproduction reached 60.04% mean R@1 IoU 0.5 on full test; the released
  reference is 60.19% (`evaluation/trained-temporal-full-test-results.json`;
  `DECISIONS.md`, "Reject the first trained adaptation after complete test").
  No number in that family appears in our result tables except this quoted
  context sentence.
- **The published numbers of any paper.** We compare only systems we ran
  ourselves, under one protocol.
- Any claim about the 60% family being beaten or matched by our pipeline. The
  product path is a different task class: evidence retrieval plus honest
  verification, with abstention, not specialist grounding.

## 3. Data

### 3.1 Positive set — the licensed pilot test split, frozen as-is

- The 69 queries over 25 test videos of the licensed private Charades-STA
  pilot, selection rule already frozen:
  "Ascending SHA256(local-video-search-charades-pilot-v1:{split}:{video_id});
  20 train and 25 test videos, all selected queries."
  (`evaluation/charades-point-aware-pilot-results.json`, data block:
  annotation hashes, revision `3793c625f2e251a5f19a0d59f0c83b12e386f808`,
  test annotation hash `fab341679c20b0917173dcffffde367a71113fe63af3a645558cef2ebfbfefb55`,
  clips 16.7–42.8 s).
- No query is added, removed or rewritten. The query list and its annotation
  hash are copied into the run manifest before the first call.
- Media and labels stay private and licensed
  (`evaluation/charades-point-aware-pilot-results.json`, license_note). Public
  artifacts carry hashes and aggregates only.

### 3.2 Negative set — 20 new no-match queries

The mandate asks for at least 20 no-match queries written from footage review,
never used for tuning (`PLAN.md`, stage 7; task order for this design). This
protocol freezes **exactly 20**, because the count, the video assignment and
the cost arithmetic must all be fixed before the run.

Rules, fixed before any authoring run:

1. **One negative per test video**, on the first 20 test videos in the frozen
   pilot selection order. The assignment is deterministic; the author picks
   videos from no list.
2. **Absence is confirmed by human review of the actual footage** (watching
   the clip or its frame samples). Model descriptions may not be used as the
   source of truth for absence.
3. **Plausible in-domain queries.** Each query names an action, object or
   person type that fits the Charades domain (indoor amateur activities) but
   does not occur in that video. A trivially rejectable query ("a submarine
   in the kitchen") is not allowed.
4. **No overlap with the positive queries' targets in the same video.** If a
   video's positive queries mention "holds a book", the negative for that
   video may not be a near-copy with a negation.
5. **Never sent to any model before the stage-7 run.** No drafting probes, no
   tuning. The author records, per negative: query text (max 1000 characters,
   the API limit in `src/video_search/api.py`), target video ID, and a
   one-line absence justification with the timestamps checked.
6. The negatives manifest (20 entries plus author and date) is hashed into
   the run manifest and stays private under `.codex-backups/` (it is derived
   from licensed footage review). Public artifacts publish the hash, the
   count and aggregate results only.
7. Disclosure: the author team also built the system, so the negatives are
   adversarial, not random. The false-match rate measured on them is an
   upper-bound stress, not an average-case rate. This sentence is copied into
   the results report.

### 3.3 Contamination audit — gate before any inference

The adapter's training set includes Charades-STA pilot windows: "186 windows
over 45 different scenes" was the supervision target (`PLAN.md`, dataset
scale-up), and the pilot has 45 videos, 20 development plus 25 test. If
adapter training windows include test-video frames, then the adapter has seen
the evaluation footage in training, and the A-vs-H comparison on those
queries is leaked by our own hand. The hosted teacher's unknown pretraining
exposure we cannot fix; our own exposure we must check.

Gate, run before any stage-7 inference:

- Read the adapter training manifests (the merged 364/196 dataset manifest
  and the hard-negative builder output; hashes recorded in `PLAN.md`, dataset
  scale-up and wave-1 sections; files under `.codex-backups/finetune-data/`
  and on Sol). List every Charades video ID that appears in any training
  row. Compare against the 25 test video IDs.
- Pre-declared outcome mapping:
  - **0 test videos in adapter training:** the full 69-query set carries the
    primary claim.
  - **Overlap, but at least 15 of 25 test videos are clean:** the clean
    subset carries the primary claim (same rate thresholds, its own
    video-grouped bootstrap, wider intervals disclosed). Full-69 numbers are
    reported in a separate table labelled "adapter training exposure
    disclosed".
  - **Fewer than 15 clean videos:** the run still happens once, but no
    adapter superlative claim is available. Arm A results are reported with a
    train-exposure label; the H-vs-B comparison stands on its own.
- The audit result is written into the run manifest before the first call. It
  is a gate, not a tuning step: it selects a claim path that this document
  already defines; it does not change any threshold, budget or query.

### 3.4 Out of this protocol's scope, on purpose

- **Long-video cases.** The master plan names them for stage 7
  (`PLAN.md`, stage 7 row), but the licensed pilot clips are 16.7–42.8 s, and
  adding long-video media would require a new licensed selection and a second
  cost ledger. Long-footage behavior is already exercised by the stage-6 real
  end-to-end campaign (`PLAN.md`, stage 6; `evaluation/` browser proofs). If
  the integrator wants a frozen long-video one-shot, that is a separate
  protocol document. This deviation is surfaced, not hidden.
- **Speech, counting, reference-image queries.** Section 5 states why.

## 4. Arms, identity pins and serving

Identity recorded in the run manifest before the first inference call:

- App source: per-file SHA-256 list, same practice as the pilot
  (`evaluation/charades-point-aware-pilot-results.json`, protocol block).
- Retrieval pins: MiniLM text encoder, SigLIP2 window space
  (`unit-sum-text-image-l2-v1`, `PLAN.md`, stage 1), reranker
  `cross-encoder/ms-marco-MiniLM-L6-v2` @
  `233902d25c440f23af6d7d6e94d2946bac0bee0a` (pilot protocol block).
- Prompt specs: the app's current description and verification specs, version
  strings copied into the manifest. The adapter was trained on these
  contracts (`DECISIONS.md`, fine-tune campaign). No spec changes between
  arms.
- Arm H: the hosted endpoint's reported model identity plus a fingerprint
  probe. Unpinned status is a disclosed limit
  (`evaluation/charades-point-aware-pilot-results.json`, model_limit).
- Arms B and A: base checkpoint files re-verified against
  `base-model-manifest.json`; adapter safetensors SHA-256 recomputed and
  matched against the recorded acceptance-eval manifest
  (`evaluation/finetune-adapter-eval-v2.json` for the first adapter; the
  newer eval report on Sol for the scaled retrain). A mismatch stops the
  run before it starts. No silent substitution.
- Arms B and A are served through the app's existing OpenAI-compatible client
  (vLLM on Sol, as proved by job 589241, or locally). Serving location does
  not change the claim: the weights are the pinned artifact. Any Sol serving
  job is added to `.codex-backups/sol-monitor/watch.json` per `AGENTS.md`
  item 7.
- Arm A eligibility: the adapter must have a recorded acceptance pass
  (serving-contract gate, `evaluation/finetune-adapter-eval-v2.json` shape).
  If no adapter has passed by run time, arms H and B run and the claim is
  scoped to what ran; the report says so.

## 5. Protocol — what runs per query

### 5.1 Primary path (all arms, all queries)

`POST /evidence-search` (`src/video_search/api.py`,
`EvidenceSearchRequest`: limit default 12, range 1–24; `max_checks` range
1–6), one request per query:

```json
{
  "query": "<the frozen query text>",
  "recording_ids": ["<this query's test video>"],
  "path": "description",
  "rerank": true,
  "limit": 12,
  "max_checks": 2
}
```

- Supplied-video task, as in the pilot (`"task": "supplied-video temporal
  grounding"`). The corpus/all-videos mode is not measured here.
- Budget frozen at the pilot's evaluation cap: **2 source checks, 8 frames
  per check, 16 sent frame slots per query** (pilot `configured_cap`
  `max_checks: 2, max_frames: 16`; frame-per-check confirmed by the app
  tests, `tests/test_benchmark_compare.py`). `limit` 12 candidates,
  reranked.
- Predictions: the top model-supported interval in controller order.
  Point-only and null-only answers are abstentions with zero IoU; raw
  judgments are preserved, never repaired (pilot `prediction_protocol` and
  `localization_rule`).
- Negatives run through the same request shape on their target videos.

### 5.2 Secondary diagnostics (no hosted-attempt cost)

- Retrieval-only rankings for every query and arm: raw vs reranked R@1/mIoU
  from the same run's candidate pools, reported like the pilot's
  `retrieval` blocks (`evaluation/charades-point-aware-pilot-results.json`,
  results.evaluation.retrieval). Zero model calls.
- Visual path retrieval ranking: build local SigLIP2 visual indexes for the
  25 test videos (local compute only, no model-service attempts), then
  `POST /search` with `path: "visual"`, retrieval-only, no source checks.
  This shows what the description path adds over pure visual similarity.
  Verification-stage cost stays with the primary path.

### 5.3 Paths not run, and why

- **Speech path: not applicable.** The pilot footage has no transcript
  builds, and Charades-STA queries describe actions, not spoken topics.
  Forcing Whisper (`openai/whisper-base` @
  `e37978b90ca9030d5170a5c07aadb050351a65bb`, `DECISIONS.md`, speech
  section) onto this footage would test ASR, not the claim. The speech
  capability keeps its own proof
  (`evaluation/speech-search-e2e-results.json`) and its experimental label.
- **`/count-events`: out of scope.** Different task class, budget-bounded and
  experimental (`DECISIONS.md`, scoped occurrence counting; task order for
  this design). Its proof stays
  (`evaluation/event-counting-e2e-results.json`).
- **Reference-image (hybrid) queries: out of scope.** Charades-STA ships text
  queries only. The image-query capability keeps its own proof
  (`evaluation/image-query-e2e-results.json`).

### 5.4 Index builds and run order

- Each arm builds a **fresh description index** over the 25 test videos with
  its own generator, under the run manifest's identity. The pilot's old
  hosted index is not reused: no mixed-generation-policy builds
  (`PLAN.md`, upload-fix rule 3: "no mixed-policy reuse is proposed"). The
  old indexes stay on disk untouched.
- Visual indexes (local) are built once and shared by all arms.
- Query order inside each arm: fixed, derived from the declared order seed
  `untouched-stage7-order-v1` over the frozen query list. Arms run
  sequentially: index build, 69 positives, 20 negatives. The durable ledger
  enforces the cap at every call.

## 6. Pre-run gates (all before the first inference call)

| Gate | Check | Stop condition |
| --- | --- | --- |
| G1 | This document is frozen: integrator records its SHA-256 in `DECISIONS.md`. | No freeze record, no run. |
| G2 | Adapter/base identity: manifest hashes recomputed, matched against the acceptance-eval record. | Any mismatch stops before start. |
| G3 | Contamination audit (section 3.3); claim path selected and written into the run manifest. | No audit, no run. |
| G4 | Negatives manifest complete: 20 entries, deterministic video assignment, hashed. | Shortfall recorded honestly with the reason; thresholds apply to the actual count, disclosed. |
| G5 | Fresh private ledger file created, cap 1,000, gateway enforcement on (the pilot's durable-ledger mechanism, `DECISIONS.md`, approved slice). | Ledger not fresh, no run. |
| G6 | One serving-chain probe per arm (budget 6 attempts total). | Probe failure: fix the cause under the two-failure rule before any query. |
| G7 | Any Sol serving job added to the monitor watch list (`AGENTS.md` item 7). | Long job unwatched, no run. |

## 7. Metrics and pre-declared acceptance thresholds

All thresholds below are fixed now, before any run. They are rates. The
69-query arithmetic is shown as the default case; on a contamination-clean
subset the same rates apply with that subset's own intervals.

### 7.1 Metrics (per arm)

- **R@1 at IoU 0.3 / 0.5 / 0.7 and mean top-1 IoU**, VSLNet-compatible:
  target `max(0, start)`, `min(raw_end, reference_duration)`, raw labels
  preserved; points are evidence, not intervals; point-only answers abstain
  with zero IoU (pilot `comparison_notes` and `primary_metrics`).
- **Video-grouped bootstrap 95% intervals**: resample whole videos with their
  queries, 2,000 repetitions, seed `20261120`, small-group warning retained
  (pilot used the same design, seed 20261108, `bootstrap_repetitions: 2000`).
- **Paired deltas** on shared queries: A−H and A−B (and B−H, reported), with
  the same video-grouped bootstrap.
- **Abstention and failure accounting**: abstention rate, invalid-reply rate,
  HTTP errors, retries, unresolved cases — per arm, reported as measured,
  never repaired.
- **Negatives**: false-match rate (a "match" status with a nonzero interval
  on a no-match query is a false match); honest-refusal rate (no_match,
  insufficient_evidence or empty candidates count as honest refusals, not
  failures).
- **Cost per arm**: index attempts, verification attempts, logical calls,
  HTTP attempts, sent frame slots, unique frames, p50/p95 source-check
  latency, provider-reported tokens (hosted arm) or local generation tokens
  (pinned arms), plus serving-wall-time notes.

### 7.2 Acceptance thresholds (pre-declared)

Anchors from the record, so no number below is wishful: on the same 69
queries, same 2-check/16-slot budget, the hosted teacher's strict product-like
path scored R@1 IoU 0.3 = 15.94%, R@1 IoU 0.5 = 1.45%, mean IoU 8.92%, with
65.2% abstention; retrieval-only reranked reached R@1 IoU 0.3 = 65.22%,
IoU 0.5 = 42.03%, mean IoU 35.89% (`evaluation/charades-point-aware-pilot-results.json`,
conditions `ranked_fixed`, retrieval blocks). The first adapter's
serving-contract pass is 100% schema validity on held-out rows
(`evaluation/finetune-adapter-eval-v2.json`). With 69 queries, one query is
1.45 percentage points.

| ID | Threshold (fixed) | Failing means |
| --- | --- | --- |
| T1 | Per-arm invalid-reply rate ≤ 5% of completed attempts. | The arm's serving contract is not stable; disclose, no repair. |
| T2 | Claim arm reaches R@1 IoU 0.3 ≥ 15.9% (≥ 11 of 69, or the same rate on the clean subset). Anchor: the hosted strict path's own 15.94%. | No superlative claim for anyone: the strict verification path is not functional on this domain yet. Report as the honest baseline. |
| T3 | Non-inferiority vs hosted: paired A−H delta on R@1 IoU 0.5 has video-grouped 95% CI lower bound ≥ −4.35 points (−3 queries). | The adapter did not match the hosted teacher. Hosted path stays default (`DECISIONS.md`, campaign rule). |
| T4 | Superiority over the pinned base: paired A−B delta on R@1 IoU 0.5 has 95% CI lower bound > 0. | The fine-tune's local benefit is not demonstrated; the claim shrinks (see wording map). |
| T5 | Claim arm false-match rate on the 20 negatives ≤ 20% (≤ 4 of 20). | The system asserts events that are not in the footage too often; no best-in-class wording. |
| T6 | Cost reported per arm; no rerun for cost reasons. If the claim arm's per-query wall cost exceeds the hosted arm's by more than 2×, the claim wording must say so. | Cost honesty is wording, not a gate. |

### 7.3 Claim wording map (pre-declared — the report uses these sentences)

- **T1–T5 all pass** (T4 included): "On this one-shot frozen-protocol
  evaluation, at fixed budgets, on 69 licensed Charades-STA pilot test
  queries plus 20 reviewed no-match queries, the pinned local adapter
  pipeline matched or beat the hosted teacher [CI] and beat its own pinned
  zero-shot base [CI]. Among the compared local pinned systems for this
  pipeline, it is best in class. Cost: [table]."
- **T1, T2, T3, T5 pass; T4 fails**: "The pinned adapter matches the hosted
  teacher [CI]. The gain over its own pinned base was not demonstrated on
  this set. No best-in-class wording."
- **T3 fails**: "The pinned adapter did not match the hosted teacher on this
  evaluation [CI]. The hosted path stays the default." Negative result
  recorded, as the campaign rule already promises.
- **T2 fails**: no superlative from any arm; the report stands as the honest
  strict-verification baseline on this domain.
- **Contamination path 3.3, few clean videos**: arm A numbers carry the
  train-exposure label; the claim, if any, comes from H vs B only.

## 8. Cost ledger and the one-shot rule

### 8.1 How attempts are counted

Same mechanism as the pilot: a durable private ledger, one row per real
upstream model call, retries charged, indexing calls charged, no retry path
around the cap (`DECISIONS.md`, approved slice; pilot cost block:
`global_unique_external_attempts: 1460`, `hard_attempt_cap: 1500`). For
symmetry, local-arm generation calls (arms B and A) count as attempts too,
one per real call; local compute, tokens and latency are reported separately.

Pilot history, kept honest: 1,460 of 1,500 spent across five protocol
revisions, an audited cache migration and the final 414-request evaluation
(`evaluation/charades-point-aware-pilot-results.json`, cost block;
`DECISIONS.md`, cache-migration section: "Costs across protocols overlap and
must not be added twice").

### 8.2 The new cap: 1,000, and the arithmetic

- Index builds: the pilot recorded 186 attempts over 45 videos ≈ 4.13 per
  video → 25 test videos ≈ 104 per arm.
- Verification: 69 positives × 2 checks = 138 per arm.
- Negatives: 20 × 2 checks = 40 per arm.
- Per arm 282; three arms = 846.
- Probes (G6): 6.
- Retry headroom at 15%: ≈ 127.
- Worst case ≈ 979. **Cap: 1,000.**

Why not the pilot's 1,500: that overage came from protocol evolution (five
extent versions plus a cache migration), which the one-shot rule forbids
here; there is no development grid and no ablation ladder in this protocol.
Why not lower: the hosted arm's unpinned service needs retry headroom, and a
cap hit must remain unlikely enough that a partial report is the exception,
not the plan.

If the ledger hits the cap before completion: stop, report partial results
with the incomplete state disclosed, and downgrade the claim to what
completed. No cap raise.

### 8.3 The one-shot rule

- The campaign runs once. No query is re-run for a better answer.
- Infrastructure failures (Sol outage, network) may resume: identical
  protocol, append-only ledger, only unanswered queries repeated. The
  Sol-SSH outage during the fine-tune campaign proves resumption must be
  allowed (`PLAN.md`, attempt-5 entry).
- Model-level failures (invalid replies, wrong statuses) are recorded as
  failures. No repair, no fallback, no retries beyond the app's standard
  transient-retry policy, all charged.
- Two consecutive infrastructure failures on one step: stop, record, and
  re-plan before resubmitting (`AGENTS.md`, two-failure rule).
- No threshold, budget, arm, metric or query changes after the first
  inference call. Results are reported as they come out, including a failed
  or partial campaign.

## 9. What this evaluation can and cannot claim

**Can claim, in plain words:** at a fixed budget, on this licensed selection,
the pinned local pipeline with the adapter scored what it scored, the hosted
teacher scored what it scored, and the difference between them is [CI], at
[cost]. If the thresholds pass: among the systems actually compared — local,
pinned, running this product pipeline — the winner is best in class. On 20
reviewed no-match queries, the winner falsely asserted events [n] times out of
20, and honestly refused the rest.

**Cannot claim:**

- Any Charades-STA state of the art, or comparability to supervised
  specialists (the 60% family is a different class; section 2.2).
- "Untouched held-out" purity for the 69 queries — their exposure history is
  disclosed (section 0).
- Anything about CCTV, doorbell or long-footage accuracy. Charades is
  scripted indoor amateur footage, 16.7–42.8 s clips.
- Corpus-level cross-file retrieval, speech, counting, reference-image or
  long-video capability (section 5.3, section 3.4).
- Freedom from pretraining contamination for any large model — hosted or
  base — on public Charades media. Only our own adapter's exposure is
  auditable, and section 3.3 audits it.
- Anything about Decider routing or OCR: both remain unbuilt
  (`AGENTS.md`, codebase item 5).

## 10. Execution order for the running session

Each step names its proof. The ledger, the monitor and the two-failure rule
apply throughout.

1. Freeze and gates: G1–G7 (section 6). Proof: freeze hash in
   `DECISIONS.md`; gate results in the run manifest.
2. Build local visual indexes for the 25 test videos. Proof: 25 ready
   indexes; zero model-service attempts.
3. Arm H: fresh description index over the 25 test videos; identity probe.
   Proof: build complete; attempt count matches the manifest.
4. Arm B: serve the pinned base; build its index. Proof: serving job
   healthy and watched; base manifest hashes verified at load.
5. Arm A: same, with the acceptance-passing adapter. Proof: adapter
   SHA-256 verified at load and written into the run manifest.
6. Run 69 positives per arm (section 5.1 request, frozen order). Proof: 69
   ledger rows per arm, failures included.
7. Run 20 negatives per arm. Proof: 20 ledger rows per arm.
8. Retrieval-only diagnostics from the stored candidate pools (section 5.2).
   Proof: raw/reranked/visual ranking tables, zero new model calls.
9. Score: metrics, paired deltas, video-grouped bootstrap (seed 20261120,
   2,000 reps), negatives rates, cost ledger (section 7). Proof: numbers
   reproducible from the ledger alone.
10. Write `evaluation/untouched-benchmark-results-v1.json` (same shape as
    the pilot artifact: run manifest, arms, per-arm metrics, paired deltas,
    negatives, cost, status, limits). Private negatives manifest stays
    private. Record the verdict and the pre-declared claim sentence
    (section 7.3) in `DECISIONS.md` and `PLAN.md`. No rerun.

## 11. Risks (largest first)

1. **Adapter training contamination of the test videos.** The Charades
   supervision targeted "186 windows over 45 different scenes"
   (`PLAN.md`), and the pilot has exactly 45 videos. Overlap is likely, not
   hypothetical. It would leak the A-vs-H comparison on those queries. This
   is the single biggest protocol risk, it is checkable before inference,
   and the outcome mapping (section 3.3) is pre-declared so the one-shot
   rule survives it.
2. **Small n.** 69 queries over 25 video groups; one query is 1.45 points.
   Intervals will be wide. Mitigation: paired video-grouped bootstrap,
   thresholds written as rates, small-group warning kept.
3. **Hosted identity drift.** Arm H's service is unpinned; it may have
   changed since the pilot. Mitigation: fingerprint probe, disclosed limit;
   no fix exists.
4. **Adversarial negatives, authored by the system's own team.** The
   false-match rate is an upper-bound stress, not an average case. Disclosed
   in section 3.2 and copied into the report.
5. **Unknown pretraining exposure** of every large model to public Charades.
   Unfixable; disclosed; only our own adapter's exposure is audited.
6. **Cost overrun via hosted retries.** The ledger enforces the cap; a cap
   hit yields a partial report, never a cap raise.

## 12. Artifacts this design relies on

- `PLAN.md` — master plan stage 7; fine-tune campaign; dataset scale-up.
- `DECISIONS.md` — approved Charades slice; extent v3/v4/v5 pre-test designs;
  "Final measured decision"; the 19 November mandate and comparison-class
  rule; reference-image, speech, counting sections; fine-tune campaign.
- `evaluation/charades-point-aware-pilot-results.json` — selection rule,
  hashes, budgets, ledger 1460/1500, anchors, bootstrap design.
- `evaluation/finetune-adapter-eval-v2.json` — adapter identity,
  serving-contract pass, honest quality limits.
- `evaluation/trained-temporal-full-test-results.json` — supervised reference
  context (60.19% / 60.04% family), out of class.
- `evaluation/speech-search-e2e-results.json`,
  `evaluation/event-counting-e2e-results.json`,
  `evaluation/image-query-e2e-results.json` — proofs of the excluded paths.
- `src/video_search/api.py` — endpoint and parameter contract.
- `tests/test_benchmark_compare.py` — frames-per-check accounting.
- `TEAM.md` — role 37 lane.
- `AGENTS.md` — monitor requirement, two-failure rule.

## Freeze record

The integrator computes SHA-256 of this file and records it in
`DECISIONS.md` under "Stage 7 protocol frozen". From that moment the
protocol is frozen: sections 3, 5, 7 and 8 may not change before the run.
A change after the run is a new protocol document, not a rerun.
