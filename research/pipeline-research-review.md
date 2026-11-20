# Pipeline research review

Checked: November 5, 2026. Status: research and proposed experiments. No models, datasets, or paper code were run. This file does not approve implementation or replace confirmed choices.

## Main finding

The proposed frame, description, and transcript index is a sound baseline. It is not enough, by itself, to support a claim that we beat a research benchmark. Its main weaknesses are loss of brief actions, fixed clip boundaries, missing evidence after an early routing decision, and treating a few retrieved clips as an exhaustive search.

The strongest initial hypothesis is: **combine broad retrieval with source-linked, query-specific inspection at a fixed cost, then refine event boundaries.** Keep the index simple and make every added stage prove its value. A larger classifier or a graph database is not the main research contribution.

## What the papers support

### ForeSea and ForeSea-Global

ForeSea indexes tracked person clips, retrieves candidates, and uses VideoLLaMA3-7B for answers. Global indexes full scenes. Its text-only result is 68.1% multiple-choice accuracy and 18.6% temporal IoU; its multimodal result is 65.1% and 16.1%. These are different query settings. The paper shows failures in counting and notes that retrieval can remove context needed for activities. Its default top-three selection is a useful comparison, not a sound rule for finding all events. The benchmark's VideoRAG baseline is Luo et al., not Ren et al. **Implication:** retain scene context and evaluate time localization separately from answer accuracy. [Paper, sections 4–5 and appendix](https://arxiv.org/html/2603.22872v1).

### VideoAgent, Fan et al.

This system stores approximately two-second video segments with captions, visual features, and caption text features. Tools retrieve memory and inspect selected video. On Ego4D NLQ, generated LaViLa captions plus ViCLIP give R1@0.3 of 11.13, versus 8.40 for ViCLIP alone. This supports complementary representations in that setup. It is not a comparison with ForeSea. Human-caption results are a separate condition and cannot represent an automatic index. **Implication:** measure visual and generated-text retrieval both alone and together. [Paper](https://arxiv.org/html/2403.11481v2).

### VideoTree

VideoTree clusters visual features, captions representatives, then explores relevant groups in more detail. It supplies selected captions in temporal order. Its reported EgoSchema and NExT-QA accuracy concerns question answering, not corpus search or timestamp accuracy. **Implication:** query-specific expansion is a useful experiment; permanent deletion of similar observations is not required to gain its efficiency benefit. [Paper](https://arxiv.org/html/2405.19209v3).

### VideoRAG, Ren et al.

Ren's method combines graph-based text knowledge and visual features for questions across long video collections. Its LongerVideos evaluation includes 160 videos and more than 134 hours. This is relevant to cross-recording discussion search. It does not establish gains on Ego4D NLQ or ForeSeaQA. **Implication:** keep a future path for cross-recording evidence, but do not build an entity graph before simpler retrieval fails on that task. [Paper](https://arxiv.org/html/2502.01549v1).

### Visual Agentic Memory, 2026

VAM separates indexing from retrieval, keeps temporal and spatial observations, and uses raw evidence for inspection. It reports OVO-Bench RT+BT average 68.41, versus 67.46 for direct use of the same Gemini 3 Flash model. It reports 17.11% on a month-scale MM-Lifelong split. The modest first gain and low second score matter: a complex memory system does not solve long-video understanding. The authors also state that an unretained state change cannot be recovered. Their reported API-based setup is not proof of local-model performance. **Implication:** preserve source media and track index coverage; measure the added query cost. [Paper, limitations and appendix](https://arxiv.org/html/2605.16481v1).

### VideoTapestry, 2026

This method refines a three-level memory using query-specific visual and ASR observations. A 200-question Video-MME Long ablation reports 79.5% for static retrieval and 87.0% for the full method. This compares several changes together; it does not isolate graph storage or prove that multiple agents are necessary for our system. The controlled final-memory experiment holds exploration fixed and compares the context supplied to the answer model. **Implication:** test new source observations separately from context organization. Do not cite that 7.5-point gain as a full-dataset localization result. [Paper, Table 3 and Appendix C](https://arxiv.org/html/2610.06672v1).

### VideoSearch-R1, 2026

This work directly separates corpus retrieval, match verification, and temporal grounding. Failed matches lead to learned soft-query refinement. It uses supervised training followed by GRPO; it is not a training-free plug-in. Its results use Charades-FIG, DiDeMo-FIG, and ActivityNet-FIG. **Implication:** a single failed first retrieval need not end a search, but our first implementation should test a bounded extra retrieval pass before adopting learned query tokens or reinforcement learning. Original dataset scores and FIG scores are not interchangeable. [Official project](https://mlv.kaist.ac.kr/VideoSearch-R1/).

### Smaller retrieval and counting references

Tran et al. combine CLIP and BEiT-3, scene/keyframe selection, and neighboring-frame reranking. The paper is close to the user's original proposal, but its illustrated retrieval improvements are not a numeric leaderboard result we can claim to beat. Neighbor smoothing could also suppress short events, so test that failure case. [CVPR workshop paper](https://arxiv.org/html/2504.08384v1).

CountVid treats unique-object counting as a tracking problem, including reappearance and occlusion. Its public code uses CountGD and SAM2. This is useful for counting instances, but unique people, visits, door crossings, and repeated actions are four different target definitions. [Paper](https://arxiv.org/abs/2506.15368), [official code](https://github.com/niki-amini-naieni/CountVid).

## Proposed changes, in priority order

The following are engineering hypotheses, not reported results from the cited papers.

| Priority | Change | Reason and proof |
| --- | --- | --- |
| 1 | Keep original media, source timestamps, and occurrence records | Similar views at different times can be separate events. Check brief events and re-entry after a long static scene. |
| 1 | Establish an all-available-path retrieval baseline | A classifier can exclude the only useful path. Compare end-to-end recall and cost before enabling route exclusion. |
| 1 | Keep scene video as the main evidence | Object crops remove surrounding action and locations. Test crop additions only after a scene baseline. |
| 1 | Retrieve candidates before expensive inspection | Measure candidate recall at fixed inspected-video seconds; the answer model cannot recover missing candidates. |
| 1 | Inspect original source around each candidate | Compare caption-only answers with direct media inspection using the same answer model. |
| 1 | Refine boundaries with ordered local observations | Return an action interval rather than the storage window. Measure temporal IoU and boundary error. |
| 2 | Combine short and longer context windows | Short actions and extended discussions require different spans. Test one scale against two, with equal total index or query cost. |
| 2 | Use compatible video-text embeddings for action retrieval | Pooled still images can miss order. Test against the existing frame baseline, including reversed actions. |
| 2 | Use keyword plus semantic search for speech | Exact names and paraphrases need different matching. Test names, acronyms, negation, and ASR errors. |
| 2 | Budget candidates across distinct time regions | Neighboring duplicates can consume top-K. Measure event recall before and after overlap grouping. |
| 3 | Add bounded query-time expansion | One extra source inspection or retrieval pass may recover uncertain cases. Compare with simply increasing initial K at the same cost. |
| 3 | Add local tracks or region observations only for measured failures | Count and spatial tasks may need them. Measure gain against compute and annotation cost. |

## Clip construction and duplicate handling

Start with logical windows over source media; do not create a separate video file for every window. Keep the earlier ten-second, two-second-overlap proposal as one baseline, not as an established optimum. Compare it with a two-scale design on validation data. Window durations, overlap, and frame rates must be selected before the final test.

Use scene changes as hints for edited videos, not as the only event boundaries. A fixed camera can show an entire day in one shot. Likewise, low global motion can hide a small hand or drawer movement. Keep a regular sampling floor. Add change-based samples rather than replacing the floor until recall measurements support that change.

Group repeated frames to save embedding or caption work, but retain every occurrence time and its parent interval. Do not use global similarity to delete time spans. Do not reuse a generated action caption merely because two still frames look similar. A selected representative must point back to the source region that produced it.

Keep speech chunks separate from visual windows. Use sentence or subtitle boundaries with context; preserve word or segment timestamps where the recognizer provides them. A discussion may span several visual scenes. A silent action may have no transcript match.

## Query and evidence design

The chosen Decider Flash 4B can score route labels, but it should earn the right to exclude a path. First compare it with searching all available paths. Test independent route decisions for mixed queries. Report route recall, missed relevant paths, latency, and total retrieval cost. A lower classifier error rate is not enough if final event recall falls.

Use rank-based fusion initially; do not average raw similarities from unrelated encoders. Search exact names in text alongside embeddings. Treat OCR as a separate later observation when queries about signs, screens, or slide titles fail; do not describe OCR text as speech.

Verification should return a supported interval, evidence source, and match status. For an action, inspect a before, action, and after sequence. For removal of an object, distinguish contact, drawer opening, visible removal, and an unknown object. A fluent generated description is not enough evidence for any of these.

Keep final source times separate from concatenated candidate time. Validate that intervals fall inside inspected source bounds. Store the frame or clip evidence used for each decision so a user can check the result.

## Find versus count

For finding a useful match, ranked retrieval with a budget is acceptable. For finding every event, top-K is only candidate generation. A count needs a declared event definition, reviewed or processed coverage, event merging rules, and a list of matched events.

Separate visit counts from unique-person counts. A visitor can return twice. A person visible in two overlapping windows is not two visits. A local track ID is not proof of identity across a long occlusion or another camera. Start with event occurrences in one recording and count the verified event table. If search or processing is incomplete, report the observed count and the missing coverage; do not claim an exhaustive total.

## Encoder experiment worth testing

VideoPrism's official release now includes matched video-text encoders. The Base LvT variant is 248M parameters, with a 991 MB checkpoint; Large is 580M and 2.30 GB. The release distinguishes public checkpoints from paper models and notes differences in their results. This is a credible small action-retrieval candidate beside a frame encoder. Use the matched LvT text encoder, not the video-only backbone with an arbitrary text encoder. The repository uses JAX, which adds deployment work; verify actual runtime memory and speed before choosing it. [Official release and model table](https://github.com/google-deepmind/videoprism).

Do not pick an encoder from whole-video retrieval scores alone. Its ranking of short actions and localization under our sampling policy is the test that matters.

## Minimal ablation sequence

1. Freeze a test set, source splits, metric implementation, model revisions, and query budget. Keep tuning separate.
2. Run frame/clip embedding retrieval only. Save candidate intervals before analysis.
3. Add generated descriptions. Then add transcripts on the speech-bearing subset. Measure each path's unique relevant matches.
4. Add original-media verification and local boundary refinement. Keep the answer model fixed.
5. Test one versus two window scales and frame versus video-text encoding, one change at a time.
6. Compare all-path retrieval with Decider routing. Keep routing only if its cost saving meets the agreed recall tolerance.
7. Test bounded expansion against a larger one-pass candidate budget. Count all model calls and inspected frames.
8. Only then test hierarchy, crops, tracking, or learned reranking for a known failure class.

Report candidate recall, final temporal metrics, unsupported matches, absent-event accuracy, event-count error where applicable, p50/p95 query time, index time per source hour, storage per source hour, peak VRAM, and paid model cost. Do not combine these into one unexplained score. Show quality-versus-cost curves and confidence intervals grouped by source video.

## Scope and open questions

The evidence supports a useful retrieval-and-verification system. It does not establish that our design beats ForeSea, current temporal-grounding methods, or a closed model. A fair first claim would be a measured gain over a reproduced baseline under the same backbone and resource budget.

Open: which public benchmark can we obtain and reproduce; which runtime works on the laptop; what accuracy/cost tradeoff is acceptable; and which event types define the first release? Training should target the largest measured error source, not begin with a large-model fine-tune by default.

No downloads, reproduction runs, model fit checks, or data-license audit were done in this review. The main risk is scope: general video search, precise action localization, and exhaustive counting require separate tests and cannot share one headline accuracy claim.
