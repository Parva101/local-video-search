# Performance campaign — 14 November 2026

The user approved research, selected implementation and longer Sol training. Read the detailed [retrieval review](retrieval-experiments-2026-11-14.md) and [temporal-model review](temporal-model-options-2026-11-14.md). Paper scores are author reports, separate from our measurements.

## Selected experiments

| Order | Experiment | Evidence and reason | Success check |
| --- | --- | --- | --- |
| 1 | Caption score curves | TAG and REZE support temporal aggregation; no new observations or model calls are needed for this first control | Beat the same fixed-window retriever at temporal overlap |
| 2 | UniVTG control plus IoU-quality foreground training | Released motion/image/text features permit a small learned grounder; ranking confidence can differ from boundary quality | Same features, architecture, split and initialization; three seeds |
| 3 | Dense frame/motion fusion and a stronger specialized grounder | Sparse still images miss action changes; SDST supplies a strong specialized reference | Separate head gains from representation gains; count extraction cost |
| 4 | Native-video recognition refinement and verified-negative calibration | Recognition scores can guide local checks; Moment of Untruth supplies negative-aware labels | Equal-cost edge gain and lower false positives without lost positive recall |

This is the first campaign's final shortlist. Implement later items only when the preceding error analysis supports their cost. More agent tools, a graph, full VLM RL and router work do not directly address the measured boundary problem.

TAG and REZE already use temporal pooling and deterministic interval extraction. Our caption-score interpolation is an adaptation, not a reproduction of their BLIP-2 or Yes/No-logit inputs. Simple smoothing is not novel. [TAG](https://github.com/Nuetee/TAG), [REZE](https://arxiv.org/html/2608.04480v1).

The training adaptation uses detached predicted-interval IoU as the positive foreground target. Classification plus localization quality is established prior work. We use weighted binary cross-entropy, not the full Quality Focal Loss formula, and claim no new loss. Its gain on this temporal model remains unmeasured. [Generalized Focal Loss, NeurIPS 2020](https://proceedings.neurips.cc/paper/2020/file/f0bda020d2470f2e74990a07a607ebd9-Paper.pdf).

UniVTG was selected for accessible, modest-size features and a pinned MIT-licensed implementation. SDST remains a stronger specialized reference; beating our old caption baseline will not establish SOTA. Corrected TimeLens boundaries are a separate target because label quality changes model rankings. [UniVTG](https://github.com/showlab/UniVTG), [SDST](https://github.com/davidpujol/SDST), [TimeLens](https://github.com/TencentARC/TimeLens).

The possible later contribution is a compact temporal scorer combining archive descriptions, dense visual evidence, reliable rejection and selective boundary checks. Each component has prior work. Novelty requires an exact difference and controlled results, not the combination alone.

## Completed caption experiment

All 53 development queries selected from ten fixed settings: Gaussian sigma 0, 0.5, 1, 2 or 3 seconds, crossed with local-background weight 0 or 0.5. Selection: R@1 at IoU 0.5, then mean IoU, then R@1 at IoU 0.7; first entry wins exact ties. The chosen setting was sigma 2 seconds, background weight 0. Code/input hashes were frozen before evaluation.

All 69 old pilot queries from 25 videos remain. They were previously exposed, so this is exploratory. Every new method uses the same saved caption reranker scores. **Zero new model calls; no production database writes.**

| Method | R@1 IoU 0.3 | R@1 IoU 0.5 | R@1 IoU 0.7 | Mean IoU |
| --- | ---: | ---: | ---: | ---: |
| Raw caption retrieval | 65.22% | 39.13% | 5.80% | 36.99% |
| Reranked caption retrieval | 65.22% | 42.03% | 4.35% | 35.89% |
| Selected score curve | 63.77% | 43.48% | 20.29% | 40.66% |
| Unsmoothed curve | 68.12% | 43.48% | 15.94% | 40.99% |
| Fixed sigma 1-second control | 66.67% | 43.48% | 18.84% | 41.52% |
| Fixed sigma 1-second plus local contrast | 66.67% | 43.48% | 17.39% | 41.31% |

Selected minus reranked: **+1.45 percentage points** at IoU 0.5, just one query. Video-group bootstrap 95% interval: **[-9.09, +10.96] points**, including zero. Mean IoU: **+4.77 points**, interval **[+0.56, +8.71]**. There are only 25 source groups. IoU 0.3 recall falls. Do not select the fixed control because its test mean IoU looks better.

The fixed-window pool's label-aware oracle is 69.57% at IoU 0.5 and 57.23% mean IoU. That diagnostic is not a deployable model. It shows both ranking headroom and interval limitations.

The decoder rejects coverage gaps, keeps fractional final seconds and marks spans estimated, unverified and not model-checked. A flat curve abstains without proving absence. Maximum-subarray extraction can join repeated events; it does not solve counts. Aggregate: [caption-curve results](../evaluation/caption-curve-pilot-results.json). Private inputs/results stay ignored. The old hosted ledger remains at 1,460 attempts.

## Release audit

Data job **1480741** completed in 8 minutes 7 seconds, without a GPU. The checkpoint, labels/config and three feature archives were downloaded and hashed. Pinned source: `32659ac7aeba21742a63274f30eba785fc57e247`. Motion and image archives each have 9,848 NPZ files; text has 16,124. Extraction rejects unsafe paths, links, wrong types and flattened-name collisions.

Author train metadata has **12,404 queries / 5,336 videos**; canonical has **12,408 / 5,338**. A normalized source/query comparison finds 24 changed strings and four omitted rows: three from two wholly absent videos, one from another video. Test retains **3,720 queries / 1,334 videos**, with seven changed strings. This is a distinct processed release. Among shared source/query keys, 1,800 training and 562 test intervals differ from the pinned VSLNet preprocessing; maximum endpoint differences are 0.21033s and 0.18534s. Thus the author-release and canonical-label scores must remain separate. Exact differences stay private.

Training uses a fixed video-hash split: **11,116 train queries / 4,802 videos**, **1,288 validation queries / 534 videos**. Test never selects epochs. Author raw width 2,816 requires the parser's two temporal endpoint values, giving effective width 2,818. The driver tests that rule. Our controlled training starts from scratch at learning rate 1e-4; it does not reproduce pretrained fine-tuning at 1e-5.

## Run gates

Strict loading rejects missing, zero, non-finite or wrong-shaped arrays and preserves all feature steps. Epoch recovery stages model/optimizer/scheduler/RNG state, publishes winning model/predictions/history, then advances the resume checkpoint. Tests simulate interruptions at each stage.

First smoke **1484086** failed before any training step because the reused container has no Git executable. Full feature preflight passed. Driver v2 replaces that runtime dependency with exact pinned source-file hashes; it retains source-path shadowing checks. Old protocol/logs stay intact. A second smoke submission was rejected because the completed preparation job was no longer available for an `afterok` dependency; no job was created. Preparation success is already verified by accounting, so a new smoke can submit without that expired dependency.

V2 smoke **1485684** then passed both 20-step training variants. Measured A100-SXM4-80GB batch times were 0.05987s and 0.04837s; peak allocated GPU memory 2.35GiB. Full v2 Docker regression: 452 passed, two skipped private-checkout checks, two existing warnings. Those private source checks pass separately on the host.

Long job **1486462** failed in its first validation after 70 seconds, before an epoch checkpoint. A CPU reproduction isolates a numeric-envelope error: duration 30.38035 becomes 30.38035011291504 in the model's float32 clamp, then 30.3804 at four decimals; the validator used double-duration rounding 30.3803. Three development queries have that duration. Preserve official emitted values; validate against the same float32/four-decimal envelope. Do not add an arbitrary tolerance or repair predictions.

Pause long jobs until driver v3 smoke runs the full validation grid and checkpoint save/load after 20 training steps, for both conditions. V3 uses a new `runs/strict-head-v3` namespace. This gate corrects the first smoke's missing epoch coverage. Old failures and launch records remain unchanged.

**V3 gate passed:** job **1487482** completed 0:0. Both conditions ran 20 training steps, all 1,288 validation queries and full model/optimizer/scheduler/RNG save/load. Measured step times were 0.04993s and 0.04931s; validation took 0.98s and 1.08s. Peak allocated GPU memory was 2.35GiB. The six-run training-plus-validation projection is 3.05h, excluding startup/checkpoint costs. The final model-enabled Docker suite passed **454 tests**, with two skipped private-checkout checks and two existing warnings; the two private checks pass separately on the host. Reviewer found no blocker after the gate.

**Long run submitted:** **1488158**, one A100, course account, eight-hour wall limit. It trains baseline and IoU-quality conditions, each at seeds 2018/2019/2020 for 100 epochs, with train-only validation. Expected wall time **4–7 hours**, excluding queue delay; this is an estimate. The batch script explicitly forwards Slurm's `CUDA_VISIBLE_DEVICES` into the clean container, using the existing Sol serving pattern. No further source changes while this campaign runs.

Log: `/scratch/psheta12/video-search-temporal-20261114/logs/train-1488158.log`. Checkpoints/history: `/scratch/psheta12/video-search-temporal-20261114/runs/strict-head-v3/{baseline,quality}-{2018,2019,2020}/`. Each run has immutable `protocol.json`, recoverable `pending.pt` during a commit, `latest.pt`, `best.pt`, and `history.jsonl`.

Check on Sol: `sacct -j 1488158 --format=JobID,State,ExitCode,Elapsed`. When it finishes, the next task is to verify all six complete histories and source identities, freeze development selection, then score the trained models and released reference with the full-test driver. Do not treat the 20-step validation metrics as trained benchmark results. Do not keep tailing the long job.

Start verified once: **RUNNING**, with the first complete baseline epoch, all validation queries and both `latest.pt`/`best.pt` saved. Epoch compute plus validation took 23.09s. The job is left running for the user to check; no further polling is needed now.

Measure GPU type, peak memory and step time before long training. A batch-only estimate excludes validation and checkpoint costs. When a long run starts, report job ID, expected duration, log/checkpoint paths and the user's status command, then leave it running.

## Updated access finding

QVHighlights test labels are now public. Official Moment-DETR commit `7c61a84217e7e6b7ee0ba0ae494c337644e9cdd4`, dated 9 March 2026, releases `data/highlight_test_with_gt.jsonl` after CodaLab shutdown. This corrects older hidden-server advice. Raw-video access and terms remain separate. [Official release commit](https://github.com/jayleicn/moment_detr/commit/7c61a84217e7e6b7ee0ba0ae494c337644e9cdd4).

Full-benchmark gains, refined-label gains, reliable counts, absent-query performance, novelty and SOTA remain unproved.
