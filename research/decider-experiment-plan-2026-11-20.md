# Decider routing experiment protocol — 20 November 2026

Status: frozen protocol, design only. Nothing has been run. A future session executes this file as written. Any change needs a recorded v2 and a reason. This document is a plan, not a claim that the model works.

Provenance: the user confirmed a dedicated typed-decision model before retrieval ([DECISIONS.md](../DECISIONS.md), 2026-11-05: "Decision model chooses the search path" and "Test Perplexity Decider Flash v1.2 first"; [RULES.md](../RULES.md): not a general chat LLM prompted to emit routing text). The retained classifier experiment and its four steps are in [PLAN.md](../PLAN.md). The four policies and the draft tradeoff are in the [full project draft](full-project-draft-plan.md), section 4.5. Model facts below were read from the [model card](https://huggingface.co/perplexity-ai/pplx-decider-flash-v1.2) on 20 November 2026.

## 0. What this experiment decides

One question: does a typed-decision model earn a place in the default query path, by saving at least 20% of the measured cost or latency, without losing evidence? The comparison class is the app's own local index and verifier with planted events. This is an engineering-grade comparison, not a public benchmark result.

The 27B `pplx-decider-v1.2` stays out of scope: it exceeds the laptop 3080 BF16 weight budget, and DECISIONS.md selected the 4B Flash checkpoint for the first test.

## 1. Verified model facts (read from the model card, 20 November 2026)

| Fact | Value |
| --- | --- |
| Exact ID | `perplexity-ai/pplx-decider-flash-v1.2` (Qwen3.5-4B backbone; card lists 5B params, BF16) |
| Repository | Gated. Access needs a Hugging Face token with permission. Access is unverified for our account. |
| Size | About 9 GiB BF16 weights plus working memory. Requires Python 3.12+ and a CUDA GPU. |
| Runtime | Native decision runtime `pplx_decider.Decider`, not chat generation. Question types: `choice`, `noul` (P(true)), `score`. Each answer carries probabilities and confidence. |
| Temperature | Saved value 1.554, applied by `decide()` by default. Their held-out calibration: ECE 0.021. Their claim, not ours; our task differs. |
| Grouping | One question per request is the card's safer default for this model. Grouping may help only for tightly coupled facets of one decision. Both modes are measured here (section 6). |
| Images | Supported, resized to at most 1.6 MP. Image queries pass the reference image into `images`. |
| Checksums | `release-manifest.json` records file checksums. Used for the pinned revision. |
| License | Apache-2.0. |
| Fast path | Optional, needs `requirements-fast.txt`. Reference path is the measured default here (section 2). |
| Published scores | Decision Index 58.88 overall. These do not measure this routing task. Do not cite them as evidence for adoption. |

## 2. Gate 1 — access and fit, local first

Local-first rule (RULES.md, 20 November 2026): prove the code on the laptop 3080 before any Sol job. Sol smoke attempts are for environment differences only, not for debugging our code.

| Step | Work | Proof | Stop rule |
| --- | --- | --- | --- |
| A1 | Verify access and pin the revision: `model_info` with the access token; record the commit SHA; `snapshot_download` at that SHA; verify `release-manifest.json` checksums. | Saved SHA, file list, checksum result. | Two consecutive access failures: stop. Report the blocker. No third-party mirrors or reuploads; provenance is part of the experiment. |
| A2 | Local smoke in a throwaway GPU container (the existing model-cache volume; nothing installed into the app stack). Install the checkpoint's own `requirements.txt`. Run the model card's usage example unchanged. | Saved valid typed output, cold-load seconds. | Two consecutive failed smokes: stop. Record the error. Do not start case work. |
| A3 | Measure the smoke: 20 short `decide()` calls. | Median and p95 warm seconds, peak VRAM (`torch.cuda.max_memory_allocated` plus `nvidia-smi`), GPU swap count. | Two consecutive OOM at the frozen runtime config: stop. A quantized or CPU variant is a new experiment and needs user approval. |
| A4 | Fit verdict. Expected: about 9 GiB weights plus short-sequence activations fits the 16 GB 3080 standalone. The app stack keeps its own containers; the Decider runs alone. | Written verdict with numbers. | — |
| A5 | Optional, only if the user asks for scale-up repetition: one Sol A100 job. Add it to `.codex-backups/sol-monitor/watch.json` first; read `ALERT.md` at session start; two failures stop the job per project rule. | Job ID, duration, ledger. | Same. |

Runtime config frozen for every comparison in this protocol: reference path (`fast=False`), saved temperature, `max_length=32768`, one request at a time, pinned revision. A fast-path run, if it installs cleanly, is an appendix comparison only; the gate never depends on it.

## 3. Gate 2 — labelled route set, frozen before any run

72 routing cases: 6 groups of 12. Vocabulary comes only from [docs/SAMPLE-QUESTIONS.md](../docs/SAMPLE-QUESTIONS.md) (the doorbell-camera and meeting-room shapes). Do not invent new query styles.

| Group | Cases | Drawn from the sample set | Expected route |
| --- | --- | --- | --- |
| Visual-only | 12 | Q1, Q4, Q5, Q11 (reference-image queries included) | `visual` (image queries: `visual` or `hybrid`) |
| Description-only | 12 | Q2, Q6, Q15 | `description` |
| Speech-only | 12 | Q7, Q8, Q9 | `speech` |
| Mixed | 12 | Q3 and action-plus-speech combinations | two or three paths together |
| Count | 12 | Q16, Q17, Q18, Q21 | mode `count` (the count endpoint takes no `path`; see below) |
| Unavailable-modality | 12 | Q20, a speech query with no transcript index, an image query with no ready visual windows | visible unavailability or a valid alternate route; never a silent switch |

Split: 36 tuning, 36 held-out — 6 per group in each. Deterministic rule: sort by `case_id`, even positions to tuning, odd to held-out. Frozen before the first model run; no case moves afterwards.

The executing session writes `evaluation/decider-route-cases.json` and records its SHA-256 in the results file header before any run. Schema per case:

```json
{
  "case_id": "VO-01",
  "group": "visual-only",
  "query": "a delivery driver at the front door",
  "context": {
    "image_attached": false,
    "available_modalities": {"visual": true, "description": true, "speech": true}
  },
  "expected": {
    "mode": "search",
    "paths": {"visual": true, "description": false, "speech": false},
    "ambiguity": "clear",
    "acceptable_alternatives": [],
    "confidence_band": "clear"
  }
}
```

Rules for the frozen expectations:

- The hard labels are the per-path yes/no set plus the mode. A case passes if the thresholded decision set equals the expected set, or, for cases with `ambiguity: "uncertain"`, matches any listed `acceptable_alternatives`.
- `confidence_band` is the case author's judgement, frozen before any run. The calibration check on held-out is an ordering check, not an invented threshold: mean P(true) of `clear` cases must exceed mean P(true) of `uncertain` cases per path. Absolute values are reported as measured.
- Unavailable-modality cases freeze the required behaviour: a visible incomplete result or error that names the missing index. A silent switch to another path, or results presented as if they answered the question, is a failure.
- Count cases: `/count-events` takes no `path` (verified in `src/video_search/api.py`). The router's mode choice selects the endpoint. Per-path answers for count cases are recorded as diagnostics only.

### 3.1 Evidence fixture library (end-to-end evidence recall)

Routing scores alone do not establish pipeline evidence recall (PLAN.md). End-to-end runs need planted ground truth.

- 48 evidence queries, 12 per retrieval group (visual-only, description-only, speech-only, mixed), each with a labelled interval on local fixtures: synthetic visual clips in the existing test-fixture style, plus speech events planted through authored SRT import (exact timestamps).
- 12 count queries on known-count fixtures (for example, N planted colour-window events).
- Split: evidence 24 tuning / 24 held-out (6 per group each); count 6 / 6.
- Frozen in `evaluation/decider-evidence-manifest.json`, SHA-256 recorded before any run.
- Primary metric: a verified evidence match overlapping the labelled interval. Secondary: IoU at least 0.5. Both reported.
- Comparison class, stated in every result: local planted-event library, engineering grade. No public benchmark claim.

## 4. Gate 3 — four policies

All policies run on the same index, the same verifier, and the same budgets. The Decider's own seconds count inside the policies that use it.

| Policy | Definition |
| --- | --- |
| P0 — all-path baseline | Search every available path for every query; fuse with the existing reciprocal rank fusion. The reference the gate is measured against. |
| P1 — small explicit rule baseline | Deterministic rules for unambiguous cases only: an attached image routes to `visual`/`hybrid`; explicit speech words ("discussed", "mentions") route to `speech`; "how many" routes to count mode. Rules are authored once, frozen with the cases, and never tuned on held-out. |
| P2 — Decider selects paths | The typed decisions choose which paths to search. Excluded paths are not searched. Decisions below the tuned confidence threshold widen visibly to all-path (marked in the response; never silent). |
| P3 — Decider allocates budget | All available paths stay in the search, but the Decider's confidences allocate the per-path candidate budget and the verification budget (`max_checks` and per-path limits). No path is hard-excluded. |

P0 and P1 make the honesty check explicit: a 4B classifier can cost more than the local database searches it avoids. If P1 captures most of the savings, the report must say so.

### 4.1 Adoption gate, frozen

Adjudicated on the held-out split only, after all tuning choices are frozen. All four conditions must hold:

1. **Valid outputs.** At least 95% of Decider calls return schema-valid typed outputs. Every invalid output is visible in the ledger, counted, never retried silently.
2. **Cost or latency.** P2 or P3 shows at least 20% lower total measured cost (Decider + encode + retrieval + verification seconds per query) or at least 20% lower median warm end-to-end latency than P0. The other of the two metrics may not regress by more than 5%. p95 warm latency, peak VRAM and swap counts are reported; no GPU swap in the warm steady state.
3. **Evidence recall.** Aggregate loss versus P0 at most 1 percentage point. At the frozen sample (24 held-out evidence queries) one lost query is 4.2 points, so the frozen discrete form is: **zero lost held-out evidence queries, in every retrieval group.** If the evidence set grows to 100 or more queries, the 1-point aggregate and a 5-point per-group bound replace the discrete form.
4. **Uncertainty bounds.** Wilson 95% bounds on every recall proportion; bootstrap bounds by query on latency and cost differences. A pass whose bounds still allow a worse-than-gate outcome is reported as "pass, uncertain". Bounds too wide to adjudicate mean no adoption claim, only a report.

**Keep** (recommendation; the user decides, per DECISIONS.md): all four pass, with one extra honesty check — if P1 reaches 80% of P2/P3's savings within the same recall tolerance, recommend rules-first and keep the Decider for uncertain cases only.

**Retire** (recommendation): any condition fails, or a stop rule triggers. The report states the failure plainly. Proposing all-path as the new default is a separate user review, because it changes an agreed direction.

## 5. Gate 4 — cost ledger and stop rules

One JSON ledger row per run:

```json
{
  "policy": "P2", "case_id": "SP-07", "split": "held-out", "warm": true,
  "decider": {"calls": 4, "input_tokens": 0, "seconds": 0.0, "valid": true,
              "revision": "<pinned sha>", "request_mode": "one_per_request"},
  "encode_seconds": 0.0, "retrieval_seconds": 0.0,
  "verification": {"calls": 0, "seconds": 0.0, "tokens_in": 0, "tokens_out": 0},
  "end_to_end_seconds": 0.0, "peak_vram_gib": 0.0, "gpu_swaps": 0
}
```

Cost is measured in seconds and tokens. No money conversion unless the user supplies prices. The verifier is the configured hosted vision service; its latency is counted; its accuracy is not re-evaluated here.

Two-failure stops (record each stop in PLAN.md, then re-plan; never a silent workaround):

- Access: two consecutive failures (section 2, A1).
- Smoke or OOM: two consecutive failures at the frozen runtime config (section 2, A2/A3).
- Schema validity: invalid-output rate above 5% on the **tuning** split after at most two request-format iterations. Held-out failures never trigger iteration. Any change after held-out exposure requires a new frozen version and a fresh held-out run, recorded as such.
- Sol jobs: two failures of the same job configuration, per the project rule.

## 6. Decider request contract, frozen

The classifier receives typed questions, nothing free-form. It never emits SQL, filters, query rewrites, plans or explanations. Explicit user filters (recordings, dates, second ranges) pass through untouched and stay authoritative.

- **State:** the query text, image presence, and available-modality metadata (ready window and segment counts per path within scope). Non-strings serialize as JSON, per the runtime contract.
- **Images:** reference images go into `images`, capped at the checkpoint's 1.6 MP.
- **Questions:** one `noul` per path — "Given the available indexes, should the visual-embedding path search for this query?" (same for generated descriptions, same for transcripts/subtitles) — plus one `choice` for mode: `search` or `count`.
- **Request mode:** the card recommends one question per request as the safer default, but these questions are facets of one routing decision, so both modes are measured on the tuning split; the better mode is frozen for held-out; both are reported.
- **Thresholds:** decision threshold 0.5 and the low-confidence widening threshold start there, are tuned on the tuning split only, and are frozen before held-out.

## 7. Gate 5 — integration sketch (design; no code yet)

Implementation waits for review under AGENTS.md. The sketch, for that review:

- `path: "auto"` as a new allowed value on `/search`, `/evidence-search` and (as a routing mode) on count requests. Explicit path values keep their current authority; `auto` is opt-in.
- The backend validates every typed field: P(true) in [0, 1], mode in {`search`, `count`}, known question IDs. Unknown fields are rejected. The backend constructs the actual request from the validated decisions plus the untouched explicit filters. There is no free-form plan surface to validate away.
- Responses gain a `route` block: model ID, pinned revision, policy, per-path decisions with probabilities, mode, decider seconds, `valid: true/false`. Invalid decisions return a visible 422 naming the router, with the raw decision recorded; never a silent all-path fallback.
- Low-confidence widening is marked in the response (`widened: true, reason: "low_confidence"`). A required modality that is unavailable produces the existing visible coverage/incomplete semantics; another path's results are never presented as the answer.
- The routing decision, model and version are recorded with each query run, per DECISIONS.md.
- A new module and config flag; no monkeypatching; current default behaviour unchanged.

## 8. Run order

| Order | Step | Proof |
| --- | --- | --- |
| 1 | A1 access and revision pin | Saved SHA and checksum result |
| 2 | A2/A3 local smoke | Saved outputs, cold load, warm p50/p95, peak VRAM |
| 3 | Author and freeze the 72 routing cases | `evaluation/decider-route-cases.json` + SHA-256 |
| 4 | Author and freeze the fixture library and manifest | `evaluation/decider-evidence-manifest.json` + SHA-256; planted events probed once through the API |
| 5 | Author and freeze the P1 rules | Rule list in the results header |
| 6 | Tuning runs: P2/P3 in both request modes; set thresholds and mode | Tuning ledger |
| 7 | Freeze thresholds, request mode and rules | Recorded in the results header |
| 8 | Held-out runs: P0, P1, P2, P3 on routing cases, evidence queries and count queries | Per-query ledger |
| 9 | Latency subset: the 24 held-out evidence queries, 3 warm repeats each, all policies | p50/p95 per policy |
| 10 | Adjudicate and report | `evaluation/decider-routing-results-<date>.json` + human summary; keep/retire recommendation; honest limits |

## 9. Honest limits

- Published Decision Index scores do not measure this routing task.
- 24 held-out evidence queries per group boundary is a small sample. The bounds will be wide. The result is engineering-grade evidence for a keep/retire recommendation, not a general accuracy claim.
- Speech search and counting are experimental paths in the app; their limits carry over to this experiment.
- No latency or accuracy targets are invented here; first measurements come from the smoke.
- Comparison class, stated with every result: local planted-event library on the shipped index and verifier.

## 10. Open questions

1. Does the user's Hugging Face account already have access to the gated repository, or must access be requested first?
2. Is the local 3080 run the whole evaluation, or is a Sol A100 scale-up wanted afterwards?
3. Confirm the P1 rule contents (the keyword list for speech, count and image cases) before authoring.
4. Confirm the strict discrete recall gate: zero lost held-out evidence queries at n=24.
