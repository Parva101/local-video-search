# Stronger temporal features: access review — 14 November 2026

Research only. No job was submitted, no model was loaded, and no full feature archive or checkpoint was downloaded. Checks used author source, metadata, bounded HTTP ranges and small label files. The current full-test job is separate; this note does not assume its final result.

## Decision

**The most complete stronger reference is now SDST.** Its actual checkpoint is public, its Charades labels match our current release byte for byte, and its intermediate features are accessible. It needs an isolated CUDA build gate before a training commitment.

**The smaller first representation experiment is InternVideo2-6B + Llama cached features from the FlashVTG release, used with our existing head.** The pair totals 2.239 GB, has pinned artifact hashes, and needs no 6B backbone in GPU memory for head training. This isolates representation value before adding another architecture. Its label/query mapping needs an explicit audit; direct qid reuse is wrong.

Do not copy the whole FlashVTG runtime into our Torch 2.11 / CUDA 12.9 environment. Its pinned TorchText dependency targets Torch 2.2.2. A same-head feature experiment can avoid that dependency. Treat the missing FlashVTG project license and incomplete 6B feature terms as unresolved distribution matters; do not package them as the app default.

These are launch candidates, not proven local improvements. One A100 80 GB is a reasonable gate allocation, not a measured memory or runtime guarantee.

## What the papers establish

FlashVTG reports Charades-STA R@1 at IoU 0.5 / 0.7 of **70.32 / 49.87** with InternVideo2-6B, versus **60.11 / 38.01** with SlowFast + CLIP. Its reported training time of about 1.5 hours on one RTX 4090 is for **150 QVHighlights epochs**, not a Charades runtime estimate. Its architecture combines a temporal pyramid and score refinement. [Author paper, Table 3 and section 4.3](https://openaccess.thecvf.com/content/WACV2025/papers/Cao_FlashVTG_Feature_Layering_and_Adaptive_Score_Handling_Network_for_Video_WACV_2025_paper.pdf)

SDST reports **72.0 / 52.6**, with **61.2 mIoU**, using InternVideo2-1B intermediate features. This is a different head and representation from FlashVTG, so the difference cannot be attributed to architecture alone. [Author paper, Table 2](https://arxiv.org/html/2507.07744v1)

Our current control already contains SlowFast motion and CLIP features. Calling it a still-image-only model would be wrong. The hypothesis is that stronger video-language pretraining or intermediate features improve semantic separation and interval quality. The FlashVTG feature comparison supports testing this; it does not prove our current failure is a representation limit.

## Pinned source releases

| Project | Commit checked | Access |
| --- | --- | --- |
| FlashVTG | `25b95916feed900038fa762985c196ee14f16c59` | Public source and metadata |
| SDST | `ea8fa9fe1158c0bcdb60df2861450f4b69362f3e` | Public source, metadata and checkpoint bytes |

[FlashVTG source](https://github.com/Zhuo-Cao/FlashVTG/tree/25b95916feed900038fa762985c196ee14f16c59), [SDST source](https://github.com/davidpujol/SDST/tree/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e). Pins were resolved through the GitHub commit/tree APIs on the date above. Do not follow moving `main` branches in a run.

## FlashVTG feature access: verified

Both main datasets are public and ungated. HF metadata gives the following immutable revisions, sizes and LFS SHA-256 identities. A 512 KiB prefix request to each returned HTTP **206** with the expected full length. The payload prefix is plain **TAR**, despite its `.tar.gz` name. Do not force gzip decoding.

| Artifact | Pinned revision | Bytes | Content check |
| --- | --- | ---: | --- |
| InternVideo2-6B Charades video | `71606b179beddafee6f3cd0b500eb573f2031c7a` | 460,646,400 | `charade_sta_6b/*.pt`; first tensor fp16, shape `(26, 768)` |
| Llama Charades query | `d51739ff4ed94d0342d8a468b17621812f0881b2` | 1,778,278,400 | `charade_sta_llama_text_feature/qid*.pt`; first tensor fp16, shape `(13, 4096)` |
| Optional InternVideo2-1B video control | `2378c8a05383efdbfd39ed267006f25088712685` | 460,646,400 | Metadata checked; payload not probed |

Direct pinned downloads:

- [6B video archive](https://huggingface.co/datasets/cg1177/charade_sta_internvideo2_videoclip_6b_w1s/resolve/71606b179beddafee6f3cd0b500eb573f2031c7a/charade_sta_internvideo2_videoclip_6b_w1s.tar.gz)
- [Llama query archive](https://huggingface.co/datasets/cg1177/charade_sta_internvideo2_llama_text_feature/resolve/d51739ff4ed94d0342d8a468b17621812f0881b2/charade_sta_internvideo2_llama_text_feature.tar.gz)
- [1B video archive](https://huggingface.co/datasets/cg1177/charade_sta_internvideo2_videoclip_1b_w1s/resolve/2378c8a05383efdbfd39ed267006f25088712685/charade_sta_internvideo2_videoclip_1b_w1s.tar.gz)

```text
6B video LFS SHA-256
05d7073557e4019d8c51c8c8a56bc8aebd67ac4e9ef63dd4784ff1c21c9df680
Llama text LFS SHA-256
2e1445f6f6ea1c80369c81f956cf094a5af0d92f6853a2e9424c12436a927e17
1B video LFS SHA-256
338cc62d184ea5d262a049008a8281b8bdf929a3cc3b9cf78819d65e1fff3842
```

The sample tensor checks inspected serialization opcodes with `pickletools`, without executing a pickle. Only the first member was checked; this is not a full-array validity or coverage audit. Full preparation must check hashes, safe archive members, tensor-only loading, finite values, widths, all qids and all sources. [6B author dataset](https://huggingface.co/datasets/cg1177/charade_sta_internvideo2_videoclip_6b_w1s), [Query dataset](https://huggingface.co/datasets/cg1177/charade_sta_internvideo2_llama_text_feature)

### Labels and split

The pinned FlashVTG source includes complete train/test JSONL files with `qid`, `query`, `duration`, `vid` and `relevant_windows`. Bounded downloads parsed successfully:

| Split | Queries | Videos | Bytes | SHA-256 |
| --- | ---: | ---: | ---: | --- |
| Train | 12,404 | 5,336 | 1,616,506 | `bcb0deddbb552354323a26dd39d3d9f2fe6d9b70fd9e51697344317364962442` |
| Test | 3,720 | 1,334 | 488,238 | `13d6e9152794d87bb501a827edcbe69e5c0428f0af60e926e6b87e4f452ad5b2` |

All parsed intervals satisfy `0 <= start < end <= duration`. Source sets equal the current UniVTG processed release, but **qids do not overlap**: FlashVTG uses integers. Source/query multisets share 12,380 train and 3,713 test entries; 24 train and seven test strings differ. Never pair Llama query features by row order or our current qid string. Keep native query identities and build a checked source/query correspondence. Keep discrepancies visible. [Train labels](https://github.com/Zhuo-Cao/FlashVTG/blob/25b95916feed900038fa762985c196ee14f16c59/data/charades_sta/charades_sta_train_tvr_format.jsonl), [Test labels](https://github.com/Zhuo-Cao/FlashVTG/blob/25b95916feed900038fa762985c196ee14f16c59/data/charades_sta/charades_sta_test_tvr_format.jsonl)

The official recipe evaluates on the test file each epoch under the name `val`. Replace this with our existing source-disjoint development source set for model selection. Freeze once, then evaluate the complete declared test release. A different metadata release must keep a separate label identity.

### Runtime, recipe and checkpoint limits

The Charades recipe specifies visual width 768, text width 4096, 1-second steps, batch 32, 50 epochs, learning rate 1.5e-4, weight decay 1e-4 and NMS 0.7. It is a head-training recipe; cached features avoid loading the backbone. [Pinned recipe](https://github.com/Zhuo-Cao/FlashVTG/blob/25b95916feed900038fa762985c196ee14f16c59/FlashVTG/scripts/charades_sta_internvideo2/train.sh)

Source hazards to address explicitly before a faithful reproduction:

- `max_v_l=-1` reaches `array[:self.max_v_l]` in the active loader, removing the final feature step. Preserve this only as a labelled exact-source control; our full-coverage experiment should retain every step and declare that difference.
- Loader exceptions select NPZ/PT/NPY alternatives. Strict preparation must establish one actual format and raise on corruption, rather than turn a malformed file into another-format attempt.
- The training path imports TorchText unconditionally. The requirements pin Torch 2.2.2 and TorchText 0.17.2; PyTorch identifies these as a compatible pair. That is not a Torch 2.11 compatibility promise.
- Attention code uses private PyTorch imports. Its `torch._overrides` import is only a fallback after the public `torch.overrides` import; do not report it as a certain failure. Import and forward/backward gates are still needed.
- No custom CUDA extension was found in FlashVTG's own model/blocks tree. `nncore` 0.4.2 supplies temporal IoU in Python. TorchText is the relevant binary dependency, not a FlashVTG deformable-attention build.

[Loader](https://github.com/Zhuo-Cao/FlashVTG/blob/25b95916feed900038fa762985c196ee14f16c59/FlashVTG/start_end_dataset.py), [Requirements](https://github.com/Zhuo-Cao/FlashVTG/blob/25b95916feed900038fa762985c196ee14f16c59/requirements.txt), [PyTorch release compatibility](https://github.com/pytorch/text/releases/tag/v0.17.2), [Attention source](https://github.com/Zhuo-Cao/FlashVTG/blob/25b95916feed900038fa762985c196ee14f16c59/FlashVTG/attention.py), [nncore release](https://pypi.org/project/nncore/0.4.2/).

The README links a [Charades checkpoint/log folder](https://www.dropbox.com/scl/fo/vxzx7o6221w35wx58655k/AN0tWBPRsvW9akunEYFSO0U?rlkey=8yt1guzfqqybiim4l5nfw4siy&dl=0). Its public page returned HTTP 200 with the expected Charades-IV2 title, but did not expose file names to the static check. **Checkpoint bytes, size and config remain unverified.** Do not make a later launch depend on this link without a download gate.

The pinned tree has no project-root license. `data/LICENSE` is CC BY-NC-SA 4.0. HF marks the 1B video dataset Apache 2.0 and the text dataset MIT; the 6B dataset has no license card. These artifact-specific facts do not grant a blanket license for code, weights, underlying video and all features. [Data terms](https://github.com/Zhuo-Cao/FlashVTG/blob/25b95916feed900038fa762985c196ee14f16c59/data/LICENSE), [1B card](https://huggingface.co/datasets/cg1177/charade_sta_internvideo2_videoclip_1b_w1s).

## SDST access: verified

The current GitHub tree contains the real **53,916,069-byte** Charades checkpoint. A 4 KiB request returned HTTP 206 and a PyTorch ZIP prefix, not a Git LFS pointer. This corrects the earlier access uncertainty. The full checkpoint was not fetched or loaded. [Pinned checkpoint](https://raw.githubusercontent.com/davidpujol/SDST/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/checkpoints_sdst/checkpoint_charades_sta.pth)

The author's public [data_sdst.zip](https://drive.google.com/file/d/1VPz-wrreNWHbTywUrNHvavODKMjZQWP9/view) is **27,292,943,823 bytes**. Confirmation-aware download access returned HTTP 206 for bounded ranges. Its ZIP64 directory contains 67,378 entries; the directory is 8,550,113 bytes at offset 27,284,393,612. Directory SHA-256: `1ca3225f100b87fe93a4dd72254caefb95e76db2750eac1fd046c537d7dff082`.

This check read the directory, two small feature members, and the two small Charades label files; it did not download the archive. Unused datasets need not be extracted.

| Charades content | Files | Compressed bytes | Uncompressed bytes | Sample verified |
| --- | ---: | ---: | ---: | --- |
| `vid_feats/*.npz` | 9,848 | 4,194,920,957 | 4,529,928,048 | `visual_feats_interm_pooled`: float32 `(34, 5, 768)` |
| `txt_feats/*.npz` | 16,124 | 2,587,503,635 | 2,773,600,696 | `text_feats`: float32 `(5, 11, 1024)` |

Those are first-member shapes, not fixed lengths. The model takes the last four intermediate levels. Visual time and query token lengths vary. This is **not** the same representation as FlashVTG's final 768-dimensional video and 4096-dimensional Llama query tensors. [Loader contract](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/datasets/grounding.py), [Model dimensions](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/models/model.py)

The embedded Charades label files are **byte-identical to the current UniVTG processed labels**: train 12,404 queries, test 3,720. Their SHA-256 values are `cc061d290f5be0735ecfaf80d9f9d09a5032f8b95faef114fe6ce21add2df9aa` and `fbf26493b5b1b7c08e3cb0b79e3ef400709229205cfea24745798292ba7eb7d6`. Our current video-disjoint split therefore transfers without query remapping. The four canonical training omissions remain; these do not become a canonical 12,408-query reproduction.

### Integrity and preprocessing limits

Google's range response supplies `Last-Modified` and byte ranges, but **no ETag**. Our current strong-ETag range reader cannot be reused without changing its contract. Do not silently remove that check. A full archive snapshot followed by a recorded SHA is the simplest strong local input; a selective range importer needs a separate, reviewed identity/publication design. Directory SHA plus per-member CRC is useful evidence but not an author-supplied full-archive cryptographic identity.

Charades payload alone is about **6.782 GB compressed**, before selecting only the actual train/test source set. The ZIP has Apple `._` entries and directory records. Exclude metadata explicitly and validate member paths/types/CRC before atomic publication.

The stock loader filters videos shorter than five seconds, truncates feature time by integer duration, clamps labels, swaps reversed endpoints and widens sub-second targets. A strict local release must report these preprocessing differences and counts; it must not silently call them raw benchmark annotations. The stock config also names the test file as `val`. [Dataset config](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/configs/_base_/datasets/charades.py), [Loader](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/datasets/grounding.py)

### One-A100 runtime gate

The author Dockerfile pins PyTorch 2.2.1 / torchvision 0.17.1 in a CUDA 12.1 development image; it also installs nncore 0.4.2, CLIP, einops, scikit-learn and wandb. It is a starting reference, not a verified lock for our newer container. The model's actual cached-feature path must first pass imports; eager dataset imports still pull in CLIP and torchvision. [Dockerfile](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/Dockerfile)

Only **ROIAlign1D** is enabled in the extension build. The active temporal deformable attention uses PyTorch `grid_sample`; its CUDA extension is commented out. The ROI kernel uses legacy THC headers, `input.type()` dispatch and `.data<>()`. The repository's bundled `.so` is CPython 3.12-specific and tied to its build environment. Do not reuse it in Torch 2.11. Rebuild from source in an isolated matching development container, then test forward/backward numerics and checkpoint loading. No build was attempted here, so compatibility failure is a risk, not a measured result. [Extension setup](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/models/ops/setup.py), [ROI kernel](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/models/ops/roi_align/src/roi_align_kernel.cu), [Active deformable attention](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/models/ops/temporal_deform_attn/temporal_deform_attn_ours_key_based.py)

The code has a BSD 3-Clause root license; individual borrowed files also retain notices. Preserve them. Dataset and feature redistribution rights remain separate. [License](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/LICENSE)

## Conditional experiment order

1. Finish and inspect the current frozen full-test run. Do not change its sources or choose new parameters from its test scores. Root later reported that this completed and justified a stronger-feature stage; this research worker did not audit those result files.
2. Prepare SDST's complete immutable local archive snapshot and pinned checkpoint in a new private research directory. Its identical processed labels make it the cleaner strong released-model reference. Validate all required Charades features before GPU work.
3. Gate SDST's isolated ROI build, forward/backward, released-checkpoint inference and full validation-source coverage. Use its native intermediate features and published decode as the reference. Train-only validation must select later adaptations.
4. Keep the smaller FlashVTG feature experiment as a second path. Audit native qids/query text/interval mapping, then compare the existing head on old versus stronger features. Use the same development **videos**, preserve all feature steps, and record representation/parameter-count differences. If query releases differ, report them and give a matched-query diagnostic; do not silently omit difficult test queries.
5. Estimate full training time from a complete epoch plus validation and checkpoint save, including the slowest configured sequence. Only then submit a resumable long run. Report the job and leave it running for the user; no repeated tailing.

Do not report the paper's 70.32% or 72.0% as our result. A feature-only gain is useful engineering; it is not a novel method. A credible stronger claim needs a same-data ablation and a later corrected-label or independent-video evaluation.

Unrun: full artifact hash verification, all-member coverage/shapes, checkpoint deserialization, Torch 2.11 / CUDA 12.9 imports or extension builds, GPU memory/runtime, and any new benchmark. No SOTA or improvement claim follows from this access review.

## Concrete SDST launch handoff

CPU preparation should precede the GPU reference gate. This is an input/compatibility experiment, not a new training method.

### Exact source and data identities

```text
Source repository: https://github.com/davidpujol/SDST
Source commit: ea8fa9fe1158c0bcdb60df2861450f4b69362f3e
Google Drive file ID: 1VPz-wrreNWHbTywUrNHvavODKMjZQWP9
Author archive view: https://drive.google.com/file/d/1VPz-wrreNWHbTywUrNHvavODKMjZQWP9/view
Initial download endpoint: https://drive.usercontent.google.com/download?id=1VPz-wrreNWHbTywUrNHvavODKMjZQWP9&export=download
Expected full archive bytes: 27292943823
ZIP64 central-directory offset: 27284393612
ZIP64 central-directory bytes: 8550113
ZIP64 central-directory SHA-256: 1ca3225f100b87fe93a4dd72254caefb95e76db2750eac1fd046c537d7dff082

Pinned checkpoint URL:
https://raw.githubusercontent.com/davidpujol/SDST/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/checkpoints_sdst/checkpoint_charades_sta.pth
Checkpoint bytes: 53916069
Checkpoint Git blob SHA-1: 5da678c2633f80c77ae3b2f5cf1eb4d645b7d326
```

The checkpoint Git blob hash is **not** a SHA-256 file digest. Verify it as SHA-1 of `b"blob 53916069\0" + payload`; also compute and record the actual payload SHA-256. No author full-archive or checkpoint SHA-256 was found in the checked sources. Do not invent an expected value. [Pinned checkpoint blob metadata](https://api.github.com/repos/davidpujol/SDST/git/blobs/5da678c2633f80c77ae3b2f5cf1eb4d645b7d326)

Verified archive prefixes and files:

```text
data/charades/charades_train.jsonl
data/charades/charades_test.jsonl
data/charades/vid_feats/<source-id>.npz
data/charades/txt_feats/<query-id>.npz
```

Use those prefixes, not an assumed `data_sdst/` root. Local headers for the two probed feature members confirm them. Directory entries are not examples, and Apple `._` entries are not labels or tensors.

### Safe CPU preparation

1. Make a fresh private namespace, separate from `strict-head-v3` and production indexes. Check available scratch space for the 27.3 GB archive, selected 7.3 GB uncompressed Charades features, source/checkpoint and temporary publication. Reserve more if keeping extraction backups.
2. Fetch the confirmation form, then stream **one complete response** to a new `.partial` file. Reject HTML, unexpected content type, wrong length or incomplete ZIP. Because no strong ETag exists, do not append stale partial data or claim that multiple unbound range requests make one immutable archive. On a failed stream, preserve its failure evidence and restart a new attempt with bounded backoff.
3. Hash the whole completed archive. Check its exact byte length and the independently observed central-directory hash above. Record the full SHA-256 as the new local release identity before extraction. The directory check binds membership/CRC metadata; it does not replace reading and hashing all bytes.
4. Use the local ZIP64 file for selection. Check all selected paths, duplicate names, file modes, links, encryption flags, decompressed sizes and CRC. Extract only native Charades label/feature files into staging; do not use unrestricted `extractall`. Preserve every source/query required by the declared split.
5. Check the two known label SHA-256 values and complete row counts. Use `numpy.load(..., allow_pickle=False)` for every required NPZ. Validate keys, finite float values, temporal/token lengths, five stored levels, widths 768/1024 and unique file coverage. Missing or invalid examples must raise; no zero vectors, skips or format fallbacks.
6. Fetch the checkpoint to a separate staged file, check length and Git blob identity, then record its file SHA-256. Do not deserialize it during network download. Publish only after all manifest and feature checks pass, using atomic rename and no overwrite of prior runs.
7. Save source file hashes, archive/member identities, label identities, selected source/query counts, software versions and validation results in a new immutable preparation report. Reuse the current video-hash training/development split because the labels match byte for byte. Keep test labels out of epoch selection.

CPU preparation needs the standard library plus NumPy for these NPZ checks. It needs no GPU and no InternVideo backbone weights. Exact archive member CRCs and the final full-file SHA must come from that snapshot, rather than this metadata-only review.

### Exact official runtime and first GPU check

The official Charades entry is:

```bash
python tools/launch.py configs/charades/sdst_charades.py \
  --checkpoint checkpoints_sdst/checkpoint_charades_sta.pth --eval
```

It expects source mounted at `/SDST`, input data under `/data/charades`, and creates `/SDST/model_results/<exp_name>`. `--work_dir` is parsed but its value is not used in the checked launcher. Mount a fresh work directory at the actual path; do not assume the flag isolates outputs. The code calls the config file positionally, despite one README example using `-c`. [Launcher](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/tools/launch.py)

The Charades override is 50 epochs, batch 32, AdamW learning rate 2.5e-4, weight decay 1e-4, decay at epoch 30, and linear NMS. The base supplies 2,000-step warmup and gradient clipping at norm 35. The model config selects `internVideo-1B`, hidden width 256 and four intermediate side-tuner levels. These settings must accompany the checkpoint; a generic FlashVTG feature wrapper is not compatible. [Schedule](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/configs/_base_/schedules/default_np.py), [Charades override](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/configs/charades/sdst_charades.py), [Model config](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/configs/_base_/models/model_charades_tacos.py)

The author extension build is:

```bash
cd models/ops
python setup.py build_ext --inplace
```

Use a CUDA **development** image with a matching `nvcc`, headers and compiler. The author Docker reference is Torch 2.2.1 / CUDA 12.1 / cuDNN 8, Python 3.12, torchvision 0.17.1, nncore 0.4.2, CLIP commit `a1d0717`, ffmpeg-python 0.2, scikit-learn 1.4.1.post1, wandb and einops. It has unpinned transitive packages; save the resolved environment. Do not install that stack into the running app or replace the current frozen campaign environment.

Gate on one A100: import model/dataset/ROI op; run ROI forward/backward against a small checked fixture; load the pinned checkpoint strictly; run representative shortest/longest and padded batches; score all development sources; save/reload state if training follows. Record device, peak memory and complete-stage timing. Do not start a 50-epoch job merely because a 53.9 MB checkpoint fits. Two failures on one step require a written re-plan, not an automatic port of all CUDA kernels.

The current feature access wrapper is the pinned `datasets/grounding.py`: it reads cached NPZs, keeps the last four of five levels, and sends them through `models/model.py`. Those two files, the model config and the ROI op form the boundary of the first reference gate. Keep its raw scores/predictions separate from any later adaptation and preprocessing changes.
