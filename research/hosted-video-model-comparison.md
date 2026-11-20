# Qwen3.8-27B and Gemma 4 31B for video search

Checked: 2026-11-06. Research only; no application changes or inference calls in this investigation.

## Finding

The available primary-source comparisons do not establish one clear winner for our complete task. Gemma leads overall panoramic video QA and state-interval overlap. Qwen leads the panoramic action category and several proactive event-detection scores. Neither result proves reliable CCTV search, counting, or exact timestamps.

Use both as candidates on the same independently reviewed clips. Gemma is a practical first hosted integration because its ASU endpoint advertises schema enforcement. That is an interface advantage, not proof of better visual understanding.

## Direct video comparison: PanoVideoBench

Table 3 compares the exact models. Scores are percentages; higher is better.

| Metric | Qwen3.8-27B | Gemma-4-31B-it |
| --- | ---: | ---: |
| Overall | 44.8 | **47.0** |
| Appearance/detail (APP) | 54.7 | **58.4** |
| Spatial/viewpoint reasoning (SPA) | 44.1 | **48.5** |
| Action/state understanding (ACT) | **46.8** | 44.6 |
| Cross-view motion/tracking (MOT) | 31.1 | **34.8** |
| Spatiotemporal event reasoning (TEM) | 27.0 | 27.0 |

Protocol: 360-degree equirectangular video, uniform 1 fps, at most 128 frames, 1280-pixel long edge; same prompts, model-default temperatures, up to 32,768 output tokens including thinking. This differs from our eight-frame pipeline and ordinary CCTV. Numbers above use the default resolution. [Table 3 and Appendix C.2](https://arxiv.org/html/2610.42082v1).

## Event intervals and tracking: ProactEgoMem-Daily

Table 4 includes both exact models. The following are intervention-level percentages; higher is better.

| Metric | Qwen3.8-27B | Gemma4-31B |
| --- | ---: | ---: |
| State tracking: interval mIoU | 13.8 | **17.2** |
| State tracking: event F1 | **20.1** | 15.5 |
| Location tracking: interval mIoU | **5.2** | 4.4 |
| Location tracking: event F1 | **14.2** | 9.0 |

Each second supplies the ten latest frames at 1 fps, timestamps, and JSON tool/event context. Invalid JSON counts as silence; unmatched intervals score zero. This tests proactive tool lifecycles in first-person video. Thinking settings for this pair were not established. [Sections 5.1–5.2 and Table 4, PDF page 7](https://arxiv.org/pdf/2610.30089v2).

## Official model evidence and missing results

Qwen's official 3.8-27B card documents image/video input, a `video_url` example, and configurable video sampling. Its published evaluation table contains visual and agentic benchmarks, but no Video-MME, MLVU, MVBench, LVBench, or LongVideoBench score for this exact release. Do not substitute Qwen3.5 or Qwen3.6 scores. [Official Qwen card](https://huggingface.co/Qwen/Qwen3.8-27B).

Gemma 4 31B supports video through frame sequences. Google's video tutorial explicitly lists `google/gemma-4-31B-it`; the model card describes a 60-second video setting at 1 fps. Its official card has image/reasoning benchmarks, not a comparable named video-benchmark table for this pair. Gemma 31B does not have native audio input. [Gemma card](https://ai.google.dev/gemma/docs/core/model_card_4), [official video tutorial](https://ai.google.dev/gemma/docs/capabilities/vision/video).

No comparable primary-source Video-MME/MLVU/MVBench/LVBench/LongVideoBench result was established for both exact models. Exclude third-party estimated leaderboard numbers, including the apparent Video-MME 84.0 versus 83.9 comparison: those are estimates, not a measured head-to-head result.

## ASU-hosted compatibility

The parent agent checked the authenticated ASU catalog during this task. It reported both as BF16 models with native vision and no gateway add-ons. These are live catalog facts reported by that check, separate from the papers:

| ASU model ID | Context window | Native vision | Response-schema enforcement |
| --- | ---: | --- | --- |
| `qwen38-27b` | 262,144 | Yes | No |
| `gemma4-31b-it` | 131,072 | Yes | Yes |

The smaller hosted Gemma context is not the base model's advertised 256K maximum. `supports_vision` does not establish acceptance of `video_url` or the number of images permitted in one request. Read these flags as ASU defines them. [ASU chat API](https://docs.rc.asu.edu/ai/api/chat/).

## Next test

Freeze source clips and labels before comparing models. Include entering/leaving, picking up/putting down, opening/closing, action order, absent events, and short actions between sparse samples. Match frame count/resolution, prompt, reasoning mode, and output budget. Measure event recall, temporal IoU, false positives, schema failures, latency, and queue time. Keep the hosted model ID and actual provider settings in each trace.

Not checked here: hosted video requests, eight-image acceptance, direct quality or latency, and a controlled CCTV comparison. Published settings differ from our current eight-frame pipeline.
