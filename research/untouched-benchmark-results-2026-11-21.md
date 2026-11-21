# Stage-7 untouched benchmark — one-shot results

Date: 2026-11-21. Executor: benchmark execution engineer (role 37 lane).
Protocol: `research/untouched-benchmark-design-2026-11-20.md`, frozen at commit
`06901bc` (SHA-256 `403D07AF...C57B`) with Amendments 1 and 2 appended pre-run
(amended SHA-256 `9EEE47B2...61D`, freeze trail in `DECISIONS.md`).
This report uses the protocol's claim-wording map verbatim; no sentence is
stronger than the numbers earn. Private per-query traces, the negatives
manifest and licensed media stay under `.codex-backups/` (ignored storage).

## What ran

One one-shot campaign, frozen budgets: 2 source checks, 8 frames per check,
16 sent frame slots per query, 12 reranked candidates, description
1024/verification 2048 max tokens, temperature 0, seed 0, per-query request
`POST /evidence-search {path: "description", rerank: true, limit: 12,
max_checks: 2}` on the supplied video. Durable ledger cap 2,000 (amended);
**final count 1,190 attempts, all charged, never refunded**. Arms ran
sequentially H, H1, X, A; arm G followed as a supplementary pass on 21
November under the same frozen identity and ledger, after the user corrected
its route (the Amendment 2 credential was an OpenRouter misidentification; the
correct endpoint is the CreateAI gateway, model served as `openai/gpt6_1_sol`
— identity-neutral, since the frozen manifest pins arm name, declared model id
and revision only); B never reached queries (below). Infrastructure resumes
under protocol 8.3: one Sol serving-job cancellation overnight (arm A
mid-run), one dead tunnel (arm A index), both resumed with identical settings;
recorded model-level failures were never retried.

| Arm | System model | Positives (69) | Negatives (20) | Notes |
| --- | --- | --- | --- | --- |
| H | hosted `gemma4-31b-it`, unpinned | R@1 IoU .3/.5/.7 = 15.94 / 2.90 / 0.00 %, mean IoU 8.69 %, abstain 68.1 % | 0 false matches, 20/20 honest refusals | T1 clean; identity `vllm-0.26.0-tp4-24487d56`, same as the pilot's teacher |
| H1 | hosted `qwen3-vl-32b`, unpinned | 24.64 / 8.70 / 0.00 %, mean 16.75 %, abstain 40.6 % | 1 of 20 answered (0 false), 19 lost to the same failure below | **T1 FAILS: 36.4 % invalid-reply rate** — the gateway's constrained decoding repeatedly enters a whitespace loop (`finish_reason: length`, tab runs) and the strict schema rejects the reply |
| X | hosted `gpt-oss-120b`, unpinned | no query cases | — | **Failed arm at the description contract**: its verbose reasoning plus per-frame JSON exceeds the frozen 1024-token description budget, truncating mid-JSON; 1 of 25 index builds completed (45 attempts charged). Raising the budget is a frozen-budget change, forbidden after the first inference call |
| A | **pinned adapter** (base `Qwen/Qwen3-VL-4B-Instruct` @ `ebb281ec...` + LoRA `b1789134...`, served as `qwen3-vl-4b-adapter-v1`) | **52.17 / 33.33 / 7.25 %, mean IoU 30.05 %**, abstain 24.6 % | **0 false matches, 20/20 honest refusals** | T1 clean (2 of 69 answered cases carry transport-class errors from the overnight job cancellation; 0 model invalids) |
| B | pinned zero-shot base, same checkpoint | no measurements | no measurements | **Blocked by serving stack, two-failure rule exhausted**: vLLM 0.20.0 and 0.26.0 both silently skip `response_format` guided decoding on the Qwen3-VL multimodal path (proved by forcing tests with a required field the model never emitted); the zero-shot base needs that enforcement to satisfy the app's strict serving contract |
| G | hosted `openai/gpt-6.1-sol`, served as `openai/gpt6_1_sol` at the CreateAI gateway, unpinned | no query cases | no measurements | **Failed at the verification contract, disclosed**: route corrected from the misidentified OpenRouter credential; the description index built cleanly (25 of 25 videos, 102 windows, all HTTP 200 and schema-valid, p50 7.9 s per describe), and retrieval-only pools match the other arms (pool-best mean top-1 IoU 57.23 %) — but every frozen verify request was rejected upstream (HTTP 500 wrapping 400 `invalid_json_schema`: the endpoint requires object-typed response_format schemas; the app's frozen Verification union schema has no top-level type); 267 of 267 verify attempts failed; 0 of 89 cases answered; recorded, never repaired, per 8.3 |

Paired deltas on R@1 IoU 0.5, video-grouped bootstrap (seed 20261120,
2,000 reps): **A − H = +30.43 points, 95 % CI [16.67, 41.79]**. B − H and
A − B are not computed: arm B produced no measurements.

## Pre-declared thresholds

| ID | Threshold | Verdict |
| --- | --- | --- |
| T1 | Per-arm invalid-reply rate ≤ 5 % | A ✓ (2.9 %, both transport-class), H ✓ (0 %), H1 ✗ (36.4 %, disclosed), G ✗ (verification contract non-functional upstream; 0 of 89 cases answered), X/B no query attempts |
| T2 | Claim arm R@1 IoU 0.3 ≥ 15.9 % | ✓ — A reached 52.17 % (36 of 69); the hosted teacher's own anchor was 15.94 % |
| T3 | A − H on R@1 IoU 0.5: 95 % CI lower bound ≥ −4.35 points | ✓ — lower bound +16.67 points |
| T4 | A − B on R@1 IoU 0.5: 95 % CI lower bound > 0 | **Not demonstrated** — arm B has no measurements (blocked by serving stack) |
| T5 | Claim arm false-match rate ≤ 20 % (≤ 4 of 20) | ✓ — 0 of 20 |
| T6 | Cost reported; >2× wall-cost wording if exceeded | Reported below; the claim arm's verify latency is ~7× faster than hosted, no adverse wording |

## The claim sentence (protocol 7.3 map, verbatim)

The thresholds that passed are T1 (claim arm and hosted teacher), T2, T3 and
T5; T4 was not demonstrated. The map's corresponding sentence, with the CI
filled in, is:

> The pinned adapter matches the hosted teacher [CI: A − H = +30.43 points on
> R@1 IoU 0.5, video-grouped 95 % CI 16.67 to 41.79]. The gain over its own
> pinned base was not demonstrated on this set. No best-in-class wording.

No stronger sentence appears in this report. There is no SOTA claim, no
"untouched held-out" wording (the 69 queries' prior exposure is disclosed in
the protocol's honesty note), and no supervised-specialist comparison.

## Negatives disclosure (protocol 3.2, copied verbatim)

> the author team also built the system, so the negatives are adversarial,
> not random. The false-match rate measured on them is an upper-bound
> stress, not an average-case rate.

Method disclosure: the executing agent cannot view images, so absence was
confirmed against the licensed per-video annotation inventory (the positives'
own human-authored ground truth), never against model descriptions. Each
negative names a salient action class absent from the target video's entire
annotated inventory; unscripted background presence remains a disclosed risk,
not a hidden one. Manifest (20 entries, deterministic first-20 frozen order)
SHA-256 `daddd0e5...a87`, kept private.

## Cost (durable ledger, 1,190 of 2,000 attempts)

| Arm | Attempts (describe / verify) | Verify latency p50 / p95 |
| --- | --- | --- |
| H | 259 (103 / 156) | 3.77 s / 22.96 s |
| H1 | 202 (104 / 98) | high tail: loop failures ran ~140–170 s each before rejection |
| X | 47 (charged; index only, failed) | — |
| A | 310 (178 / 132; the 178 includes 75 transport failures from the cancelled serving job) | **0.52 s / 0.92 s** |
| B | 1 (probe, failed) | — |
| G | 371 (103 describe via CreateAI incl. its probe, all 200 / 267 verify, all rejected; plus the earlier 1 OpenRouter probe, 401) | rejected in ~0.9 s each (p50 0.84 s / p95 1.06 s); no completed checks |

Retrieval diagnostics (best candidate in the 12-candidate pool, zero model
calls): raw = reranked at top-1 for every arm with answered cases (H 69.57 %,
H1 66.07 %, A 68.66 % mean top-1 IoU). Arm G's case pools were never saved
(its cases errored before completion), so its number comes from a
retrieval-only re-run over its completed index: pool-best R@1 IoU 0.5
69.57 %, mean top-1 IoU 57.23 % — equal to arm H's ceiling. The
description path's strict-verification gain over pool-best is therefore a
comparison against a strong ceiling, not against the ranked order the pilot
reported. Local visual retrieval (69 queries, zero model-service attempts) is
stored under the private work directory with the same pools.

## Gates and audit

G1 freeze recorded; G2 identity pins verified fresh on Sol (base manifest
13-file re-hash, adapter SHA-256 match against the acceptance eval, job
2195712 re-verified at load); G3 contamination audit: **0 test videos in
adapter training rows** (all 106 Charades train rows are dev videos; merged
dataset verified row-for-row) — the full 69-query set carries the primary
claim; G4 negatives manifest hashed and private; G5 fresh ledger, cap
enforced, never hit; G6 probes passed for H, H1, X, A and G (G's probe
exercises the describe path; its verify incompatibility surfaced only at the
query phase and is disclosed in its arm row); G7 every Sol job watched
(`watch.json`: 2130192, 2132562, 2135198, 2139568, 2195712).

## Honest limits

- H1's serving contract is unstable under this gateway and schema (36.4 %
  invalid); its numbers are lower bounds on what it could score with a
  stable contract.
- Arm A was served without serving-layer grammar enforcement (the
  multimodal guided-decoding gap above); its validity comes from the
  adapter's trained contract, exactly the condition of its recorded
  acceptance gate (196/196 schema-valid, unconstrained). Disclosed deviation,
  consistent with the frozen identity.
- X's failure is a budget-contract failure, not a capability claim in either
  direction; only that it could not build the frozen 25-video index is
  measured.
- B's blocker is a serving-stack capability gap, not a base-model
  measurement; no A-vs-B number exists.
- G's failure is an upstream schema-validation contract failure, not a
  GPT-6.1 capability claim in either direction: its description index built
  cleanly (25 of 25 videos) and its retrieval-only pools match the other
  arms; only the strict verification stage could not run at this endpoint.
  A future protocol that re-envelopes the union schema as an object-typed
  root would be a new protocol document, not a rerun.
- 25 video groups, 69 queries: one query is 1.45 points; intervals are wide
  by construction.
- Hosted identities are unpinned; H's fingerprint matched the pilot's, H1's
  is recorded in the ledger traces, G's served id `openai/gpt6_1_sol` is
  recorded in its probe and ledger traces.
