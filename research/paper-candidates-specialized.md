# Paper-based project candidates: specialized audio and document retrieval

Reviewed November 4, 2026, for a personal project using limited ASU Sol GPU access. These are proposals and hypotheses, not claims of novelty or measured gains. No model was run.

## 1. A local sound editor that removes a specified sound while preserving the rest

**Best candidate from this review.** Intended users are podcast editors, student filmmakers, field recordists, and people preparing lecture recordings. Example: “Reduce the air conditioner, keep the speaker and audience reactions.” The output is edited audio and separate tracks, with an audible before/after comparison.

### Research basis

[CLAPSep, 2024](https://arxiv.org/html/2402.17455v2) adapts a pretrained contrastive audio/text model for target sound extraction. It supports text or example-audio queries, including positive and negative queries. The paper trains a separation decoder plus LoRA weights in the audio encoder. Its reported setup uses one RTX 3090 with 24 GB memory, bf16, batch size 32, and 150 epochs. Training mixtures come from roughly 145 hours of AudioCaps. The paper measures SDR and SI-SDR improvement. It explicitly says its method is non-causal, so do not present the original model as a live streaming solution. The code repository declares an MIT license; pretrained dependencies and audio rights still need separate checks. [Author repository](https://github.com/Aisaka0v0/CLAPSep)

[Listen, Chat, and Remix](https://listenchatremix.github.io/) is a related full-task reference: text requests control removal, extraction, and volume changes for multiple sounds. Its author page describes a 160-hour constructed dataset and supplies audio examples. This establishes that editing, beyond a binary extraction task, has been studied. The page was read; this review did not obtain the full paper successfully.

### A useful modification to test

Focus on **preserving untargeted speech and doing nothing when the requested sound is absent**. Adapt the separator with absent-target examples and an explicit preservation loss. Compare with the unchanged separator on:

- Target suppression and target reconstruction quality.
- Damage to speech that should remain, including transcription error and a blinded listening test.
- Absent-target cases where output should remain close to the input.
- Long recordings: audible joins, volume jumps, and processing speed across chunks.

This is a controlled experiment, not a claim that absent-target training is new. Select a limited set of frequent editing cases first. Time-range selection, reversible edits, residual tracks, and preview/export make a useful product around the trained component.

### Data and feasibility

AudioCaps relies on audio sourced from YouTube; matching the exact historical corpus is not guaranteed. A more reproducible starting dataset is [FSD50K's official release](https://zenodo.org/records/4060432): it contains downloadable waveforms, clip labels, and per-clip license metadata. Use a reviewed subset with suitable terms and preserve attribution. Its labels are weak, and clips can contain multiple sources; they are not automatically clean stems. Manually check source clips, then mix separate clips to obtain known target and residual waveforms. Generate descriptions from verified labels, then add a small human-written set. Separate train/test clips and source recordings before mixing.

The single-GPU paper setup is evidence for feasibility. Runtime on Sol and fit for changed chunk lengths remain unknown. Start from a pretrained checkpoint or reproduce a small decoder-training run; do not assume 150 epochs fit one four-hour allocation.

[SAM Audio, 2025](https://arxiv.org/html/2512.18099v1) is a more recent reference and possible comparison model. Its paper describes text, visual, and temporal prompts. Full training uses a very large batch and long training schedule; that is outside this project's intended scope. The project must show a useful quality/cost/preservation result against available models, not merely wrap an old checkpoint.

**Why it survives the coding-agent objection:** a coding agent can operate a sound model, but tool orchestration alone does not learn the waveform separation. The contribution is the trained acoustic component and its verified behavior. It can also be exposed as a tool for agents.

## 2. Visual evidence search for changing technical documents

**Second choice; needs a sharper user and corpus before commitment.** Intended users are engineers comparing technical manuals, equipment specifications, or report revisions. They need the correct figure, table, or page from the correct edition, with visual evidence.

### Research basis

[ColPali, 2024 / ICLR 2025](https://arxiv.org/html/2407.01449v6) embeds page images and uses token-to-patch late interaction for retrieval. It trains LoRA weights and a projection layer with a contrastive objective and hard in-batch negatives. The reported training uses about 119,000 query-page pairs and eight GPUs. Its method is suitable for adaptation, but reproducing full training on one GPU is not a promised equivalent. [Released training data](https://huggingface.co/datasets/vidore/colpali_train_set)

[ViDoRe V3, 2026](https://arxiv.org/html/2601.08620v1) extends evaluation to complex queries, multiple pages, answer generation, and visual grounding. The paper includes query-page links and bounding-box annotation methods. Thus page retrieval and grounding can be evaluated separately. It does not automatically supply a benchmark of document revisions.

### A useful modification to test

Train with **near-identical pages from different revisions as hard negatives**. Test whether this reduces wrong-edition retrieval compared with the unchanged model. Always include a simple metadata-filter baseline: if filtering by date/version solves the task, model training is unnecessary. A stronger training target would involve visually similar tables with changed headers, units, or values after the correct revision has been selected.

For test labels, construct a small reviewed corpus of original, shareable technical documents and controlled revisions. Each change has a known page, bounding box, and value. Keep all versions of one document family in the same split. Add a human-checked set of naturally revised documents where reuse is permitted. Synthetic revisions alone do not prove utility on real manuals.

Measure retrieval recall, wrong-version rate, bounding-box grounding, answer support, index size, and query latency. Ship a version-aware evidence browser and an API. Do not assume retrieval heat maps are reliable factual citations.

**Why it might survive the coding-agent objection:** the potential contribution is a compact, trained retrieval component over a large visual corpus. A general agent can call that component. A PDF chat screen without measured retrieval gains does not establish a reason to build this project.

## Deferred candidate: personalized captions for atypical speech

[Adapting Foundation ASR Models to Dysarthric Speech, 2026](https://arxiv.org/html/2606.31722v1) presents a deployed personalized recognizer and finds full fine-tuning stronger than LoRA in its single-speaker study. This is a useful problem, but it is not the easiest public portfolio route. The [released German data](https://huggingface.co/datasets/chuber/dysarthric-speech) is gated and CC BY-NC; the larger [Speech Accessibility Project](https://speechaccessibilityproject.beckman.illinois.edu/conduct-research-through-the-project) requires an institutional data-use agreement. Do not assume either dataset is already available to this user. A single-speaker result would also not establish general accessibility benefit.

No compute trial, demand validation, complete license audit, or implementation was done. Main risks are data quality, source rights, and failing to improve on strong current baselines.
