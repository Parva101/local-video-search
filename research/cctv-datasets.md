# CCTV datasets for text-to-moment archive search

Reviewed November 5, 2026. Scope: research on visible actions in recorded video. No face recognition, person identification, or conclusions about intent. No video was downloaded or inspected in this review.

## Recommendation

Use **UCA as the first research benchmark for sentence-to-time-span training**. It directly supplies the task labels needed. Use a small, reviewed **MEVA subset for a public demo and a separate camera/time-held-out test**, after writing natural-language queries for its action annotations. MEVA has clearer media licensing. Keep VIRAT as a later robustness dataset unless its agreement is already accepted.

This recommendation concerns fit, not verified download success or legal clearance. UCA's terms need clarification before redistribution or commercial use.

## UCA: the closest task match

[Towards Surveillance Video-and-Language Understanding, CVPR 2024; paper HTML](https://arxiv.org/html/2309.13925v2) describes UCF-Crime Annotation (UCA): 1,854 videos and 23,542 sentence annotations with temporal spans. It distinguishes 121.9 hours of retained video from 110.7 annotated hours. It evaluates temporal sentence grounding, among other tasks. The underlying videos come from UCF-Crime. The paper provides train/validation/test splits; this review did not establish that cameras or original source recordings are disjoint across those splits.

The [original author repository](https://github.com/Xuange923/Surveillance-Video-Understanding) is accessible. It supplies annotation text/JSON, with per-video sentences and timestamps. It also lists `txt_mask`, a gender-neutral annotation version. It links to the original UCF-Crime video download rather than hosting the videos as part of its annotation files. The old GitHub Pages project URL returned 404 in this review.

**Terms:** The author repository and paper appendix both state Apache 2.0 and also restrict intended use to academic/research purposes. Do not treat this as unambiguous permission to redistribute all source footage. Rights for the underlying UCF-Crime videos are a separate matter. The [UCF-Crime author page](https://www.crcv.ucf.edu/research/real-world-anomaly-detection-in-surveillance-videos/) provides the original dataset description and download links; this review did not verify a complete media license or download the archive.

**Fit and limits:** Good for learning language-to-event alignment. Its event selection includes crimes, accidents, and violence, so it is not a representative sample of an ordinary building archive. Review labels and restrict project queries to visible events such as entering, leaving, carrying, placing, or vehicle movement. Do not turn category names into claims about a person's intent. Some annotations use inferred or demographic language; the gender-neutral release does not by itself establish that every description is suitable.

## MEVA: strongest starting media source for a public demonstration

The [official MEVA site](https://mevadata.org/) describes staged and unscripted person/vehicle activities captured from several viewpoints. It lists 64 hours of evaluation-level annotations and 120.2 hours of training-level annotations, with the latter receiving less audit. The site reports 328 hours of ground-camera video in its dated release summary. It is an activity-detection dataset; natural-language retrieval queries must be added and checked.

The [official download README](https://mevadata.org/resources/README-meva-kf1-data.html) provides a public S3 bucket (`mevadata-public-01`) and unsigned download commands. Typical clips are five minutes. Filenames encode date, time, and camera. The README and main site use different corpus totals and release snapshots, so select and record an explicit file manifest rather than claiming all totals are interchangeable. The HADCV22 test drop must not be used to train NIST ActEV leaderboard submissions.

The [dataset's own license](https://mevadata.org/resources/MEVA-data-license.txt) states CC BY 4.0. Preserve attribution and modification notices. Public documentation does not show an application gate for the S3 media. The annotation GitLab site returned 403 to the browsing tool; this does not establish that a normal browser or Git client cannot access it. Do not promise an end-to-end download until checked.

**Fit and limits:** Useful for neutral visible-action queries and repeated observations from fixed cameras. Action classes and tracks are not open-ended sentence annotations. Make templates only as a starting point, then have a human write and check held-out query paraphrases. Treat object relations, counts, clothing, or spatial descriptions as unsupported until separately annotated. Multi-camera views of the same event can leak across a naive split.

## VIRAT: compact, useful second test after access terms

The [official VIRAT site](https://viratdata.org/) describes Ground Release 2.0 as about 8.5 hours from 11 outdoor scenes with 12 event classes. Its newer DIVA annotations add tracks and 46 activity types; these are separate annotation releases and must not be mixed without a documented mapping. [NIST's catalog](https://tsapps.nist.gov/BDbC/Search/Details/433) lists concrete original actions, including loading/unloading a vehicle, opening/closing a trunk, entering/exiting a vehicle or facility, carrying, and running.

Ground footage is subject to the [VIRAT Video Dataset Usage Agreement](https://actev.nist.gov/pub/VIRAT-Video-Data-Set-Protection-Agreement-1-4-11.pdf). It says every individual with access must sign. Do not silently accept it or redistribute ground video as ordinary open-source assets. Aerial footage has different terms and lacks the same completed annotation coverage. As with MEVA, original activity labels are not natural-language queries.

## Evaluation design for this project (our proposal)

1. Preserve the official UCA split for one comparable benchmark. Separately audit source duplicates and near-duplicates; report any limits.
2. Add a deployment-style split by scene/camera **and** recording session. For MEVA, hold simultaneous views of the same event together. A camera-only split can still leak the same event through another camera.
3. Split raw recordings before making windows, crops, paraphrases, or synthetic negatives. Keep adjacent overlapping windows together.
4. Include many queries with no matching event. Check negatives against the whole candidate interval; an event absent from annotations is not automatically absent from video.
5. Test repeated matches. “Find each time a person places a bag” may require multiple intervals, unlike a single-span benchmark.
6. Compare action-sensitive hard negatives from the same scene: opening versus closing, placing versus picking up. Use only clearly visible, reviewed labels.
7. Report temporal recall/IoU, ranking quality, false-positive rate on absent queries, missed repeated events, indexing cost, query latency, and human review time. Do not report anomaly AUC as proof of language retrieval quality.

No dataset was downloaded, no license was accepted, and no annotation quality was tested. Main risks are label gaps, source/camera leakage, and assuming benchmark footage represents a real deployment.
