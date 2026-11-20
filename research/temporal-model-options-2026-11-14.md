# Temporal model options — 14 November 2026

Research only. No model was run for this note. Sources are papers, author code, and author model cards. Scores below belong to the named paper protocol; they are not measurements of this application. The old 69-query pilot is exploratory and cannot establish a full-benchmark win.

## Recommendation

Build a learned temporal-grounding path beside archive retrieval. First reproduce a released feature-based model. Then train one focused adaptation with an untouched evaluation split. Keep the general VLM for visual verification and complex language. Do not make fluent timestamp output the sole boundary signal.

Start with UniVTG as the low-friction trained control and TD-DETR as the first training baseline. SDST with InternVideo2 features is the stronger specialized reference. TimeLens2 is the current generalist reference worth testing on Sol. Binary VQA scanning is a separate inference experiment, not a reason to train a large model first.

This order is an engineering judgment. It favors reproducible weights, inexpensive trainable heads, and clear ablations over changes to prompts alone. Loading another author's checkpoint is a baseline, not a new contribution.

## Five candidates, ranked for the next experiments

### 1. UniVTG: released weights and reusable dense features

The ICCV 2023 paper reports full Charades-STA test R@1 at IoU 0.5 / 0.7 of **60.19 / 38.55**, and **52.17 mIoU**, with grounding pretraining followed by benchmark fine-tuning. Without that pretraining its scores are **58.01 / 35.65 / 50.10**. Its zero-shot result is **25.22 / 10.03 / 27.12**. Thus the supervised and zero-shot rows must remain separate. These are interval localization results, not archive-wide retrieval results. [Paper, Table 3](https://openaccess.thecvf.com/content/ICCV2023/papers/Lin_UniVTG_Towards_Unified_Video-Language_Temporal_Grounding_ICCV_2023_paper.pdf)

The authors provide downstream checkpoints and practical models. The model zoo distinguishes CLIP-only models from SlowFast R50 + CLIP B/32 models; use the matching extractor, checkpoint and config. The README's less-than-4-GB and subsecond claims are author claims, not measured end-to-end app costs. [Model zoo](https://github.com/showlab/UniVTG/blob/main/model.md), [README](https://github.com/showlab/UniVTG)

Charades feature downloads are listed as 1.3 GB SlowFast, 305 MB CLIP video, 178 MB CLIP text, plus metadata. This avoids raw-video decoding during head training. The code license is MIT; dataset and feature rights remain separate. [Data instructions](https://github.com/showlab/UniVTG/blob/main/install.md), [Code license](https://github.com/showlab/UniVTG/blob/main/LICENSE)

**Experiment:** reproduce the released model first. Then compare identical heads with cached motion features versus the current static image representation. Record feature-extraction time and storage separately. **Novelty risk:** high if the change is only a backbone swap. Training duration on our two A100s is unmeasured; time a fixed number of steps before estimating a full run.

### 2. TD-DETR: train against misleading context

The ICCV 2025 paper studies false associations between a query and its visual background. It changes training through video synthesis and temporal dynamics. Its full Charades-STA test result is **60.89 R@1 at IoU 0.5** and **40.35 at 0.7**, averaged over three runs. It reports about **six hours on one RTX 2080** for Charades training with pre-extracted features. This is a source result, not an A100 runtime promise. [Paper, Tables 2–3 and implementation details](https://arxiv.org/html/2501.07305v2)

Official code uses released Moment-DETR / CG-DETR features and a similarity matrix. The Charades recipe uses SlowFast+CLIP, a 256-dimensional hidden state, three encoder and decoder layers, batch 32 and 100 epochs. Its recipe points `eval_path` to the test file; do not copy that model-selection practice. Use a video-disjoint slice of the training split for selection. [Code and feature links](https://github.com/xyangzhou/TD-DETR), [Training recipe](https://github.com/xyangzhou/TD-DETR/blob/main/td_detr/scripts/charadesSTA/train_charades.sh)

Code is MIT. A released trained-checkpoint link was not established in the README reviewed here; training should not depend on one. [License](https://github.com/xyangzhou/TD-DETR/blob/main/LICENSE)

**Experiment:** train the official method as a control, then add one query-conditioned near-miss loss that separates a complete event from a visually similar partial event. Compare baseline, original synthesis, new loss, and both. **Novelty risk:** high: hard negatives and context suppression already exist. The proposed loss needs a prior-art check and a gain on independent data before any novelty claim.

### 3. SDST + InternVideo2: strong temporal features with a small trainable part

The 2025 SDST paper combines sparse interval prediction with dense refinement of frozen intermediate features. It reports **72.0 R@1 at IoU 0.5**, **52.6 at 0.7**, and **61.2 mIoU** on Charades-STA with InternVideo2 features. It trains Charades for 50 epochs at one feature step per second. The stated hardware is one RTX 6000 with fp16; A100 memory use and runtime remain unmeasured. These numbers are specialized supervised results, not zero-shot VLM results. [Paper, Table 2 and Appendix A](https://arxiv.org/html/2507.07744v1)

Official code offers a pre-extracted feature download and training/evaluation configs. It requires compiled deformable-attention / ROI operations. Evaluation examples name local checkpoint paths, but I did not verify an actual public checkpoint download. Feature archive size and successful download also remain unchecked. The repository license is BSD 3-Clause. [Official code](https://github.com/davidpujol/SDST), [Charades config](https://github.com/davidpujol/SDST/blob/main/configs/charades/sdst_charades.py), [License](https://github.com/davidpujol/SDST/blob/main/LICENSE)

**Experiment:** use SDST as a strong ceiling and compare its clip features against a CLIP-based trained head under the same data split. If it wins, test distilling its dense relevance and edge outputs into a smaller archive-time model. **Novelty risk:** side-tuning and distillation are established methods. The useful claim would be a measured accuracy–storage–latency tradeoff, not the existence of a second model.

### 4. TimeLens2: modern generalist grounder, including repeated intervals

The July 2026 paper trains interval-set prediction with supervised learning and temporal reward optimization. In its seven-benchmark protocol, the 8B model reports **68.0 R@1 at IoU 0.5 / 58.6 mIoU on Charades-TimeLens**, and **18.4 / 19.0 on Ego4D-NLQ**. Its seven-benchmark average mIoU is **48.0**. The corresponding 4B average is **47.7**. These corrected / long-video protocol scores are not comparable to original Charades-STA scores. [Paper, Table 1 and Appendix A.2](https://arxiv.org/html/2607.17423v1)

The official project provides 2B, 4B and 8B SFT and final checkpoints, SFT / GRPO code, and a 93,232-instance training dataset. Use a released small model first. The 8B card gives a native video input example with timing metadata; replacing that with our existing image-grid input is not a faithful reproduction. [Code and releases](https://github.com/MCG-NJU/TimeLens2), [8B model card](https://huggingface.co/MCG-NJU/TimeLens2-8B)

SFT documentation supports a configurable process count but uses a default global batch of 256. The GRPO recipe uses eight generations, batch 64 and a 16,384-token visual budget. Neither proves that an unchanged full recipe fits two A100s. First measure a forward pass and a training step with a fixed frame budget. [SFT guide](https://github.com/MCG-NJU/TimeLens2/blob/main/sft/README.md), [4B GRPO recipe](https://github.com/MCG-NJU/TimeLens2/blob/main/grpo/scripts/train_grpo_4b.sh)

**License discrepancy:** the README and HF card say Apache 2.0, while the repository `LICENSE` reviewed here contains TimeLens terms restricting academic use and EU use. Resolve the artifact-specific terms before packaging it as the default in a public product. Local ASU research evaluation is the intended use here. [README](https://github.com/MCG-NJU/TimeLens2), [Repository license](https://github.com/MCG-NJU/TimeLens2/blob/main/LICENSE), [Model card](https://huggingface.co/MCG-NJU/TimeLens2-8B)

**Experiment:** reproduce native 4B inference, then compare whole-video inference with archive retrieval followed by overlapping local video crops. Keep crop offsets in code and preserve all predicted spans. Test identical total frames and report the cost of misses outside retrieved crops. **Novelty risk:** retrieval plus a grounder is not new. A new contribution needs a repeatable gain in long-video evidence coverage under a fixed compute budget.

### 5. FV-Action: binary judgments instead of direct timestamp generation

The August 2026 preprint reports **56.8 R@1 at IoU 0.5 / 29.7 at 0.7** on Charades-STA with frozen Qwen2.5-VL-7B. It ranks first-token yes/no scores in coarse and fine scans, then emits a fixed-width window. It reports that threshold-derived boundaries, onset prompts and visual-change sampling performed poorly. The fixed output width depends on training-set event-length statistics; “training-free” does not mean free of dataset priors. The text has inconsistent descriptions of frames per probe, and I found no author implementation link in the paper inspected. Treat it as a design hypothesis that needs a declared reproduction protocol. [Paper](https://arxiv.org/html/2608.08315v1)

**Experiment:** obtain token logits from a local open model; compare fixed timestamp prompting, binary scanning with a fixed width, and a learned temporal head. Match frames, decoding work, and coverage. Do not replace first-token scores with a model's stated confidence. **Novelty risk:** this exact interface is now prior work. Useful extension: a learned duration / edge estimator tested against the paper's fixed-width control. No new checkpoint is required; base-model licensing applies. Runtime on Sol is unknown until measured.

## Important methods not chosen for the first training run

- **Time-R1:** released 3B/7B weights make it a useful inference baseline. The paper reports 60.8 R@1 at IoU 0.5 in its zero-shot Charades setting, but full RL training took 15 hours on eight A100s. It also states an ultra-long-video limit. Do not promise the same recipe on two GPUs. [Paper](https://arxiv.org/html/2503.13377v2), [Code and weights](https://github.com/xiaomi-research/time-r1)
- **TimeSuite, TRACE and VideoChat-Flash:** useful older grounded-VLM controls. The newer Time-R1 comparison reports original Charades R@1 at IoU 0.5 of 48.7, 40.3 and 53.1 respectively. These are the comparison paper's cited results, not independent reproductions. Prioritize one current released grounder over implementing all three. [Time-R1 comparison, Table 1](https://arxiv.org/html/2503.13377v2)
- **VideoMind:** its role-based LoRA agent is close prior art for a planner / grounder / verifier design. The official training guide defaults to eight devices and recommends A100 80 GB. It is a useful architecture reference, but adds several training stages before we know whether a simple learned head solves our main failure. [Official training guide](https://github.com/yeliudev/VideoMind/blob/main/docs/TRAIN.md)
- **CG-DETR, TR-DETR and EaTR:** established feature-based baselines; TD-DETR builds directly on this family and SDST supplies a stronger feature comparison. Reproducing every member is unnecessary for the first ablation. CG-DETR code and pretrained feature use are linked by TD-DETR. [TD-DETR code](https://github.com/xyangzhou/TD-DETR), [CG-DETR paper and code link](https://arxiv.org/abs/2311.08835)
- **InternVideo2.5:** improves rich and long visual context, but its general QA strength is not proof of interval precision. For our next feature experiment, the verified SDST result with InternVideo2 is more direct evidence. [InternVideo2.5 paper](https://arxiv.org/abs/2501.12386), [SDST paper](https://arxiv.org/html/2507.07744v1)
- **VideoPrism:** public video-text encoders are now available; the official code is JAX/Flax, with PyTorch support still listed as a TODO. It is an alternative motion representation, not a ready drop-in replacement for our PyTorch temporal head. Defer this extra runtime until a feature ablation justifies it. [Official repository](https://github.com/google-deepmind/videoprism)

## Benchmark correction changes the goal

TimeLens re-annotates temporal boundaries and reports large changes in model rankings. Its supplemental comparison gives Time-R1 **60.8 R@1 at IoU 0.5 on original Charades-STA**, versus **32.0 on Charades-TimeLens**; TimeLens-7B gives **39.8 versus 55.6**. A win only on old annotation geometry could fail the real use case. Keep original STA for literature continuity and corrected TimeLens as a separate evaluation, with pinned labels and the proper evaluator. [TimeLens supplementary Table 7](https://openaccess.thecvf.com/content/CVPR2026/supplemental/Zhang_TimeLens_Rethinking_Video_CVPR_2026_supplemental.pdf)

The TimeLens license restricts academic / production use, and its HF metadata is less specific. Keep benchmark files and outputs in research storage, and preserve terms rather than treating “public download” as permission for all redistribution. [Terms](https://github.com/TencentARC/TimeLens/blob/main/LICENSE)

## Proposed contribution and required ablations

The following are **our hypotheses**, not established improvements or novelty claims:

1. **Complete-event learning:** train a small query-conditioned head with positive interiors, edge-near examples and visually similar partial-event confusers. The key test is whether it beats the same head without those examples on source-disjoint data. Do not assume unlabelled events are negatives: sparse benchmark annotation does not establish absence.
2. **Learned crop allocation:** use the head to nominate multiple non-overlapping event candidates; spend native-video VLM work where candidate scores or boundaries disagree. Compare uniform crops and top-score crops at the same total frames, calls and wall time. Recall outside chosen crops must remain visible.
3. **Compact archive inference:** distill a stronger temporal model into the cached-feature path. Compare the teacher, unchanged student, and distilled student. Include all extraction, query encoding and refinement costs. Faster indexing with worse event recall is not a success by default.

Implement only after the first released control runs. If a plain trained head wins, first determine whether its gain comes from supervised labels, better features or temporal modeling; do not attribute all three to a controller.

## Stop rules and evidence needed

- Use train-video-disjoint development data. Freeze model selection and decoding rules before untouched evaluation. Preserve the old pilot, failed runs, source hashes and per-query traces.
- On Charades, report full R@1 at IoU 0.3 / 0.5 / 0.7 and mIoU. On repeated-span and long-video tasks, use each benchmark's actual multi-span evaluator. Do not silently score only the easiest occurrence.
- Compare both a **same-training / same-features control** and a **strong released grounder**. A win over our 42.03% small-pilot baseline is progress, not SOTA.
- Report video-group confidence intervals, multiple training seeds where feasible, absent-query false positives, event recall, and total cost. Use only verified absent examples.
- Run one short hardware test per training configuration. Save optimizer / scheduler / RNG state and checkpoint before the scheduler time limit. Predict runtime from measured steps; report long submitted jobs and leave them running, as requested.
- After two failures on the same step, preserve evidence and revise the plan. Stop adding components when the clean ablation cannot explain their value.

No weights, feature archives, licenses for downstream commercial distribution, training speed or benchmark reproduction were validated by execution in this note. Reported gains remain paper claims until reproduced under a fixed local protocol.

## UniVTG implementation handoff: verified small-file access

Pinned author commit: **`32659ac7aeba21742a63274f30eba785fc57e247`**, resolved from the [GitHub commit API](https://api.github.com/repos/showlab/UniVTG/commits/main) on 14 November 2026. The following checks read small public files or download landing pages only; no large feature archive or checkpoint was downloaded.

| Artifact | Author download | Observed content |
| --- | --- | --- |
| Training labels | [charades_train.jsonl](https://drive.google.com/file/d/1Ywo5A7wpdMfI9Ph9XllCMKi2PC-YJZZ9/view) | 1,829,259 bytes; 12,404 rows; 5,336 videos |
| Test labels | [charades_test.jsonl](https://drive.google.com/file/d/1Z6pElW_Gq-LeIlD-ptnyf7G6NeYE1FYW/view) | 548,707 bytes; 3,720 rows; 1,334 videos |
| Charades config | [opt.json](https://drive.google.com/file/d/1CBHPMvq2_nBWG7eAw9mIhYJbTLZan0kd/view) | 2,882 bytes; parsed successfully |
| Charades pretrained-and-tuned weights | [model_best.ckpt](https://drive.google.com/file/d/1rXxBhjsEvHYywvf--RIFMWJ1VV2ZdblX/view) | Author folder lists 520,351,563 bytes; payload unchecked |
| SlowFast features | [vid_slowfast.tar](https://drive.google.com/file/d/1JPkrJcpSwJqrGlq-aIW58UgxWRenVPVN/view) | Virus-scan confirmation HTML reached; binary unchecked |
| CLIP video features | [vid_clip.tar](https://drive.google.com/file/d/1JQGEz6jiizAccylBDZoMQQHMDwcQ7Nkv/view) | Virus-scan confirmation HTML reached; binary unchecked |
| CLIP text features | [txt_clip.tar](https://drive.google.com/file/d/1JYXjl0AnKHjDYb4_c-SUp4zq-_pXj_tU/view) | Virus-scan confirmation HTML reached; binary unchecked |

The author metadata folder also contains underscore-prefixed alternatives. Do not silently substitute them. The observed 12,404-row train file differs from the canonical 12,408-row count. Record that difference and audit all four missing examples before making a full-data reproduction claim. Both downloaded label files include `qid`, `query`, `duration`, `vid` and `relevant_windows`; labels are present, not hidden. No query text is reproduced here. [Author metadata folder](https://drive.google.com/drive/folders/1YuO1CPyWurjKZjGgHqX2m4mNrcr2Xstd), [Author checkpoint folder](https://drive.google.com/drive/folders/1xXw0QgJiW7m6lPX1dH-MFXU983IxJiG_)

Verified SHA-256:

```text
charades_train.jsonl cc061d290f5be0735ecfaf80d9f9d09a5032f8b95faef114fe6ce21add2df9aa
charades_test.jsonl  fbf26493b5b1b7c08e3cb0b79e3ef400709229205cfea24745798292ba7eb7d6
opt.json              2957f39e3d94448758945214402e8056046196258e5bc4f14602fe519c389519
```

Feature contract from pinned code: video NPZs have a `features` array, SlowFast width 2304 and CLIP width 512. Text NPZs have `last_hidden_state` or `pooler_output`, width 512. Temporal features are concatenated after per-stream normalization and alignment to their shorter length. `use_cache > 0` instead uses HDF5 caches. The stock loader catches absent query features and supplies zeros; our strict preflight must reject missing, non-finite or wrong-shaped arrays before a run. Training-path lookup is hard-coded by filename, so a source-disjoint split cannot be passed under an arbitrary filename without an explicit loader change. [Pinned dataset source](https://github.com/showlab/UniVTG/blob/32659ac7aeba21742a63274f30eba785fc57e247/main/dataset.py)

The real Charades config uses hidden width 1024, four encoder layers, eight heads, feedforward width 1024, 1-second clips, maximum video/text length 75, batch 32, 100 epochs, learning rate / weight decay 1e-5, input dropout 0.5, dropout 0, drop-path 0.1; loss weights b=10, g=1, f=10, intra=1, inter=0.5; score mode `add`, NMS 0.7, no time rounding. It points selection at original test labels. Keep that as provenance; select our adaptation on train-only development videos. [Downloaded opt.json](https://drive.google.com/file/d/1CBHPMvq2_nBWG7eAw9mIhYJbTLZan0kd/view)

The repository has no dedicated Charades shell script at this commit. The official entry point is `main/train_mr.py`; its published QVHighlights scripts are templates, not an exact Charades command. Reconstruct a Charades command from the linked config, with all settings saved. For checkpoint-only evaluation the documented flags are `--resume <checkpoint> --eval_init --n_epoch 0`. For a true training continuation, add `--resume_all`; otherwise only weights load. [Pinned train entry](https://github.com/showlab/UniVTG/blob/32659ac7aeba21742a63274f30eba785fc57e247/main/train_mr.py), [Pinned config / resume implementation](https://github.com/showlab/UniVTG/blob/32659ac7aeba21742a63274f30eba785fc57e247/main/config.py), [Official example](https://github.com/showlab/UniVTG/blob/32659ac7aeba21742a63274f30eba785fc57e247/scripts/qvhl_inference.sh)

Static import inspection gives a much smaller dependency set than the 325-line environment export. The model builder uses PyTorch, NumPy and SciPy. The stock train / dataset / evaluator path additionally imports tqdm, TensorBoard, h5py, nncore, pandas, transformers and scikit-learn. These are direct imports, not a tested install lock; transitive nncore dependencies must also resolve. A small strict loader around the unchanged model can avoid importing the legacy whole training stack. Keep that in an isolated research environment. [Model](https://github.com/showlab/UniVTG/blob/32659ac7aeba21742a63274f30eba785fc57e247/model/univtg.py), [Dataset](https://github.com/showlab/UniVTG/blob/32659ac7aeba21742a63274f30eba785fc57e247/main/dataset.py), [Train](https://github.com/showlab/UniVTG/blob/32659ac7aeba21742a63274f30eba785fc57e247/main/train_mr.py), [Eval utility](https://github.com/showlab/UniVTG/blob/32659ac7aeba21742a63274f30eba785fc57e247/eval/utils.py)
