# Next benchmark access and pilot

Checked 8 November 2026. Research only. No application code, model job, full video download, or benchmark run was made. Small HTTP metadata and range probes tested the access paths below.

## Recommended first pilot: Charades-STA

Use **20 official train videos for development (53 queries)** and **25 official test videos for the frozen pilot (69 queries)**. Include every query attached to each selected file. Select files by ascending SHA-256 of `local-video-search-charades-pilot-v1:{split}:{video_id}`, separately within each official split. This rule uses neither model scores nor target locations. Freeze IDs, source hashes and settings before model runs. Check split overlap and duplicate media during preparation. The pilot is a development/evaluation subset; it is not the complete Charades-STA test benchmark.

The annotation files in the [VSLNet authors' reference implementation](https://github.com/26hzhang/VSLNet) are readable at commit `3793c625f2e251a5f19a0d59f0c83b12e386f808`:

| Split | Rows | Video files | SHA-256 |
| --- | ---: | ---: | --- |
| [train](https://raw.githubusercontent.com/26hzhang/VSLNet/3793c625f2e251a5f19a0d59f0c83b12e386f808/data/dataset/charades/charades_sta_train.txt) | 12,408 | 5,338 | `e966fc1970cf6bc4cc73db2dd4fc10e148313810a372eef488defb0dd2ee359f` |
| [test](https://raw.githubusercontent.com/26hzhang/VSLNet/3793c625f2e251a5f19a0d59f0c83b12e386f808/data/dataset/charades/charades_sta_test.txt) | 3,720 | 1,334 | `fab341679c20b0917173dcffffde367a71113fe63f3a645558cef2ebfbfefb55` |

These are paper-author reference copies, not a new claim that they were byte-compared with the original TALL release. Both original annotation links on the [TALL authors' page](https://github.com/jiyanggao/TALL) returned 404 in this check, including normal public download URLs. Pin the accessible copy and report its identity. TALL documents cleaned annotations and R@1/R@5 at temporal IoU 0.5/0.7; preserve that protocol rather than treating our QVHighlights export as a Charades evaluator.

## Small raw-media access is verified

The [Ai2 Charades 480p archive](https://ai2-public-datasets.s3-us-west-2.amazonaws.com/charades/Charades_v1_480.zip) returned HEAD 200, length **16,339,546,533 bytes**, and byte-range responses 206. A 65,536-byte tail read located its ZIP64 directory. The directory is **1,022,502 bytes** at byte offset **16,338,523,933**. A bounded range read parsed 9,849 directory entries, including 9,848 MP4 files.

All selected pilot video members are present. The 20 development files total **35,628,494 compressed bytes**; the 25 test files total **42,772,169 compressed bytes**. Thus this pilot needs about **78.4 MB** of compressed video, plus headers and the directory, rather than the whole 16.3 GB archive. A selected member's local header also returned 206 and passed ZIP header checks. That 256-byte probe included a short compressed prefix; no complete video was downloaded or decoded.

A small standard-library downloader can later fetch selected local headers and their exact compressed payload ranges, inflate each member, and verify CRC, declared sizes and a new SHA-256. It must reject ignored ranges, changed archives, unsafe paths, unexpected compression/encryption, and incomplete data. The archive ETag `d37c91565b08ce1f432a46e11351751e-1948` is a multipart change marker, not a SHA-256 integrity proof.

## Primary data license recovered

The current web license link is broken, but [Ai2's official annotation archive](https://ai2-public-datasets.s3-us-west-2.amazonaws.com/charades/Charades.zip) remains readable. Its `Charades/license.txt` member was fetched by a small range, inflated and checked: 1,177 bytes, CRC32 4,255,669,424. It permits academic, non-profit and government research, and evaluation use. It restricts commercial use, public modification and redistribution of the data. This agrees with [Google's dataset loader](https://raw.githubusercontent.com/google-ai-edge/mediapipe/master/mediapipe/examples/desktop/media_sequence/charades_dataset.py), which says the code license does not cover the dataset.

Keep video files, normalized query manifests and annotations in ignored local storage. Ship preparation code, source URLs, hashes and numeric results, rather than republishing the dataset. Third-party mirrors that label Charades video archives Apache-2.0 do not replace these primary data terms. A research pilot on this academic project is feasible; commercial reuse needs separate permission.

## Why QVHighlights is a later raw-media step

The [official raw archive](https://nlp.cs.unc.edu/data/jielei/qvh/qvhilights_videos.tar.gz) is a **143,734,787,897-byte gzip-compressed tar**, not a ZIP. HEAD 200 and a 65,536-byte range 206 worked; gzip magic and the first `videos/` tar header were checked. Ranges alone do not provide random member extraction from a gzip stream. No public gzip index was verified.

The [official validation annotations](https://raw.githubusercontent.com/jayleicn/moment_detr/b7e553ac3b0c898ee6b85e03ee507c064eab89ca/data/highlight_val_release.jsonl) contain 1,549 queries over 1,518 clip files, at most two queries per file. Even the 20 most query-dense files cover only 40 queries. A 10?20-file, 50-query official QVHighlights pilot is therefore not available from this split. The authors provide one direct [example video](https://github.com/jayleicn/moment_detr/tree/main/run_on_video/example), which we already use. YouTube reconstruction is described in the [official data instructions](https://github.com/jayleicn/moment_detr/blob/main/data/README.md), but availability and byte identity are not guaranteed. Use the author evaluator for official mAP/R@1; no new QVHighlights model result is claimed here.

## Fallback and speech tests

[DiDeMo](https://github.com/LisaAnne/LocalizingMoments) is a feasible fallback: the complete official validation JSON has 4,180 queries over 1,094 videos; the first 20 sorted file IDs cover 77 queries. Its author-provided AWS URL rule resolved one media file with HEAD 200 (4,092,999 bytes). Its [per-video licenses](https://raw.githubusercontent.com/LisaAnne/LocalizingMoments/master/data/video_licenses.txt) list different Creative Commons terms, so select and record acceptable files individually. Its five-second chunk annotations and [official evaluator](https://raw.githubusercontent.com/LisaAnne/LocalizingMoments/master/utils/eval.py) use ranked discrete moments and several annotator responses. A seconds-only QVHighlights score is not a reproduction of DiDeMo's official metric.

[LibriSpeech](https://www.openslr.org/12) can test transcription word error rate, but it is read speech, not video-topic retrieval or conversations. Add separate rights-cleared product recordings with spoken topics, names/numbers, silence, noise, missing audio and supplied subtitles. Freeze transcript labels and relevant time spans before inference; measure ASR error, speech-only retrieval, mixed audio/visual evidence overlap and timestamp error. Neither WER nor Charades-STA establishes reliable event counts. Counting needs a defined event and complete reviewed occurrence labels; overlapping retrieval windows are not separate events.
