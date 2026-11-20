# SDST runtime gate — 15 November 2026

Read-only source review. No package was installed, no shared library or checkpoint was loaded, and no Sol job was submitted by this worker. The source was checked out at `ea8fa9fe1158c0bcdb60df2861450f4b69362f3e` under ignored `.codex-backups/sdst-reference-20261115/upstream`. Its working tree is clean. Parent owns data preparation and the gate implementation.

## Choice

Use an isolated development container with **Torch 2.2.1 and CUDA 12.1**, then build ROIAlign1D from the pinned source. This is the smallest route that preserves the released model. Do not port the operator to Torch 2.11 before this check.

The parent directly checked the current Sol SIF: Torch 2.11.0+cu129, CUDA 12.9, Python 3.12, and `/usr/local/cuda/bin/nvcc` 12.9.86. nncore, CLIP, scikit-learn and wandb are absent; einops and torchvision are present. Its dispatch API differs from the active SDST code. An old Torch wheel inside that SIF would not establish a matching CUDA development toolchain.

The official Docker registry returned HTTP 200 for `pytorch/pytorch:2.2.1-cuda12.1-cudnn8-devel`. Metadata checked on this date:

```text
Immutable image: docker://pytorch/pytorch@sha256:42204bca460bb77cbd524577618e1723ad474e5d77cc51f94037fffbc2c88c6f
Manifest: Docker schema 2; linux/amd64
Image config SHA-256: 8a2cd2aba91fa1daef17b57f2cea623488c179d82a3166c67898289383553cd0
Compressed layer bytes: 9,063,269,507
CUDA_VERSION: 12.1.1
PYTORCH_VERSION: 2.2.1
```

Only the small manifest and config were fetched; no image layers were pulled. The base image's exact Python, compiler and installed package versions remain to be checked inside it. The author Dockerfile creates a separate Python 3.12 environment. Do not assume that the base image already uses Python 3.12. A fresh build for its actual Python is sufficient for tensor checkpoint inference. [Author Dockerfile](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/Dockerfile), [official registry manifest endpoint](https://registry-1.docker.io/v2/pytorch/pytorch/manifests/2.2.1-cuda12.1-cudnn8-devel).

## Compiler evidence

- `models/ops/setup.py` builds only `roi_align.Align1D`. It raises unless `torch.cuda.is_available()` and `CUDA_HOME` are both set. A CPU-only allocation cannot run this setup unchanged, even when `nvcc` is installed.
- The active source includes `THCAtomics.cuh` and `THCDeviceUtils.cuh`. Both still exist as forwarding headers in the official Torch 2.2.1 **and 2.11** source. `THC.h` is commented out. A missing `THC.h` is therefore not evidence of a build failure here.
- The active forward and backward dispatch call `AT_DISPATCH_FLOATING_TYPES(input.type(), ...)` and its gradient equivalent. Torch 2.2.1 has an overload that accepts `DeprecatedTypeProperties`. Torch 2.11 routes dispatch through the header-only implementation, whose `scalar_type` accepts `ScalarType`; the old overload is absent. This is a concrete source-level incompatibility. A compiler run has not yet measured it in the current SIF.
- `.data<T>()` and `.type().is_cuda()` are also legacy calls. Do not change them merely because they are old. First use the matching release. If a later port is approved, the public equivalents are `.data_ptr<T>()`, `.scalar_type()` for dispatch, and `.is_cuda()`; test both numerical values and gradients.
- The active deformable attention uses PyTorch `grid_sample`. Its separate CUDA extension is disabled. No second CUDA operator needs a build for this model.

[SDST setup](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/models/ops/setup.py), [ROI kernel](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/models/ops/roi_align/src/roi_align_kernel.cu), [Torch 2.2.1 dispatch](https://github.com/pytorch/pytorch/blob/v2.2.1/aten/src/ATen/Dispatch.h), [Torch 2.11 dispatch](https://github.com/pytorch/pytorch/blob/v2.11.0/torch/headeronly/core/Dispatch.h), [2.2.1 THC forwarding headers](https://github.com/pytorch/pytorch/tree/v2.2.1/aten/src/THC), [2.11 THC forwarding headers](https://github.com/pytorch/pytorch/tree/v2.11.0/aten/src/THC), [active deformable attention](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/models/ops/temporal_deform_attn/temporal_deform_attn_ours_key_based.py).

## Bundled binary: inspect, do not load

The source tree includes `models/ops/roi_align/Align1D.cpython-312-x86_64-linux-gnu.so`, 1,217,544 bytes, SHA-256 `a6de705936ced53e8ab50bca8beeee87c216632071aaa4b498c83c5f6d3c8249`. A standard-library ELF parse, with no dynamic loading, found:

```text
ELF64, x86-64, CPython 3.12 filename
NEEDED: libc10.so, libtorch_cpu.so, libtorch_python.so, libcudart.so.12,
        libc10_cuda.so, libstdc++.so.6, libgcc_s.so.1, libc.so.6
RPATH: /opt/conda/envs/main/lib
Version strings include: GLIBC_2.32, GLIBCXX_3.4.29, CXXABI_1.3.13
Visible PTX: .target sm_86
```

The checked-in `build.ninja` sets `_GLIBCXX_USE_CXX11_ABI=0` and includes `sm_80` and `sm_86` cubin targets, plus `compute_86` PTX. Thus visible `sm_86` PTX alone does **not** prove that A100 support is absent. Neither the file name nor these strings establish compatibility with the current Torch build. Rebuild into a fresh execution copy; keep the upstream binary as evidence. Never load it to discover whether it works. [Bundled build record](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/models/ops/build/temp.linux-x86_64-cpython-312/build.ninja).

## Imports and checkpoint

There are three useful boundaries:

1. **ROI alone:** Torch, setuptools, a compatible CUDA development toolchain, and the build tools. Put the fresh execution copy's `models/ops` on the import path and import its ordinary `roi_align` package. This avoids the parent `models/__init__.py` import chain. It does not require CLIP, nncore, torchvision, wandb or any features.
2. **Model and checkpoint:** nncore 0.4.2, its normal package dependencies, SciPy and einops. `models/__init__.py` imports the loss and Hungarian matcher even for inference, so SciPy is needed. Load `configs/_base_/models/model_charades_tacos.py` through `nncore.Config.from_file`, then `build_model(cfg.model)` without a parallel wrapper. This imports the normal model registry but no SDST datasets. Do not inject fake modules or replace imports.
3. **Native dataset and launcher:** full `configs/charades/sdst_charades.py` also imports `datasets`. Its eager imports require CLIP and torchvision, although the cached Charades path calls neither the CLIP encoder nor tokenization. The evaluator imports scikit-learn. The launcher imports `nncore.engine`, which also imports torchvision and TensorBoard. Wandb is imported only when its writer is constructed; the supplied runtime config has no WandbWriter. ffmpeg is not used by the cached path.

Use the author package versions where declared: nncore 0.4.2, torchvision 0.17.1, scikit-learn 1.4.1.post1 and CLIP commit `a1d071733d7111c9c014f024669f959182114e33`. Keep NumPy on 1.26.x for this old Torch stack and resolve a compatible OpenCV package; do not let a current resolver silently replace Torch or force NumPy 2. Record all resolved versions and artifact hashes in the private runtime manifest. The nncore 0.4.2 source archive SHA-256 is `d486d23d5951b0843b6835b08ea9ff3a0f3309ecf623f944a46e8b4fc2b770ce`. This review did not install or validate that environment. [nncore release metadata](https://pypi.org/pypi/nncore/0.4.2/json), [SDST model imports](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/models/__init__.py), [dataset imports](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/datasets/grounding.py), [launcher](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/tools/launch.py).

For the fresh image, these are the smallest direct package pins for the native cached dataset, model and evaluator path:

```text
numpy==1.26.4
nncore==0.4.2
scipy==1.12.0
scikit-learn==1.4.1.post1
opencv-python-headless==4.9.0.80
einops==0.7.0
ftfy==6.1.3
regex==2023.12.25
tqdm==4.66.2
```

Revision, 19 November 2026: the pinned Torch 2.2.1 image ships no `libGL.so.1`, so the `opencv-python` import probe failed explicitly (job 1609446). The isolated runtime now pins `opencv-python-headless==4.9.0.80`: same upstream version, no GUI library. The cached server-side paths do not use highgui.

Install into new private `ROOT/runtime-python`, using that image's Python, not the app environment. PyPI release metadata confirms each pin exists and supports Python 3.10; compiled packages have Linux x86-64 wheels, except nncore, which is a source archive. These pins are a direct dependency list, **not a complete lock**. Resolve and save every transitive package and hash before publication. nncore declares h5py, joblib, jsonlines, NumPy, PyYAML, requests, tabulate, TensorBoard, termcolor and OpenCV dependencies; it does not declare Torch or torchvision. This allows ordinary resolution of the list above without adding a new Torch. Explicitly verify the imported Torch remains 2.2.1 and torchvision remains 0.17.1 from the base image.

Install the separately pinned CLIP source with `--no-deps` into the same target: its declared Torch and torchvision requirements must not cause another install. ftfy, regex and tqdm above supply its extra runtime imports; Pillow and packaging must pass an import check in the base environment. Use `WANDB_MODE=disabled` for the gate. Omit ffmpeg and wandb. No cached path uses ffmpeg, and no active config constructs WandbWriter. Do not supply stub modules. [NumPy pin](https://pypi.org/pypi/numpy/1.26.4/json), [SciPy pin](https://pypi.org/pypi/scipy/1.12.0/json), [scikit-learn pin](https://pypi.org/pypi/scikit-learn/1.4.1.post1/json), [OpenCV pin](https://pypi.org/pypi/opencv-python-headless/4.9.0.80/json), [CLIP requirements](https://github.com/openai/CLIP/blob/a1d071733d7111c9c014f024669f959182114e33/requirements.txt).

The full public checkpoint was obtained by the pinned checkout. Its byte count is 53,916,069. Both its expected Git blob hash and its new payload hash match:

```text
Git blob SHA-1: 5da678c2633f80c77ae3b2f5cf1eb4d645b7d326
Payload SHA-256: 2ed447770f3875536b454a5d0fe3367ba2828a74561a74c78f1952eace6f5698
```

`pickletools` inspected its ZIP member `epoch_36/data.pkl` without executing pickle. Globals are limited to `collections.OrderedDict`, `torch.FloatStorage` and `torch._utils._rebuild_tensor_v2`. Top-level strings include `meta` and `state_dict`; metadata records epoch 36, iteration 13,968, nncore 0.4.2, and the declared Charades optimizer/NMS values. **Its saved warmup is 500 steps; current source default is 2,000.** Do not claim the published checkpoint was trained with the current default. This difference does not change inference but matters for a later training reproduction. Use `torch.load(..., map_location='cpu', weights_only=True)` and `model.load_state_dict(checkpoint['state_dict'], strict=True)` in the isolated gate. nncore's checkpoint loader defaults to `strict=False`, so the launcher's success alone is not a strict state check. [Pinned checkpoint](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/checkpoints_sdst/checkpoint_charades_sta.pth), [nncore 0.4.2 source archive](https://files.pythonhosted.org/packages/43/e7/c10d8362b4e5560a2ca21e3a05f9ba3deca65c64ea61f28f4dfd288eae5c/nncore-0.4.2.tar.gz).

## Input and evaluation invariants

- Keep the native `internVideo-1B` model, hidden width 256, four side-tuner levels, five learned prediction queries and the released actionness head. The ROI output width is 16, sampling ratio is 0, and proposal expansion is 1.5.
- Video NPZ input is `visual_feats_interm_pooled`, stored as `(T, 5, 768)`. Native loading takes `[:int(duration * fps)]`, moves levels before time, then selects the last four levels. Query NPZ `text_feats` is `(5, L, 1024)`; loading takes the last four levels, and the model removes the first token. Native fps is 1. Features must be finite before padding. Native padding is positive infinity; the model derives masks from it and replaces padding values with zero. Do not pad with zeros and then infer masks from finiteness.
- Test inference requires batch size one. Multi-item padded batches belong in a separate training/loss gate. The denoising code calls `.cuda()` even at inference, so CPU model inference is not a supported check of unchanged source.
- Native training alone has `min_video_len=5`; native validation has **no** such filter. Grounding's boundary binding clamps to feature coverage, swaps reversed endpoints and widens targets shorter than one second. These operations create training targets. They do not modify the raw `label` record used by the evaluator, which reloads the label file. Report target changes and counts; score against the frozen raw labels.
- Native decoding converts normalized center/width to endpoints, clamps to `[0,1]`, scales by the original duration, and ranks by `sqrt(P(action) * predicted_actionness)`. Dataset postprocessing rounds valid endpoints to 0.1-second units and applies linear soft NMS. Preserve this sequence for the released reference.
- `vtg_eval` defaults to `match_number=True` and checks qid sets. Add explicit row count and qid uniqueness checks: a set check alone cannot detect duplicate rows. Keep every declared evaluation query. Never use `match_number=False`, drop missing features, or widen raw ground truth to make a run pass.
- The stock `val` file is the full test release. For development, point a new external gate config at the existing source-disjoint train-derived validation labels and features. Do not edit upstream configs. Keep the released checkpoint reference labelled as such; it already used the author's test-selection procedure. Do not claim untouched-test selection.

[Model contract and decode](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/models/model.py), [Charades config](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/configs/_base_/datasets/charades.py), [native loader/postprocessing](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/datasets/grounding.py), [evaluator](https://github.com/davidpujol/SDST/blob/ea8fa9fe1158c0bcdb60df2861450f4b69362f3e/datasets/eval/evaluation.py).

## One short gate

Prepare the pinned runtime image and dependency manifest in allocated CPU preparation, separate from the running app. Then request **one A100, four CPU cores, 32 GB host RAM, 30 minutes** for this gate. This allocation is an estimate, not a measured need. Use `apptainer exec --cleanenv --nv`; forward Slurm's `CUDA_VISIBLE_DEVICES` through the established container pattern.

1. Record device/driver, Python, Torch/CUDA, nvcc, C++ compiler, library ABI and package versions. Check the pinned source hashes and strict checkpoint identity. Use a fresh execution copy with upstream `.so`, object files and `build/` excluded, and preserve their originals. Fail on source changes or an unexpected imported module path.
2. Build the unchanged ROI source with `TORCH_CUDA_ARCH_LIST=8.0`, bounded build parallelism and a fresh build directory. The unchanged setup needs a visible GPU. Keep complete stdout/stderr and the generated compiler commands. Allow at most 15 minutes for build.
3. Import the freshly built `roi_align` package and verify its library path. Test float32 and float64 forward/backward against a small scalar interpolation reference. Include fractional, clipped, degenerate, empty and overlapping ROIs; check batch isolation and non-contiguous input. Use the kernel's exact sampling and edge rules, not generic 2D torchvision ROIAlign defaults. Test gradient only with respect to input features: the native wrapper returns no ROI gradient. Synchronize CUDA before recording success and timing.
4. Import the normal model and load all checkpoint tensors with `strict=True`. Run shortest and longest native cached examples with batch size one, in eval mode and float32. Require finite scores/boundaries, valid output shapes and no missing/unexpected state keys. If features are not ready, mark this stage pending; an ROI pass alone is not a model pass. Do not start training.
5. If these stages pass, import the native dataset/evaluator and record preprocessing counts, exact validation qid coverage and native decode checks. A full validation run and a padded training/loss/state round trip are separate next checks. Record peak GPU memory, wall times and a machine-readable pass/fail report. Keep the gate under its wall limit.

Use `set -euo pipefail`, unbuffered Python and one immutable log/report path per attempt. Each stage must write a start event, parameters, a completion event and elapsed time. Keep tracebacks and compiler stderr. Never turn an import/build failure into a missing-query skip, fake operator, optional zero output or swallowed error. On the **second failure of the same step**, stop and write a re-plan with both logs. Do not spend the retry budget on the known Torch 2.11 dispatch mismatch, and do not change kernels or model behavior without the user's required approval.

Unrun: container pull, environment resolution, source build, binary loading, safe checkpoint loading, ROI numerical checks, GPU use, complete feature checks and all model/evaluation runs. The metadata and source review select a runtime path; they do not prove that it works or that SDST improves the benchmark.
