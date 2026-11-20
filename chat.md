
# Review arXiv paper 2501.05874 (2)

> go voer this research paper: [https://arxiv.org/pdf/2501.05874](https://arxiv.org/pdf/2501.05874)

<details><summary>3 previous messages</summary>

> I’ll read the paper and explain its main claims, the evidence, and the limits.
>
> <details><summary>Searched the web</summary>
>
> Searched the web for `https://arxiv.org/pdf/2501.05874`
>
> </details>
>
> The results support using video frames with transcripts. Two limits need care: the text comparison uses a different source collection, and the human review covers only 50 questions.

</details>

I reviewed **[VideoRAG: Retrieval-Augmented Generation over Video Corpus](https://arxiv.org/pdf/2501.05874)**. It shows promising gains for answering instructional questions from videos.

The method has three main steps:

1. **Prepare videos:** Extract frames and transcripts. Use Whisper when transcripts are missing.
2. **Find a relevant video:** Compare the question with combined visual and text representations.
3. **Generate an answer:** Give selected frames, the transcript, and the question to a video language model.

A trained selector chooses four frames for retrieval and 32 for generation. Generation frame selection considers the question. The experiments use one retrieved video per answer. [Method and implementation](https://arxiv.org/pdf/2501.05874#page=16)

For LLaVA-Video on WikiHowQA, adding frames raises ROUGE-L from **22.81 to 24.93** compared with transcript-only RAG. This measures answer similarity, not factual accuracy. [Table 1](https://arxiv.org/pdf/2501.05874#page=6)

My main concern is the evidence for retrieval: random videos score **24.29**, versus **25.42** for retrieved videos. That small gap needs further study before claiming strong reliance on retrieved evidence. [Table 7](https://arxiv.org/pdf/2501.05874#page=17)

I did not run the code. Performance on your own videos remains untested.

> what language modelis it usingfor videorag

The paper tests three models to generate answers from videos:

- **LLaVA-Video — 7B parameters**
- **InternVL 2.5 — 8B parameters**
- **Qwen2.5-VL — 3B parameters**

It uses **InternVideo2** to retrieve relevant videos and **Whisper** to convert speech into text. VideoRAG combines these models; it is not a separate language model. [Paper, implementation details](https://arxiv.org/pdf/2501.05874#page=5)

I checked the paper’s setup, but did not check the code.

> check the limitation in this paper and all papers that eventually cite this paper and publish an upgrade, what is the sota frontier AI in this

<details><summary>10 previous messages</summary>

> I’ll check the paper’s limits, trace later papers that cite and extend it, and compare the strongest results. I’ll separate research results from models you can use today.
>
> <details><summary>Searched the web</summary>
>
> Searched the web for `"2501.05874" "VideoRAG" citing ...`
>
> </details>
>
> I’m using the research skill to check primary sources and save a source-linked report. There are two different papers called “VideoRAG,” so I’ll check which one each later paper cites.
>
> <details><summary>Searched the web</summary>
>
> Searched the web for `https://mlsanity.com/paper/2501.05874/`
>
> Searched the web for `"2501.05874" -site:alphaxiv.org -site:dblp.org -site:mlsanity.com -site:huggingface.co -site:arxiv.org/abs/2501.05874 -site:arxiv.org/pdf/2501.05874 -site:arxiv.org/html/2501.05874 ...`
>
> </details>
>
> <details><summary>Searched the web</summary>
>
> Searched the web for `https://arxiv.org/html/2504.20734`
>
> Searched the web for `'Table 1:'`
>
> Searched the web for `https://arxiv.org/html/2609.14066`
>
> </details>
>
> I found 59 indexed arXiv papers that cite the original paper, plus 29 records in OpenAlex. These lists overlap and include surveys and applications.
>
> The clearest later changes are better evidence selection, memory across videos, and repeated retrieval. The results use different tests, so they do not give one clear winner for every video task.
>
> <details><summary>Searched the web</summary>
>
> Searched the web for `https://deepmind.google/models/model-cards/gemini-3-8-flash/`
>
> Searched the web for `'LVBench'`
>
> Searched the web for `"VideoRAG" "Jeong" "EgoFact" ...`
>
> Searched the web for `https://openreview.net/pdf?id=6WS1wfLmc6`
>
> Searched the web for `https://openreview.net/pdf/814413c114203795bf327cb75f4b92aa3e45ed09.pdf`
>
> </details>
>
> Two papers give clear comparisons with the original approach: CARVE improves evidence retrieval, and GraMRAG reports better answers on the original datasets under a new scoring method.
>
> I also found several “VideoRAG” comparisons that test a different paper with the same name. I’ll keep those separate in the report.
>
> <details><summary>Searched the web</summary>
>
> Searched the web for `https://arxiv.org/html/2606.07512v2`
>
> </details>
>
> <details><summary>Created a file</summary>
>
> - Wrote `./research/video-rag-review.md` (+48 -0)
>
> </details>

</details>

**There is no single proven SOTA for this task.** The strongest candidates I found are **CARVE for evidence retrieval, GraMRAG for direct comparisons with the original VideoRAG, and MemDreamer for long-video reasoning**. They solve different tasks, so their scores cannot form one fair ranking.

As of **6 November 2026**, I screened **59 arXiv papers that cite the original paper**, plus **29 overlapping publication records**. I saved the [full review](./research/video-rag-review.md) and [citation inventory](./research/video-rag-citation-inventory.md). Citation indexes can miss papers, so this is a documented search, not proof of every citation worldwide.

**The original paper has five main limits.**

- **Retrieval remains weak:** adaptive retrieval ranks the paired target first in 11.8% of cases. Other retrieved videos can also be valid.
- **Sparse frames can miss evidence:** it uses four frames for retrieval and 32 for generation.
- **Limited evidence combination:** experiments use one retrieved video per answer.
- **Narrow evaluation:** mainly instructional questions; human review covers 50 questions.
- **The text comparison changes the source:** Wikipedia versus instructional videos makes the benefit of video harder to isolate.

The authors also call for better benchmarks and more efficient frame selection. [Original paper](https://arxiv.org/html/2501.05874v3)

The main later papers address these limits as follows:

| Paper                                                                                   | What it improves                                                                                    | What the evidence supports                                                                                              |
| --------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **[UniversalRAG](https://arxiv.org/html/2504.20734)** — April 2025, later revised | Routes questions to text, tables, images, clips, or full videos                                     | A broader framework from the same research group; stronger mixed-task results, rather than a consistent video-only lead |
| **[WorldMM](https://arxiv.org/html/2512.02425)** — December 2025                  | Stores visual, event, and semantic memories; searches repeatedly at different time scales           | A substantial move toward hours or days of video                                                                        |
| **[VimRAG](https://arxiv.org/html/2602.12735)** — February 2026                   | Stores reasoning and evidence in graph memory; learns how to retrieve and retain visual information | Direct comparisons with VideoRAG under a new evaluation setup                                                           |
| **[MemDreamer](https://arxiv.org/html/2606.07512v2)** — June 2026                 | Builds hierarchical graph memory, then uses a reasoning model to search it                          | Strong reported long-video QA results; tests a supplied video                                                           |
| **[CARVE](https://arxiv.org/html/2606.13141v2)** — June 2026, revised October     | Chooses text or visual evidence, at frame or clip level, separately for each chunk                  | The clearest controlled retrieval improvement I found                                                                   |
| **[MERIT](https://arxiv.org/html/2608.07663v2)** — August 2026                    | Stores multiple search keys per episode and expands evidence to nearby clips                        | Strong results for ultra-long video memory                                                                              |
| **[GraMRAG](https://arxiv.org/html/2609.14066)** — September 2026                 | Combines multiple agents, graph memory, and reinforcement learning                                  | Strong reported direct improvements on the original dataset family; still preliminary                                   |
| **[TAL](https://arxiv.org/html/2611.01460)** — November 2026                      | Converts tutorials into a persistent “tutorialbook” without changing model weights                | A new direction for learning reusable knowledge from videos; different tests from VideoRAG                              |

**Three results matter most when judging the frontier.**

**1. CARVE gives the clearest evidence that retrieval itself improves.** On V-RAGBench, it raises Recall@5 from **51.0% to 60.3%** against its Jeong-style VideoRAG baseline. With Qwen3-VL-32B, answer pass rate rises from **31.2% to 36.8%**. The methods share chunk embeddings, which helps isolate the retrieval policy. It is not an unchanged reproduction of the original system. [CARVE, Table 2 and implementation](https://arxiv.org/html/2606.13141v2)

**2. GraMRAG reports direct gains on the original benchmark family.** With Qwen3-VL-8B:

| Dataset             | VideoRAG baseline |        GraMRAG |
| ------------------- | ----------------: | -------------: |
| WikiHowQA           |              27.1 | **33.4** |
| SyntheticQA         |              48.6 | **59.0** |
| Cross-video XVBench |              32.1 | **41.2** |

These are **model-judged answer scores**, not the original ROUGE scores. GraMRAG uses Qwen3-Max as judge and trains on eight H100 GPUs. I found no established independent reproduction or public code release, so I would treat it as a promising research claim. [GraMRAG](https://arxiv.org/html/2609.14066)

**3. MemDreamer has the highest selected long-video QA result I found:** **90.7% on LVBench**, using Gemini 3.1 Pro for perception and reasoning. Its small online context excludes the earlier work needed to build memory. This is strong reported evidence for memory plus repeated search, but it does not establish the best retrieval across a large collection of unknown videos. [MemDreamer](https://arxiv.org/html/2606.07512v2)

For ultra-long personal video histories, **MERIT** is also worth close attention: it reports **71.2% EgoLifeQA with GPT-5**, versus WorldMM’s reported **65.6%**. Its results depend on the solver and memory construction models. [MERIT](https://arxiv.org/html/2608.07663v2)

**For the underlying AI model, keep model capability separate from the retrieval system.** Google reports **87.1% static LVBench for Gemini 3.8 Flash**. However, the comparison uses unequal frame budgets across vendors. Newer Gemini 4 models exist, but the checked sources do not establish a comparable video-corpus RAG lead. [Model card](https://deepmind.google/models/model-cards/gemini-3-8-flash/), [evaluation method](https://deepmind.google/models/evals-methodology/gemini-3-8-flash), [current Gemini models](https://deepmind.google/models/gemini/)

One correction is essential: **three different papers use the VideoRAG name**. Several later papers cite Jeong’s paper but test Luo’s or Ren’s system. For example, SceneRAG mainly extends Ren; LVAgent and GCAgent test Luo. The [earlier-paper review](./research/video-rag-earlier-extensions.md) records these differences.

My assessment is that the useful research frontier is **better evidence selection, persistent memory, repeated search, and source verification**. For a research starting point, I would read **CARVE first**, then **MemDreamer**, and assess **GraMRAG** once its results can be reproduced.

I did not run the systems, and some publisher full texts were unavailable. Different tasks, models, judges, and processing budgets prevent a verified global SOTA claim.

> what is a common challenge across all that is yet to be solved

**The common open challenge is reliable evidence grounding: finding the evidence needed for an answer and proving that the answer follows from it.**

Across the papers reviewed, systems still struggle to do all four tasks together:

| Task                                      | What remains difficult                                                                                          |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **Find complete evidence**          | A relevant clip may contain only part of the answer. Other evidence can occur much earlier or in another video. |
| **Preserve time and relationships** | Selected frames and summaries can lose event order, object identity, or the links between actions.              |
| **Check the answer**                | A model can produce a plausible answer despite retrieving the wrong evidence.                                   |
| **Control cost**                    | More frames, searches, and verification steps increase processing time and cost.                                |

CARVE makes the evaluation problem clear: **a correct answer does not prove that retrieval worked**. Its benchmark therefore measures retrieval and generation separately. MemDreamer addresses long-range relationships with graph memory, but the answer still depends on what the earlier perception stage preserved. [CARVE](https://arxiv.org/html/2606.13141v2), [MemDreamer](https://arxiv.org/html/2606.07512v2)

For example, consider: *“Where did the person leave the keys before going outside?”* A system must find the right person, identify the keys, follow the sequence, and return the supporting moment. If that moment is missing, it must recognize the gap.

**A clear research question is:** *Can a video RAG system detect missing evidence, search again, and decline to answer when support remains insufficient—within a fixed processing budget?*

This is my synthesis of the reviewed papers. I did not test the systems under one shared evaluation.

Copied conversation

Source conversation: 01a1b207-8270-78b3-8607-d4fa92525d5b
