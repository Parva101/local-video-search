# Papers close to a frame and caption search pipeline

Checked 2026-11-05. These are paper results, not tests of our proposed system.

## VideoAgent: memory-based search

Fan et al., *VideoAgent: A Memory-augmented Multimodal Agent for Video Understanding* (ECCV 2024) is a close match. It divides video into two-second segments and stores event captions plus text and visual features. Its tools retrieve captions, find segments by similarity, inspect selected video with a video question-answering model, and query an object database. This supports keeping visual evidence alongside text descriptions.

On the same NExT-QA 600-question subset, Table 4 reports 70.8% accuracy for VideoAgent and 53.5% for Video-LLaVA alone. This supports a pipeline benefit in that experiment; it does not prove superiority over ForeSea. Table 5 uses a separate 150-question subset: captions alone score 40.7%; adding segment localization and Video-LLaVA question answering scores 62.7%, without the object database. On Ego4D NLQ, Table 2 reports R1@0.3 / R5@0.3 of 8.40 / 17.36 for visual ViCLIP features, 10.07 / 22.53 for generated LaViLa caption features, and 11.13 / 25.31 for their combination. Ego4D human captions are another experiment and must not be treated as automatic captions.

Sources: [paper](https://arxiv.org/html/2403.11481v1), [official method page](https://videoagent.github.io/).

## VideoTree: reduce repeated frames, then inspect useful detail

Wang et al., *VideoTree* (CVPR 2025) clusters frame embeddings, captions representative frames or short clips, and scores their relevance to a query. It then creates finer clusters where detail is useful. Selected captions go to an LLM in time order. This is close to the proposed reduction of repeated frames, with query-guided expansion added. The final reasoning input is captions rather than direct video verification.

The paper reports 61.1% accuracy on the full EgoSchema test set and 75.6% on the NExT-QA test set. These are question-answering scores, not timestamp overlap scores. They cannot be compared with ForeSeaQA percentages.

Source: [paper](https://arxiv.org/html/2405.19209v3).

## Names and comparison limits

There is a different 2024 VideoAgent paper by Xiaohan Wang et al., *Long-form Video Understanding with Large Language Model as Agent*. Its reported 54.1% EgoSchema and 71.3% NExT-QA results belong to that paper, not Fan et al.'s memory-based system. [Source](https://arxiv.org/html/2403.10517v1).

ForeSea's reported tables do not include VideoTree or Fan et al.'s VideoAgent. A direct comparison with either was not found in the papers checked. ForeSea's baseline labeled VideoRAG cites Luo et al.'s *Video-RAG: Visually-aligned Retrieval-Augmented Long Video Comprehension* (2411.13093). Do not substitute scores from the separate VideoRAG papers by Jeong et al. or Ren et al. [ForeSea paper](https://arxiv.org/html/2603.22872v1).

## Practical test

Compare the simple frame/clip index, captions plus visual retrieval, and ForeSea's scene/person retrieval variants on the same held-out questions. Keep the answer model and video input budget fixed. Measure retrieval recall, timestamp overlap, answer accuracy, search time, and indexing cost separately. Better question answering alone does not prove better evidence retrieval.

## ForeSea evidence and proposed experiment

ForeSea's full-scene variant beats its person-focused variant on text-query accuracy and timestamp overlap, and on image-plus-text timestamp overlap. Its tested Video-RAG baseline uses a different answer model, so that comparison does not isolate pipeline quality. Sources: [Tables 1-3 and appendix Table 6](https://arxiv.org/html/2603.22872v1).

The proposed system should retain source video and timestamps. Group repeated frames for indexing; do not erase source evidence. Store separate visual and caption features. Merge retrieval rankings, recover nearby source clips, and inspect those clips before returning event intervals. Test query-guided denser sampling only after this baseline works. Object tracks are optional until a measured failure needs them.

The test should compare the original simple pipeline, the combined caption/visual pipeline, and reproduced ForeSea and ForeSea-Global variants. Use the same videos, held-out queries, answer model, and input budget. Keep frame selection and thresholds fixed after validation. Measure retrieval recall, interval overlap, missed events, false matches, query latency, and indexing time/storage. Include absent-event queries and uncertainty across videos. No model training is required for this first experiment.

No models were run. Access to the complete ForeSeaQA release was not confirmed. Paper results are evidence for hypotheses, not results for the proposed system.
