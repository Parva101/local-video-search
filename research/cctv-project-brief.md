# CCTV event search: proposed project

Date: November 5, 2026 (America/Phoenix).

## User choice and purpose

The user selected video moment search and suggested CCTV footage review. The proposed product searches recorded fixed-camera footage for visible actions and returns source clips with timestamps. This is a design proposal; implementation has not been approved or started.

Potential users include people reviewing loading bays, entrances, parking areas, and shared facilities. Demand has not been tested. The first evaluation should focus on a bounded set of visible actions, such as placing/picking up an object, entering/leaving an area, and loading/unloading a vehicle. Search must work without audio.

The user also requires spoken-content search when audio or subtitles are available, including meeting recordings: "Find the meeting where we discussed Project XYZ." Add source-linked, timestamped speech transcripts and supplied subtitles/captions alongside visual embeddings and generated visual descriptions. Keep spoken text distinct from descriptions of visible events. Speech recognition and subtitle handling remain design proposals; this addition does not remove the no-audio visual search requirement.

Example query: "Find someone picking up a box near the entrance between 2 and 4 pm." The result includes the camera, original file, interval, and playback with context before and after the event. Camera and date filters should use metadata; the trained model handles the visible action. A missing match must be distinguishable from incomplete index coverage or poor visibility.

## Research basis

[ForeSea: AI Forensic Search with Multi-modal Queries for Video Surveillance](https://arxiv.org/html/2603.22872v1), March 2026 preprint, uses a tracking stage, multimodal clip indexing, and a video model to examine retrieved candidates. It is a directly relevant system reference. Its reported method uses existing components; the proposed project's training contribution must be measured separately. Its benchmark results are not evidence that our design works, and its benchmark availability has not been verified.

[QD-DETR](https://arxiv.org/pdf/2303.13874), CVPR 2023, supplies a temporal localization baseline with query-conditioned features and negative examples. Use it as an implementable method reference, not a claim that generic video performance transfers to fixed-camera footage.

[UCA / Towards Surveillance Video-and-Language Understanding](https://github.com/Xuange923/Surveillance-Video-Understanding), CVPR 2024, provides surveillance event descriptions and temporal annotations. The authors report 1,854 videos and 23,542 sentences. It is a direct candidate for sentence-to-time-span training. Annotation and raw-video permissions need separate review; the repository's license alone does not settle media rights.

[MEVA](https://mevadata.org/index.html) provides fixed-camera videos with activity annotations and states CC BY 4.0 terms. It is useful for an independent domain test or a shareable demonstration subset. Activity labels are not the same as diverse natural-language queries; extra reviewed query labels are needed. Multi-view footage of the same physical event should remain in one evaluation split.

## Product path

1. Import existing recordings with camera identity and time metadata. Preserve original footage.
2. Divide recordings into overlapping visual windows, extract visual features and descriptions, and store a persistent index. Add timestamped transcripts and supplied subtitles/captions for spoken-content search; speech chunks can span several visual windows. Keep wide context alongside any object crops; the object and surrounding action can both matter.
3. Apply user-selected camera/date filters and retrieve likely intervals through visual, description-text, or speech/subtitle search. Return source-linked excerpts for spoken-topic matches.
4. Use a trained reranker/localizer to distinguish the requested action and refine its interval.
5. Return ranked source clips, context playback, coverage information, and an explicit no-match outcome when supported.
6. Let a reviewer correct the interval or reject a result. Preserve corrections as versioned data for later training; do not silently learn from them during evaluation.
7. Export a reviewed clip and its source reference.

Start with recorded files. Live stream ingestion is a later extension. For long archives, index once and perform detailed analysis on candidate windows. A first demo can search several recordings from multiple cameras without claiming identity tracking between cameras.

## Model contribution to test

Hypothesis: surveillance-specific training with difficult examples from the same scene improves action retrieval over general visual embeddings.

Useful distinctions include place vs pick up, enter vs exit, and load vs unload. Choose examples with similar objects and backgrounds so the model cannot succeed through scene recognition alone. Manually verify negative labels; a time window without an annotation is not necessarily a negative.

Train a compact query-conditioned temporal model or reranker on frozen features first. Compare that with a stronger pretrained video embedding baseline and a caption-then-text-search baseline. Add encoder adapters only if there is evidence that frozen features lose necessary motion or small-object detail. Train and tune no-match behavior with reviewed absent-event cases, using a separate calibration set.

Hard-negative training and no-match detection are established techniques. The contribution would be a reproducible CCTV adaptation, its measured behavior, and a usable review workflow. No improvement or novelty is claimed yet.

## Evaluation

- Correct event in the first few results, with temporal overlap measured against reviewed labels.
- Boundary error and the amount of footage a person must watch to find the event.
- False matches when the requested event does not occur, plus missed events.
- Indexing speed, query latency, GPU memory, and index size per video hour.
- Performance by camera/viewpoint, object size, illumination, and occlusion.

Use both a published split for comparison and an independent camera/session-held-out test where the metadata permits. Check duplicates and keep adjacent clips and synchronized views of one event together. Include long normal stretches, not only selected event clips. Do not tune on test outcomes.

A replayable local demonstration should let a user search, inspect, and export without exposing the held-out labels to the model. Results describe visible events and remain candidates for human review; intent and authorization are not inferred from a clip.

## Compute and first milestone

Use Sol for feature extraction, model training, and batch evaluation. A frozen-backbone temporal model is a plausible one-GPU starting point, but actual memory, runtime, storage, and queue access remain unmeasured. Save checkpoints and use restartable preprocessing.

Before a large interface build, verify a usable video subset and annotation terms, create a sealed evaluation split, and implement the three baseline paths. The first decision is whether incorrect action matches are a measurable problem and whether targeted training reduces them. A failed improvement test should be reported and used to adjust the method.

No model execution, full data download, private CCTV access, live deployment, or source-code edit was performed for this brief.
