# Paper-based AI project shortlist

Research date: November 4, 2026, America/Phoenix.

## Scope and decision

The user wants a substantial open-source AI Engineer project that trains and ships a useful model. They have some ASU Sol GPU access, but no confirmed pilot users. Generic booking agents, incident assistants, and voice QA platforms were rejected. Code availability is not a selection requirement.

The strongest candidates from this pass are selective audio editing, video moment search, and visual inspection. These are proposed adaptations of existing work. No claim of novelty, better performance, verified demand, or successful reproduction is made.

| Candidate | User and result | Main experiment | Main obstacle |
| --- | --- | --- | --- |
| Selective audio editor | A creator removes one unwanted sound while retaining speech and other wanted audio | Fine-tune for preservation and absent-target cases | Obtaining usable audio and preventing audible damage |
| Video moment search | An editor or instructor retrieves exact intervals from a local video collection | Train with confusing, same-video negative examples | Domain-specific temporal labels and media storage |
| Visual inspection | A workshop trains an inspection model from acceptable examples and reviews defect maps | Reduce lighting-related false alarms without missing defects | Camera setup, domain shift, and dataset use restrictions |

## 1. Selective audio editing

### Paper evidence

[CLAPSep: Leveraging Contrastive Pre-trained Model for Multi-Modal Query-Conditioned Target Sound Extraction](https://arxiv.org/html/2402.17455v2), 2024, reuses CLAP representations and trains a separation decoder plus LoRA parameters. It supports text/audio queries and positive/negative prompts. Section IV-B reports a single RTX 3090 with 24 GB memory, mixed precision, and 150 epochs. The paper uses short clips; this does not establish long-recording quality or a short total training time. Its data relies partly on YouTube sources, and the authors report unavailable links.

[SAM Audio: Segment Anything in Audio](https://ai.meta.com/research/publications/sam-audio-segment-anything-in-audio/), December 16, 2025, already supports text, visual, and temporal prompts. Time selection or text-guided separation alone is therefore an existing capability, not a new research contribution.

### Proposed product

A local audio editor for interviews and creator recordings. The user loads a recording, describes a sound to reduce or isolate, previews the edit, adjusts its strength, compares with the original, and exports audio. A timeline, local batch processing, saved edit settings, and repeatable evaluation complete the workflow. The trained separation model should also be usable through a command or API without the editor.

Example: reduce keyboard clicks while preserving the interview and room ambience. This is a goal to test, not a promised capability.

### Proposed training change

Start by reproducing the base separation method with pretrained encoders. Test a preservation-focused adaptation using mixtures with known sources. Include examples where the requested unwanted sound is absent, so the desired removal result is unchanged audio. Penalize damage to speech that should remain. Do not present positive/negative prompting as the change; CLAPSep already includes it.

An absence-aware output or gate is a hypothesis, not evidence that the baseline fails. If baseline behavior is already adequate, select another measured failure before training. Long-recording chunking and overlap handling are engineering work with separate tests; they are not the model contribution.

### Evaluation and feasibility

Compare the original model, the adapted model, and a current separation baseline such as SAM Audio when its license and hardware needs permit. Use identical recordings and prompts. Measure separation quality on known source mixtures, speech distortion, human listening preference, processing speed, and memory. For silent/absent target cases use output energy or input-preservation error; ordinary SI-SDR against a zero target is not a valid score.

Split by original recording and speaker before making mixtures. Separate synthetic-mixture tests from real recordings. Public dataset annotations do not automatically grant redistribution rights for the underlying media. Audit raw downloads and licenses before selecting the training set.

The [official FSD50K release](https://zenodo.org/records/4060432) offers downloadable waveforms and per-clip license metadata. A reviewed subset with suitable licenses is a possible starting point. Its labels describe whole clips, which may contain multiple sounds; inspect clips before treating them as clean source tracks. Retain attribution and split source recordings before generating mixtures. This would be a dataset adaptation, not an exact reproduction of the AudioCaps experiment.

The published 24 GB setup is useful feasibility evidence. It does not establish runtime on the user's Sol allocation. Full pretrained-model training is outside the proposed scope.

## 2. Search for exact moments in a local video library

### Paper evidence

[QD-DETR: Query-Dependent Video Representation for Moment Retrieval and Highlight Detection](https://arxiv.org/pdf/2303.13874), CVPR 2023, uses query-conditioned video features, negative video-query pairs, and temporal predictions. Its appendix trains over features from pretrained encoders. It already includes negative examples formed from different video-query pairs; adding generic negatives is not a distinct contribution.

[Audio Does Matter: Importance-Aware Multi-Granularity Fusion for Video Moment Retrieval](https://arxiv.org/html/2508.04273v1), ACM Multimedia 2025, learns when audio is useful and combines audio and visual information. Appendix D reports experiments on one NVIDIA 3090. This is evidence for a practical research model, not for training its large feature encoders from scratch.

[Not All Inputs Are Valid: Towards Open-Set Video Moment Retrieval Using Language](https://arxiv.org/html/2605.29812v1), listed as ACM Multimedia 2024 with an arXiv posting in May 2026, studies rejection of irrelevant queries. A no-match feature is therefore established research. Its experiments also report one GPU.

### Proposed product

An editor or instructor indexes a local collection of demonstrations, tutorials, or workshop recordings. A query returns ranked intervals with exact playback links, previews, source files, and clip export. It should find visible actions even when the transcript never names them. The user can correct start/end points and mark incorrect matches. Indexing is persistent; do not process every complete video from scratch for each query.

Example: find the moments where someone disconnects a cable, while distinguishing them from moments where the person merely holds the cable.

### Proposed training change

Use confusing examples from the same video: the same objects and background, but the wrong action or wrong stage of the action. Test whether these improve precise retrieval relative to the base negative-sampling method. Training labels must confirm that an alleged negative is actually wrong; unannotated windows may contain valid but unlabeled matches.

Choose one main experiment first. Audio-visual fusion and no-match rejection can be later extensions or comparison methods. Combining all three papers immediately would make attribution and debugging difficult.

### Data, evaluation, and feasibility

The [QVHighlights authors' repository](https://github.com/jayleicn/moment_detr) provides annotations, an evaluation path, and feature-based training resources. It also supports prediction on user videos. Verify the linked feature files and underlying media rights before committing. Benchmark videos are not a substitute for a separate, manually annotated target-domain set.

Compare transcript search, simple visual-embedding search, the paper baseline, and the changed training scheme. Measure temporal overlap, recall of correct intervals, false matches on absent events, indexing throughput, query latency, and storage per video hour. Hold out entire videos, preferably recording sessions, rather than adjacent clips.

A single-GPU temporal head over cached features is a sensible starting design. Extracting video features and storing media can take more time and disk than training that head. Do not claim real-time performance without a measured end-to-end run.

## 3. Visual inspection that tolerates changes in lighting

### Paper evidence

[EfficientAD: Accurate Visual Anomaly Detection at Millisecond-Level Latencies](https://arxiv.org/html/2303.14535v3), WACV 2024, trains a student against a teacher on acceptable images and adds a global autoencoder for logical defects. It already uses augmentation and score normalization. The paper gives training and inference algorithms in its appendix. Its reported timings are specific to its setup and do not include proof of workshop performance. Small geometric errors remain a limitation.

[MVTec AD 2](https://www.mvtec.com/research-teaching/datasets/mvtec-ad-2) includes more than 8,000 images across eight inspection scenarios and test lighting conditions that can differ from training. It has public and private test portions; the latter uses an evaluation server. Its stated license is CC BY-NC-SA 4.0, with commercial use restricted. Downloads use a form, and file availability was not tested.

### Proposed product and experiment

A workshop records acceptable examples for a fixed camera station, trains a model, inspects new images, and reviews highlighted defects. It retains reviewed results and model versions. The goal is a reusable inspection workflow for a specific class of objects, not universal defect detection.

Test a change that uses a small separate set of verified acceptable images from a new lighting setup to adapt the model or its decision threshold. Compare it with stock EfficientAD, stronger training augmentation, and threshold recalibration alone. The change must reduce false alarms without simply suppressing genuine defects. Existing normalization or brightness augmentation must not be relabeled as a novel method.

Evaluate false alarms, defect recall, pixel localization, runtime, and performance under held-out lighting. Keep adaptation data separate from test cases. If this changes the official benchmark's training protocol, report it as a separate adaptation experiment rather than an official standard-setting score.

A one-GPU prototype is a reasonable estimate for the small model. A real camera test is needed before claiming usefulness for makers or workshops. The dataset's noncommercial terms require care before distributing data or marketing a commercial model.

## Selection and next experiment

Prefer audio editing for a clear creator-facing result and a new training story that still connects with the user's speech experience. Prefer video search for broader multimodal retrieval experience and a strong end-to-end demonstration. Prefer visual inspection for computer vision and deployment depth with a smaller model.

Before building a large interface: audit accessible data, implement or run one baseline, create a small sealed evaluation set, and identify one measurable failure. Then implement the selected paper-derived change. Publish unsuccessful results too. A useful reproduction with a careful extension can be a strong project without a claim of research novelty.

Sol is for scheduled training and evaluation. Design jobs to checkpoint and resume under account limits. Local inference performance, account access, dataset downloads, and user demand remain untested. No source code or existing application behavior was changed during this research.
