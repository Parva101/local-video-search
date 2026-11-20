# Retrieval experiments supported by current research

Checked 14 November 2026. Research only. No model calls, training, data downloads, or application edits were made for this note. Paper scores below are author reports, not our results. The experiment designs are our proposals; they have no measured gain yet.

## Recommendation

Stop treating two sparse source checks as a strong temporal grounder. First test a dense temporal score curve with deterministic interval extraction. In parallel, reproduce one small trained grounder on released frozen features. These answer two different questions: can better temporal aggregation improve the present encoder, and how much does a learned grounder add?

Keep the current app and old pilot intact. Put experiments in a separate runner. Do not tune on the 69 evaluation queries from the old pilot. Those inputs and results are already exposed. Use those files for debugging only. Split new development videos by source ID; freeze the protocol before the full official test.

## What the current code actually measures

- `encoder.py` stores one normalized mean of three SigLIP2 still-image embeddings per window. It does not store a dense frame sequence or learn motion. Three sampled images cannot establish exact event boundaries.
- The completed pilot's main retrieval path is **description**, with lexical/vector fusion and a text cross-encoder. It is not a full visual-plus-description comparison. The benchmark runner requests 24 description candidates in a supplied video.
- On that 69-query subset, reranked retrieval has 42.03% R@1 at IoU 0.5 and 35.89% mean IoU. Extent has 33.33% and 28.86%. The stricter IoU 0.7 result favors extent, but it does not remove the loss on the main metrics.

These are observations from `src/video_search/encoder.py`, `store.py`, `benchmark_run.py`, and `evaluation/charades-point-aware-pilot-results.json`. They support replacing the experimental boundary component, not a claim that the entire retrieval architecture is wrong.

## Ranked experiment list

### 1. Dense score curves and several temporal scales

**Evidence.** TAG uses temporal pooling, temporal coherence clustering, and score adjustment without task training. Its official release reports Charades-STA R@1 at IoU 0.5/0.7 of **48.58/26.67** and mean IoU **45.69**, using BLIP-2 features at 3 fps. Its paper ablation raises R@1 at IoU 0.5 from 40.83 to 47.34 with temporal pooling, then 48.01 with coherence clustering. This is evidence for temporal continuity in that setup, not a prediction for SigLIP2. [Official code and reported results](https://github.com/Nuetee/TAG), [paper, Table 6](https://arxiv.org/html/2508.07925v1).

DSE-VTG combines frame and native video-clip similarities, then extracts intervals. With Qwen3-VL-Embedding, its Table 6 reports mean IoU **47.06** for frames, **42.82** for clips, and **51.30** for both. The paper says code will be released upon acceptance. Its multi-scale-only ablation scores 50.25 mean IoU; adding query adaptation reaches 51.30. These use a stronger encoder than our present SigLIP2 model. [Paper, sections 3.3–3.6 and Tables 5–6](https://arxiv.org/html/2609.08850v1).

**Adaptation.** Cache time-stamped, independent SigLIP2 frame features at a regular sampling rate. Compute a query-to-frame score sequence. Compare peak-centered fixed spans, pooled multi-scale spans, and a smoothed score curve with mean-centered maximum-subarray extraction. Preserve source timestamps and gaps. Evaluate two versions: the present sparse sampling and dense sampling. This separates new aggregation from new observations. Pooling still-image features does not make a native motion encoder.

**Ablations.** Same features: no smoothing, smoothing only, multi-scale only, both. Then hold the algorithm fixed and upgrade the encoder. Fix the proposal count and report total proposed seconds, feature-extraction cost, and query cost. Report candidate-oracle IoU to distinguish missing proposals from poor ranking.

**Risk.** Smoothing can erase a short action or join repeated actions. A high relative peak is possible even when no match exists. Mean-centering or min-max scaling is not an absence detector.

**Priority.** Implement first. It can run without new hosted calls. Add no clustering library merely to imitate TAG. Independently implement the simple score operations first; the TAG repository has no root `LICENSE` at the checked URL, so do not copy its code without resolving permission.

### 2. Frozen features plus a trained temporal head

**Evidence.** UniVTG predicts foreground indicators, temporal spans, and saliency. Its controlled full Charades-STA comparison uses CLIP ViT-B/32 plus SlowFast R50 and CLIP text features for all methods. Without its large pretraining, it reports **58.01/35.65 R@1 at IoU 0.5/0.7**, mean IoU **50.10**. With pretraining, it reports **60.19/38.55**, mean IoU **52.17**. The zero-shot row is much lower: 25.22 R@1 at IoU 0.5. Training setup is material. [Paper, Table 3](https://arxiv.org/html/2307.16715v2).

Its official feature table lists Charades data of 1.3 GB SlowFast, 305 MB CLIP video, 178 MB CLIP text, and 4 MB metadata. This permits a feature-based baseline without first encoding the full raw archive. It does not prove current download access. [Feature release](https://github.com/showlab/UniVTG/blob/main/install.md).

**Adaptation.** Reproduce the released model first on its own feature family. Then train an experiment head with the same labels and features. Include a small query-conditioned temporal head with an explicit no-match output and multi-scale frame/clip evidence. Train on official train videos; choose settings using a source-disjoint subset of train. Keep the official test out of epoch selection. Report the change from the reproduced model, not only from the app's small subset.

**Alternative.** FlashVTG releases scripts and checkpoints for Charades with InternVideo2 features. Its official training script uses 768-dimensional video features and 4,096-dimensional Llama text features, batch size 32, and 50 epochs. It points `eval_path` at official test annotations; change that selection rule for our new work. A released checkpoint can still be evaluated as a published baseline. [Release](https://github.com/Zhuo-Cao/FlashVTG), [training script](https://github.com/Zhuo-Cao/FlashVTG/blob/main/FlashVTG/scripts/charades_sta_internvideo2/train.sh).

**Proof.** Reproduce a frozen checkpoint before adaptation. Save dataset/model/code hashes, all epoch scores, and three training seeds. Compare the trained version against both the frozen feature scorer and the reproduced grounder. Use identical features when attributing a gain to the head. Verify actual Sol hardware, time per batch, and peak memory with a short run before predicting wall time. No defensible training-time estimate follows from the paper's epoch count alone.

**Priority.** Highest chance of a substantial benchmark gain after experiment 1. Full LLM fine-tuning is not the first requirement.

### 3. Recognition scores, then local boundary refinement

**Evidence.** REZE asks a frozen VLM whether an action is active in each short clip, reads the relative Yes/No logits, and aggregates ordered continuous scores outside the model. Its default clips are three seconds at 2 fps. Single-interval extraction smooths, subtracts the mean, then uses maximum-subarray search. Multi-interval extraction uses a clip-scale kernel and Otsu threshold. Its QVHighlights claim is 40.32 training-free moment-retrieval mAP, not a Charades R@1 result. Its appendix supplies a scoring implementation; its whole-video fallback is unsuitable for our no-match product behavior. [Paper, sections 3.2–3.3 and appendix A](https://arxiv.org/html/2608.04480v1).

**Adaptation.** Use a local open VLM on Sol to score only candidate neighborhoods produced by experiment 1. Require real Yes/No logits; a JSON field that asks the model to invent a probability is a different experiment. Keep all raw logits and token IDs. Then resample around uncertain edges at a finer temporal rate. Return estimated intervals separately from observed samples.

**Ablations.** Dense uniform inspection versus candidate-neighborhood inspection at equal decoded frames and model forward passes. Continuous versus binary score. Fixed finer sampling versus uncertainty-based sampling. Do not compare a full sweep against two old calls and call it a controller gain.

**Priority.** After testing the cheap score curve. More coverage and local motion evidence may help; extra calls alone can also explain a gain. A failed old sparse check does not prove this dense recognition approach will fail.

### 4. Negative-aware training and calibrated multimodal ranking

**Evidence.** Moment of Untruth releases negative-aware versions of QVHighlights and Charades-STA with in-domain and out-of-domain negatives. Its UniVTG-NA has an added relevance head. The abstract reports average negative rejection of 98.4% with moment-retrieval recall within 3.87% of its positive-only setting. That rejection figure is not final search accuracy or proof about arbitrary CCTV absence. Its repository includes labels, feature links, and checkpoints. [Paper](https://arxiv.org/html/2502.08544v1), [official release](https://github.com/keflanagan/MomentofUntruth).

CG-DETR uses query-conditioned dummy tokens and clip-word correlation to reduce irrelevant cross-modal attention. Its official release provides trained features and checkpoints; its custom-video path supports a CLIP-only model. This is a more relevant design precedent than a classifier that selects one retrieval route too early. [Official method and release](https://github.com/wjun0830/CGDETR).

**Adaptation.** Keep visual and description candidate unions. Fit a small relevance and ranking head using training-only features such as visual score, caption similarity, reranker score, local temporal contrast, evidence disagreement, and sampling coverage. Use in-domain negatives that share objects/scenes, not only unrelated text. A changed caption is not a verified negative: reject ambiguous examples or use the released benchmark labels. Train a distinct no-match decision rather than thresholding a per-video normalized peak.

**Proof.** Compare each path, unweighted union, the existing rank fusion, learned ranking, and learned ranking with the rejection head. Report positive recall alongside ID/OOD false-positive rate, AUROC, and a frozen operating threshold. Add corpus-level tests in which the correct video is not supplied; keep those results separate from single-video Charades grounding.

**Priority.** After the basic learned grounder. This protects practical search behavior while we improve localization.

## Ideas not selected now

- More tools, a graph, or a router by itself: no measured localization failure here requires them.
- Full VLM reinforcement learning before a reproducible supervised head: higher cost and more failure modes; it does not repair missing visual observations.
- Caption-only expansion as the sole improvement: it can change retrieval rank, but it cannot reliably recover an unrecorded hand action or exact edge.
- A standard caption/vector/rerank cascade as a novelty claim: RefCap already separates dense caption construction from multi-granularity retrieval. [Author paper](https://doi.org/10.1109/ICASSP49660.2025.10888164), [official code](https://github.com/BUAAPY/RefCap). CorpusMR also publishes an event/subclip, transcript/visual/text retrieval cascade with VLM reranking and boundary refinement. Its 300-query ActivityNet corpus result is not directly comparable to our supplied-video pilot. [Author release](https://github.com/sgakula/VCMR).

## Possible contribution, still only a hypothesis

The promising direction is a **trained temporal scorer that uses both scene descriptions and dense visual evidence, rejects absent events, and spends source checks where they reduce boundary uncertainty**. Each part already has precedents. The combination is not automatically novel. A credible claim needs an exact difference from these methods, controlled gains over the strongest reproduced method, and an independent test of the claimed failure case.

Use two separate targets: higher official localization quality, and the same quality with less query-time work. Do not mix these claims. Publish negative results and candidate-oracle limits. Never report a gain from swapping to a stronger encoder as a gain from retrieval policy alone.

## Execution order and stop conditions

1. Reproduce current scores from saved outputs; calculate candidate oracle and boundary/ranking errors. Proof: complete query grid, same evaluator, no new calls.
2. Build the score-curve experiment and freeze a small development grid. Proof: exact tests for irregular timestamps, constant curves, gaps, short actions, repeated events, source bounds, and deterministic ties.
3. Reproduce UniVTG or FlashVTG with released features/checkpoints. Proof: feature identity, split identity, official evaluator, all queries retained. If release access fails twice, record it and use raw-video feature extraction or another verified release.
4. Run trained temporal-head ablations on Sol. Proof: train-only fit, source-disjoint validation, resumable checkpoints, measured throughput, three seeds, no test-based model selection.
5. Add recognition refinement and negative-aware ranking only if error analysis justifies each cost. Proof: paired source-group confidence intervals and equal-cost ablations.

For a long Sol job, report the submitted job ID, checkpoint/log paths, measured estimated finish range, and the user's completion-check command. Leave it running. Do not spend the session repeatedly tailing it.

## Access and protocol checks still needed

REZE appendix A.2 says the official Moment-DETR release made QVHighlights test labels public in commit `7c61a84` on 9 March 2026 after the server closed. Verify that official commit before relying on old notes about a hidden-test server. Raw video access remains a separate problem.

This note did not fetch model checkpoints, audit feature licenses, measure Sol memory/time, or run these methods. Stronger benchmark performance and novelty remain unproved.
