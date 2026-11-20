# Benchmark strategy for local video archive search

Research checked on 2026-11-05. This is a draft recommendation, not a report of project results. No data, weights, or evaluation server submission was tested. Sources below are papers, author repositories, or official dataset documents.

## Main recommendation

Aim first to improve **evidence retrieval and timestamp accuracy at a fixed compute budget**. Do not set the project goal as beating every video model on a multiple-choice test. The product must find a source interval across files, keep repeated events, and show what was searched. A correct multiple-choice answer can occur even when the retrieved interval is wrong.

Use a small benchmark ladder:

1. QVHighlights for the first repeatable timestamp test.
2. TVR for corpus search with visual and subtitle routes, subject to media access.
3. A small, fully reviewed product test for absent events, repeated events, counts, and recording gaps.
4. Ego4D NLQ for a harder external action-grounding test after access is ready.
5. ForeSeaQA for the direct ForeSea comparison only when its full release and evaluator are obtained.

QV-M2 and TVR-Ranking are useful extensions. LongVideoBench and OpenHome are secondary answer-model tests. Do not make all nine datasets a first-release requirement.

## Benchmark fit and limits

| Dataset | What it measures | Use in this project | Main limit / access requirement |
|---|---|---|---|
| QVHighlights | Query-conditioned intervals and highlights within a supplied video | First temporal-localization harness; repeated moments already exist | It does not test choosing the right file from a large archive |
| TVR | Video corpus moment retrieval using video, subtitles, or both | Best direct fit for mixed visual/speech retrieval and routing tests | TV dialogue differs from meetings; raw-media access and rights must be checked |
| TVR-Ranking | Several relevant intervals ranked across a corpus, with graded relevance | Better fit for broad requests that have many valid answers | Relevance judgments are not proof that every occurrence is labeled |
| Ego4D NLQ | Find the interval that answers a natural-language question in a supplied egocentric clip | Action/state evidence and hard temporal grounding | Wearable-camera data differs from fixed cameras; official release version matters |
| Ego4D MQ / VQ | All instances of a named activity / last occurrence of a reference object | Possible later tests for repeated activity and object-image queries | Separate tasks and labels; neither is a general identity-search benchmark |
| QV-M2 | Retrieval of several matching moments | Test missed events and boundary refinement | Reuses the QVHighlights setting; not an independent archive-scale domain |
| ForeSeaQA | Surveillance question answering plus temporal grounding | Direct comparison with ForeSea and ForeSea-Global | Full release and reproduction access not confirmed in this review |
| LongVideoBench | Multiple-choice reasoning with long video and subtitles | Check that retrieval does not remove needed context | Answer accuracy does not measure archive recall or boundary accuracy |
| OpenHome | Multiple-choice understanding of home-camera clips | Test the final visual verifier on relevant camera footage | Test-only release; short-clip QA does not establish long-footage search quality |
| MAD | Sentence grounding over long movies | Later scale test if the required features suffice | Access requires a form/NDA; source movies are not released |

### QVHighlights: start here, but keep the task name accurate

The original release has train, validation, and test annotations. The paper uses a 70/15/15 split and includes multiple intervals per query. Its moment metrics include mAP at IoU 0.5 and 0.75, average mAP over 0.5:0.05:0.95, and R@1. Preserve the official evaluator and report exact metric names. Sources: [paper](https://proceedings.neurips.cc/paper/2021/file/62e0973455fd26eb03e91d5741a4a3bb-Paper.pdf), [data](https://github.com/jayleicn/moment_detr/blob/main/data/README.md).

The current author evaluator caps the mAP input at ten predicted windows by default. Its R@1 code compares the top prediction with the best-overlap ground-truth window. This rewards finding one good event; it does not establish complete event coverage. Use the official score unchanged, then add a separately named complete-event diagnostic. [Evaluator](https://raw.githubusercontent.com/jayleicn/moment_detr/main/standalone_eval/eval.py).

Moment-DETR is the simple, reproducible supervised baseline. FlashVTG is a stronger practical comparison candidate with released checkpoints for SlowFast+CLIP and InternVideo2 features. Report which feature family and training data each method uses. Do not call a feature upgrade a pure pipeline gain. The repository points to a test evaluation server; server availability was not tested. [Moment-DETR](https://github.com/jayleicn/moment_detr), [FlashVTG](https://github.com/Zhuo-Cao/FlashVTG).

### TVR: the useful routing benchmark

TVR has approximately 109K queries over 21.8K clips. Queries carry visual, subtitle, or combined type labels. This allows per-type scores for our retrieval paths. Its XML baseline separates corpus-level video retrieval from finer moment localization. [Author repository](https://github.com/jayleicn/TVRetrieval).

The official evaluator distinguishes VCMR, SVMR, and video retrieval. VCMR requires both the correct video ID and enough temporal overlap. It reports R@1/5/10/100 at IoU 0.5/0.7. A test that supplies the correct file is SVMR, not VCMR. Keep the official candidate corpus; a 100-file sample is a development test, not a full TVR result. [Evaluator](https://raw.githubusercontent.com/jayleicn/TVRetrieval/master/standalone_eval/eval.py).

Use the type labels as a routing diagnostic, not absolute truth about the only useful path. Captions can recover visual facts; a combined query may need evidence from both paths. The real gate is end-to-end retrieval loss versus searching all available paths. This is our proposed evaluation method.

The VALUE release lists TVR annotations under CC BY-NC-SA 4.0. The software's MIT license does not grant rights to redistribute television footage. Raw-media download and current access terms need a separate check before choosing TVR as a required end-to-end dataset. [VALUE data facts](https://github.com/VALUE-Leaderboard/DataRelease/blob/main/DATA.md), [software license](https://github.com/jayleicn/TVRetrieval/blob/master/LICENSE).

### TVR-Ranking and QV-M2: avoid a one-answer bias

TVR-Ranking supplies graded relevance for 94,442 query-moment pairs and uses NDCG with temporal-IoU constraints. Its author repository supplies ReLoCLNet and links XML and CONQUER baselines. This tests the quality of a result list more directly than a single-positive task. It does not remove the need to inspect unjudged matches. [Paper](https://arxiv.org/html/2407.06597v1), [code and release](https://github.com/Ranking-VMR/TVR-Ranking).

QV-M2 adds 2,212 annotations covering 6,384 segments. FlashMMR refines boundaries and verifies proposals after initial prediction. Its paper evaluates multi-moment metrics including G-mAP, mAP@3+tgt, and mR@3. Use its evaluator if we claim results on this task; do not replace its definitions with our count metric. Released code, annotations, and checkpoint links make it a useful second-stage experiment. [Paper](https://arxiv.org/html/2510.17218v1), [repository](https://github.com/Zhuo-Cao/QV-M2).

### Ego4D: pin the release and input

NLQ asks for a temporal response window within a supplied clip. MQ asks for all windows of a named activity. VQ asks for the last visible occurrence of a query object, with spatial and temporal output. These are separate tasks; a high NLQ score does not establish count or reference-image performance. [Official task definitions](https://ego4d-data.org/docs/benchmarks/episodic-memory/).

NLQ reports R@1/5 at temporal IoU 0.3/0.5. GroundVQA is a trained reference, not a training-free pipeline: its reported NLQ-v2 test result of 26.67 R@1 at IoU 0.3 and 17.63 at 0.5 uses specified pretraining and fine-tuning. OSGNet is a later comparison candidate. Neither is labeled current SOTA here. [GroundVQA paper](https://openaccess.thecvf.com/content/CVPR2024/papers/Di_Grounded_Question-Answering_in_Long_Egocentric_Videos_CVPR_2024_paper.pdf), [OSGNet paper](https://openaccess.thecvf.com/content/CVPR2025/papers/Feng_Object-Shot_Enhanced_Grounding_Network_for_Egocentric_Video_CVPR_2025_paper.pdf).

Ego4D access now points to Lab22. Official instructions require review and acceptance of the data terms, then credentials. Select the benchmark subset rather than the full multi-terabyte archive. Record release ID, annotation hashes, accepted terms, and local media manifest. We have not completed this access process. [Access instructions](https://ego4d-data.org/docs/start-here/).

For pipeline comparison, Fan et al.'s VideoAgent is a closer conceptual baseline than a large trained grounder: it combines caption and visual retrieval. Its results are tied to its selected features and split. Use its automatic-caption setting; human annotations used as searchable captions are privileged input. [VideoAgent](https://arxiv.org/html/2403.11481v2).

### ForeSea and short-answer tests

ForeSea-Global reports 68.1% answer accuracy and 18.6% temporal IoU on text-only ForeSeaQA; its multimodal setting reports 65.1% and 16.1%. These are paper results, not our reproduced targets. The text-only VideoLLaMA3 baseline reaches 67.7% accuracy but 15.5% IoU. This makes temporal evidence a more useful improvement target than answer accuracy alone. Keep the query modality, evaluator, answering model, and sampling budget fixed for a pipeline claim. [ForeSea tables 5–6](https://arxiv.org/html/2603.22872v1).

LongVideoBench provides validation and test loaders with frames and subtitles. A subtitle-enabled run must not be compared as if it used the same inputs as a no-subtitle run. Record frame limits, resolution, reasoning settings, and all indexed source data, not just final answer-model frames. [Official loader](https://github.com/LongVideoBench/LongVideoBench).

OpenHome exposes one test split of 2,254 questions, with CC BY-NC 4.0 listed on its card. Its published protocol samples at 1 fps, caps input at 64 frames, uses about 200K pixels per frame, and excludes audio and metadata. Use it as an untouched final visual check. Tuning on it would weaken the external-test claim. [Dataset card](https://huggingface.co/datasets/wyzelabs/OpenHome).

MAD is valuable for long-form retrieval, but its authors release annotations and precomputed features after an access process; they do not release the movies. It cannot be our default raw-video ingestion test. [Official repository](https://github.com/Soldelli/MAD).

## Proposed experiment contract

These are proposed rules for a credible experiment, not requirements imposed by the papers.

### Three distinct claims

1. **System gain:** same base models, better intervals at the same per-query budget. Count all indexing work separately.
2. **Efficiency gain:** preserve retrieval quality within a declared tolerance, reduce latency or model work. Fix the tolerance before evaluation.
3. **Model gain:** a trained retriever or boundary head beats its frozen version using the same data split. Report training cost and data.

Do not combine these into one unexplained percentage. A pipeline using a stronger caption model can be a better product, but it is not a controlled test of retrieval logic.

### Baseline ladder

| Run | Purpose |
|---|---|
| Uniform sampling plus fixed answer model | Measures the value of search for QA, where that task permits it |
| Fixed windows plus visual-vector search | Smallest visual search baseline |
| Timestamped transcript keyword and vector search | Speech-only baseline |
| Visual descriptions plus visual vectors plus transcripts, all enabled | Main high-recall baseline for the planned app |
| Same system plus Decider routing | Tests whether classification saves work without losing evidence |
| Same system plus context expansion and boundary refinement | Tests the main quality hypothesis |
| Same system plus adaptive windows / second temporal scale | Tests recovery of short and long actions |
| Relevant published method, reproduced on identical inputs where possible | Gives an external comparison |

Run the first working versions before adding a scene graph, multi-agent planner, detector fleet, or full-model fine-tuning. Optional mechanisms need a measured error to solve.

### Metrics and logs

- **Candidate recall:** fraction of labeled intervals reached before verification at a declared temporal overlap and candidate budget. Also report retrieved seconds per query; top-K alone is unfair when windows differ in length.
- **Final temporal quality:** official R@K/mAP/IoU metrics plus boundary error where useful. Use the dataset's matching rules.
- **Repeated events:** event precision/recall/F1 after one-to-one matching; count MAE and exact-count rate. This requires reviewed complete labels. Retrieval duplicates are not events.
- **Absent events:** false-positive rate and precision of a reported match. Add manually checked absent-event queries; missing annotation is not evidence of absence.
- **Answer quality:** correct answer supported by correct source evidence. Separate answer-only accuracy from joint answer-and-evidence success.
- **Efficiency:** p50/p95 cold and warm query latency, peak GPU/RAM, model calls, decoded frames, indexed video hours per wall hour, index bytes per video hour, and rebuild cost.
- **Robustness:** missing audio, broken media, variable frame rate, duplicate files, edits after indexing, recording gaps, and explicit clock offsets.

### Split and measurement discipline

1. Freeze data manifests, source checksums, model revisions, prompts, frame rates, evaluation code commit, candidate budgets, and random seeds.
2. Split original recordings before making windows or paraphrases. Keep adjacent windows and simultaneous views of the same event together in the product test.
3. Use train data for fitting; use a defined validation portion for thresholds. Freeze choices before the held-out test. Do not use test answers, reference captions, or human event labels to build the production index.
4. Preserve official candidate pools and split versions for published comparisons. Label smaller runs as subsets. Report inaccessible media and failed queries; do not silently drop them.
5. Compare methods with paired per-query outputs. Bootstrap by source recording, rather than treating many windows from one video as independent observations. Report confidence intervals and failure categories, not only means.
6. Measure two budget settings: equal final evidence budget, and equal total query cost. Publish indexing cost separately and show how it amortizes over repeated queries. Include captioning calls and classifier load time.
7. Compare the router with all-path search. Measure missed evidence, not just label accuracy. A route classifier can save work but cannot recover evidence from a route it disabled.
8. Keep custom concatenated archives separate from official benchmarks. Use them for scale stress tests and call them derived tests. Concatenation does not create verified camera continuity or exhaustive labels.

## Realistic success gate

Proposed first goal: improve temporal retrieval over the all-path fixed-window baseline on one official dataset, with the same models and declared evidence budget, and reproduce that gain on the reviewed product set. Require a paired confidence interval that supports the gain, or report the result as inconclusive. Then test cost reductions without material recall loss.

Only claim to beat ForeSea after reproducing its task and inputs on the released benchmark. Only claim a leaderboard result after the official evaluation. It is reasonable to aim for better temporal accuracy or a better accuracy/cost tradeoff. There is no evidence yet that our planned system will beat the strongest fully trained grounders or every closed video model.

## Open questions and unchecked items

- Which raw-video dataset can we access first under its terms: QVHighlights, TVR, or Ego4D?
- Is the complete ForeSeaQA release available with its exact evaluator and setup?
- What query-cost and indexing-cost budget should define the first experiment?
- Who will review complete event labels and negative queries for the product test?
- What accuracy loss, if any, is acceptable for routing cost savings?

No dataset was downloaded, no agreement was accepted, and no benchmark was run. Code/checkpoint links and evaluation servers were inspected as documentation, not executed. Data rights, media availability, and reproducibility remain release gates.
