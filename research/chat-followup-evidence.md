# Evidence retrieval improvements from chat.md

Checked 6 November 2026. This note checks the main research claims in `chat.md` against primary sources and maps them to this codebase. It adds to `pipeline-research-review.md` and `benchmark-strategy-review.md`; it does not replace their evaluation rules. Paper scores below are authors' results, not our measurements.

## What the sources support

| Source | Checked result and limit | Implication for this project |
| --- | --- | --- |
| [VideoRAG, Jeong et al., Table 7](https://arxiv.org/html/2501.05874v3#A2) | Random videos score 24.29 ROUGE-L; retrieved videos score 25.42. Answer similarity alone cannot establish good evidence retrieval. | Measure localization before and after verification. Add irrelevant-evidence controls. |
| [CARVE, sections 5–6 and reproducibility statement](https://arxiv.org/html/2606.13141v2) | Table 2 reports Recall@5 0.603 versus 0.510 for VideoRAG-A, and Qwen3-VL-32B answer pass rate 0.368 versus 0.312. The baselines share chunk embeddings. CARVE pools four modality/granularity branches, retains branch tags, and uses a multimodal reranker. Its benchmark searches within a supplied long video and removes repeated events. The paper says data, code, and evaluation scripts will be released upon acceptance. | Keep retrieval provenance. A query-level route should not remove useful evidence without proof. Our current two-path RRF is a baseline, not CARVE. No verified runnable release was found in this check; do not claim a CARVE reproduction or compare archive-wide counts with its scores. |
| [MERIT, Tables 3 and 11, appendix C](https://arxiv.org/html/2608.07663v2) | For GPT-5, adding nearby context raises target-time hit rate from 0.40 to 0.56, while QA rises from 70.0 to 71.2. With Qwen3-VL-8B, flat caption retrieval scores 46.6; multi-key retrieval plus neighbor filtering scores 54.2. Its larger context also costs more tokens. | Test nearby evidence separately from new semantic searches. A better hit rate does not guarantee a similar answer gain. It is reasonable to test local expansion before building a global graph. |
| [MemDreamer, Tables 3, 7–10](https://arxiv.org/html/2606.07512v2) | Reports 90.7 LVBench with Gemini-3.1-Pro and a prebuilt hierarchical graph. It measures online reasoning context separately from perception work. More retrieval rounds and more candidates do not always improve its score. | Use explicit call/frame budgets and stop reasons. Measure index construction separately from query work. Its result does not establish the benefit of adding a graph to our smaller system. |
| [GraMRAG, Table 1 and implementation](https://arxiv.org/html/2609.14066) | Qwen3-VL-8B results in the chat match Table 1: WikiHowQA 27.1 to 33.4, SyntheticQA 48.6 to 59.0, XVBench 32.1 to 41.2. These are binary model-judged answer scores, not ROUGE. Training uses eight H100 GPUs. | Keep this as later training research. It is not a direct benchmark target for this laptop implementation. |

The chat's central research question is useful: can a limited second inspection recover missing evidence and abstain when support remains weak? The checked sources already study repeated retrieval, multi-key memories, and temporal expansion. Combining those features alone is not a new research contribution. A new contribution would need a distinct method and a controlled gain, such as better temporal evidence recovery at equal cost.

This check did not repeat the chat's exhaustive citation search, verify its citation counts, or establish a global model ranking. The three linked `video-rag-*.md` reports from that chat are not in this workspace.

## What is already built

Read-only inspection found the following:

- `store.search_descriptions` already combines vector and keyword ranks.
- `/search` already supports visual, description, and hybrid paths. Hybrid results retain branch scores and paths.
- `analysis.verify` reads the source, inspects eight ordered frames, validates model intervals, and saves the result and evidence.
- Verification has `match`, `no_match`, and `insufficient_evidence` outcomes. These describe the inspected interval; they do not prove that an event is absent from an archive.
- The browser currently checks a fixed small set of candidates. A saved, budgeted search procedure and a repeatable temporal evaluation are the missing seams.

## Small implementation sequence

These are proposed experiments, not deductions that the papers prove for our data.

1. **Add a bounded server-side evidence search.** Reuse current retrieval and verification. Keep the initial ranking and each inspected interval. Return the budget, work used, stop reason, and supported source intervals. A failed model call must remain an error. It must not become an abstention or a match.
2. **Spend inspection on distinct time regions.** Exact duplicate intervals should not consume two checks. Compare rank-only selection against an explicit temporal-diversity policy. Preserve every candidate in the trace. Do not merge nearby windows into one supposed event; overlapping views can contain different actions.
3. **Test a second pass only for missing evidence.** Compare two options separately: inspect the next unvisited candidate, or inspect adjacent source windows when the first check is uncertain. Keep the same total call and frame budgets as the one-pass baseline. A second pass is a retrieval policy, not an error fallback.
4. **Keep frame density when expanding.** Eight frames across a longer interval can hide the brief action that motivated expansion. Prefer bounded adjacent inspections, or an explicit frame-budget split. Record actual sampled PTS and inspected source seconds. Do not claim continuous coverage from sparse frames.
5. **Make no-match scope clear.** Use wording such as “No supported match in the inspected candidates.” Exhaustive absence, event counts, identity matching, and cross-video causal answers need separate tests and should not be inferred from top-K search.
6. **Run an ablation before adding another model.** Hold the index, encoder, verifier, prompts, and source files fixed. Test the effect of candidate selection and extra inspection first. A multimodal reranker, multi-key embeddings, ASR, and a learned router can follow a measured failure.

## Runnable public test and benchmark path

The [official QVHighlights repository](https://github.com/jayleicn/moment_detr) includes a 150-second public example video and query. On this check, the direct video URL returned HTTP 200 and a size of 10,404,801 bytes. The [query file](https://raw.githubusercontent.com/jayleicn/moment_detr/main/run_on_video/example/queries.jsonl) contains query 8056 and target interval `[106,122]`. Use it as an end-to-end smoke test, not a held-out result. The current upstream commit is `b7e553ac3b0c898ee6b85e03ee507c064eab89ca`; pin downloaded files to that revision and save hashes. The repository distinguishes MIT code from CC BY-NC-SA 4.0 annotations.

- [Pinned example media](https://raw.githubusercontent.com/jayleicn/moment_detr/b7e553ac3b0c898ee6b85e03ee507c064eab89ca/run_on_video/example/RoripwjYFp8_60.0_210.0.mp4)
- [Official annotation format](https://github.com/jayleicn/moment_detr/blob/b7e553ac3b0c898ee6b85e03ee507c064eab89ca/data/README.md)
- [Official evaluation instructions](https://github.com/jayleicn/moment_detr/blob/b7e553ac3b0c898ee6b85e03ee507c064eab89ca/standalone_eval/README.md)
- [Official evaluator](https://github.com/jayleicn/moment_detr/blob/b7e553ac3b0c898ee6b85e03ee507c064eab89ca/standalone_eval/eval.py)

The raw archive linked by the authors also returned HTTP 200, but reports 143,734,787,897 bytes. Do not download roughly 144 GB merely to prove an adapter. The repository's small sample is enough for the first full pipeline check. A later benchmark run needs a declared, reproducible media subset or the full licensed dataset.

Use the official evaluator for published QVHighlights comparisons. Its moment-retrieval AP evaluates up to ten predictions over IoU thresholds 0.50 through 0.95; R1 compares the first prediction with the best-matching ground-truth interval. Prediction rows contain query ID, video ID, and ranked `[start,end,score]` windows. An adapter must preserve local clip time: the media filename's original-video offset must not be added to annotations. Validate this on the public example.

## Evidence required for an improvement claim

Freeze source splits, media hashes, prompts, model revisions, retrieval paths, and budgets before evaluation. Keep human labels and expected answers out of the production index. Save both the raw candidate list and the checked intervals, including failed queries.

Run four conditions on the same queries: current top-K; distinct-time selection; larger one-pass K; and bounded second-pass inspection. Match total verifier calls and sampled frames, and report the number of actual calls as well as the cap. Keep indexing cost separate. An adaptive policy cannot take credit for a gain caused only by more work.

Report candidate Recall@K at fixed temporal IoU, final temporal recall, unsupported-match rate, abstention rate, p50/p95 latency, and total model calls/frames. Report multiple required evidence intervals separately from a single relevant interval. For negative queries, inspect complete source recordings before assigning ground truth; missing annotations are not proof of absence.

Use paired comparisons and confidence intervals grouped by source video. Preserve official splits and candidate pools for leaderboard comparisons. A small public smoke set or a private user video can prove the pipeline works; neither can establish SOTA. A new method must beat a reproduced baseline under the same task and budget before a stronger claim is justified.

No model or benchmark was run for this research note. The remaining risk is measurement: a better search trace and valid model output do not by themselves prove better evidence accuracy.
