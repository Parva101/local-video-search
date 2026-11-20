# Full temporal-head test — 14 November 2026

**The IoU-quality foreground adaptation did not improve the main test metric. Keep the baseline.** Its mean R@1 at IoU 0.5 is 58.80%, versus 60.04% for the matched baseline. The train-only validation gain did not transfer. This negative result is retained in the project.

All six runs finished 100 epochs. Job **1488158** completed successfully in **4h35m4s**, using one A100. Each used the same 11,116 training queries and 1,288 source-disjoint validation queries. The architecture and inputs were fixed; the adaptation changed only foreground targets to detached predicted-interval IoU. This is an established quality-calibration idea, not a novel loss.

## Complete test results

Evaluation job **1527713** completed successfully in **9m19s**. Every one of its eight comparisons retained **3,720 queries from 1,334 videos**. Checkpoint contents were audited: the six best epochs match the frozen validation selections, latest checkpoints reached epoch 100, and protocol/hash links match. No test score selected a checkpoint or seed.

| Matched batch-32 method | R@1 IoU 0.3 | R@1 IoU 0.5 | R@1 IoU 0.7 | Mean IoU |
| --- | ---: | ---: | ---: | ---: |
| Baseline, mean of three seeds | 71.06% | **60.04%** | 37.31% | **51.09%** |
| IoU-quality, mean of three seeds | 69.22% | 58.80% | 38.65% | 50.44% |
| Released pretrained reference | 72.61% | 60.11% | 38.55% | 52.12% |

The reference uses pretraining and the authors' model selection procedure. It is a stronger external control, not a matched training comparison.

| Seed | Baseline R@1 IoU 0.5 | Quality R@1 IoU 0.5 | Quality minus baseline |
| --- | ---: | ---: | ---: |
| 2018 | 61.32% | 58.55% | -2.77 points |
| 2019 | 59.76% | 59.89% | +0.13 points |
| 2020 | 59.03% | 57.96% | -1.08 points |

Do not select the best seed and call its result the method's performance. The sample standard deviations at IoU 0.5 are 1.17 points for baseline and 0.99 for quality.

Paired bootstrap resamples seed pairs and whole source-video groups, with the same video draw across sampled seeds: 2,000 draws, seed 20261114. Only three seed pairs limit the uncertainty estimate.

| Quality minus baseline | Mean difference | 95% interval |
| --- | ---: | ---: |
| R@1 IoU 0.3 | -1.84 points | [-3.22, -0.38] |
| R@1 IoU 0.5 | -1.24 points | [-3.08, +0.55] |
| R@1 IoU 0.7 | +1.34 points | [-0.21, +2.76] |
| Mean IoU | -0.65 points | [-1.57, +0.30] |

The stricter-IoU point estimate rises, but its interval includes zero. The main metric falls in two seeds and has no demonstrated improvement. These results justify rejecting this recipe, not claiming it can never work.

## Reference reproduction and batch padding

Before test scoring, review found that masked batch padding can enter the unchanged author's temporal convolution heads. A synthetic CPU check reproduced changed valid predictions. We therefore froze an extra reference check at the author's batch size 4, separate from the matched batch-32 comparison.

That native batch-4 check gives **72.63 / 60.19 / 38.55** R@1 at IoU 0.3 / 0.5 / 0.7 and **52.17% mean IoU**. These reproduce the rounded values in the author's release. Batch 32 gives 60.11% at IoU 0.5. The measured difference is small here, but batch size remains part of the protocol. [UniVTG paper](https://openaccess.thecvf.com/content/ICCV2023/papers/Lin_UniVTG_Towards_Unified_Video-Language_Temporal_Grounding_ICCV_2023_paper.pdf), [author model release](https://github.com/showlab/UniVTG/blob/32659ac7aeba21742a63274f30eba785fc57e247/model.md).

## Reproduction and evidence

The public [aggregate JSON](../evaluation/trained-temporal-full-test-results.json) contains every seed, means, deviations, intervals, selected epochs, source/report hashes and timing. It contains no raw queries, video IDs or predictions. Raw evidence remains in ignored private storage.

Use `scripts/summarize_temporal_heads.py` with `--metadata`, `--reports`, `--freeze` and a new `--output`. It requires the complete frozen eight-case set, verifies checkpoint audit links and recomputes the metrics. Existing output files cannot be overwritten. The seven-case matched comparison uses batch 32; native batch 4 stays separate.

New focused checks: **47 passed**. They cover complete grids, identities, batch controls, point evidence, metric recomputation, confidence intervals and public privacy. The earlier complete model-enabled regression remains 454 passed with two private-checkout skips; those private checks passed separately on the host. No application search behavior changed in this evaluation step.

All inference timers use supplied precomputed features. They exclude raw-video feature extraction, query encoding and Python/container startup; they are not end-to-end application latency. Training and evaluation jobs together used about 4.74 allocated GPU-hours. No new hosted-model calls were made.

## Limits and next experiment

This is the full **processed author Charades-STA release**. It is not a claim of canonical annotation equivalence: seven test strings and 562 shared test intervals differ from the pinned canonical copy. The old 69-query subset was exposed. This does not measure absent queries, repeated events, counts, corpus search or long CCTV footage. It proves neither novelty nor SOTA.

The next approved experiment is the stronger **SDST released reference**, with verified checkpoint/data access and identical processed labels. Prepare a new immutable local snapshot first, then gate its isolated ROIAlign build and checkpoint inference before training. This changes both representation and head; report it as a stronger reference, not as a pure gain from our loss. [Access and runtime plan](stronger-feature-access-2026-11-14.md).
