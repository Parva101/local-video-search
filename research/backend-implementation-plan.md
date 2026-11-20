# CCTV search backend: implementation proposal

Date: November 5, 2026.

## Decision and current evidence

The user wants the backend pipeline first. Model training is deferred until the pipeline works. The workspace currently contains research notes and no application code, tests, package configuration, or existing callers to preserve. This document proposes a new backend; source-code implementation requires user approval under the supplied AGENTS.md instructions.

The research reference is [ForeSea](https://arxiv.org/html/2603.22872v1), a March 2026 preprint. Its pipeline uses tracking, multimodal indexing, retrieval, and video-model analysis of candidate clips. This project adapts that structure; it does not claim to reproduce the paper's results.

## First usable workflow

Import recorded videos, process them in durable jobs, search by description with explicit camera/time filters, analyze candidate clips with an existing video-capable model, and return playable source intervals. Export selected clips with a source manifest. No model fine-tuning is required for this phase.

Also support spoken-topic queries, such as finding a meeting where Project XYZ was discussed. Index timestamped speech transcripts and supplied subtitles/captions alongside visual evidence. This is a confirmed requirement; the processing and search design below remains proposed.

Use a dedicated classifier or discriminative typed-decision model before retrieval to choose the query's search path, not a general chat LLM prompted to emit routing text or JSON. This is a confirmed direction; fixed labels or independent yes/no decisions and support for several paths on mixed queries remain proposals. The backend constructs the executable search plan. Initially evaluate the 4B checkpoint [`perplexity-ai/pplx-decider-flash-v1.2`](https://huggingface.co/perplexity-ai/pplx-decider-flash-v1.2); it is not a proven production default. The local laptop has a 16 GB RTX 3080 and about 32 GB RAM; the 27B candidates exceed the GPU's BF16 weight budget. Checkpoint access, runtime fit, speed, and accuracy remain unverified. Thresholds, calibration, and final model choice remain open. See [the classifier benchmark plan](../PLAN.md).

## Proposed implementation

- Python and FastAPI for the backend.
- PostgreSQL for recordings, jobs, processing coverage, searches, and evidence records.
- pgvector for searchable embeddings in the same database. Start with exact vector search; choose approximate indexing only after measurements justify it. [pgvector documentation](https://github.com/pgvector/pgvector)
- FFmpeg and ffprobe for media inspection, timestamp-preserving decoding, preview generation, and clip export.
- Local managed media storage for the first deployment.
- One separate worker process using a PostgreSQL jobs table. Use atomic job claiming, leases, progress records, bounded retries, and recovery after worker termination.
- Docker Compose for the database and repeatable local startup. GPU processing remains a separately scheduled worker where needed; do not assume course-account Sol is a permanent server.

This is one application with an interface process and a worker, not a collection of microservices.

## Processing and search

1. Register a recording and camera, verify the media, calculate a content hash, and retain the original. Store UTC capture start only when supplied by trusted metadata or the user. Do not infer capture time from a filename or filesystem modification time without an explicit rule.
2. Create overlapping time windows. Generate preview media and sampled frames with a mapping to source presentation timestamps. Preserve enough scene context for actions involving objects and locations.
3. Add pretrained detection and within-recording tracking to create person/object-focused candidates in a separate milestone. Keep the full-scene search path so missed detections do not remove all access to a source interval. Track IDs are local to a recording; they are not identities across cameras.
4. Build three retrieval paths: visual embeddings of frames/clips, text embeddings of generated visual descriptions, and text embeddings of speech transcripts or supplied subtitles/captions. Use compatible query and source encoders for each path. Initial pooled-frame embeddings are a retrieval baseline whose motion limitations must be measured. Store the source type, encoder identity, generating model when applicable, and preprocessing version with each record. A changed embedding model requires a separately built index.
5. For audio selected for speech recognition, transcribe the source audio once into timestamped segments. Chunk speech and subtitles by speech boundaries and surrounding context, independently of the visual windows. Retain source offsets so a text chunk can link to one or more visual windows. Keep supplied subtitles, speech-recognition output, and generated visual descriptions distinct. The speech-recognition model and subtitle/transcript precedence remain open. A recording without audio or subtitles has no speech/subtitle path; this expected absence is distinct from a processing error and must not trigger a silent provider fallback.
6. Run the dedicated classifier before retrieval. Proposed input: query text, reference-image presence, and available index/modality metadata. Proposed output: scores for fixed route labels or independent yes/no decisions for visual embeddings, generated visual-description text, and transcript/subtitle text. Validate the typed decisions; the backend then constructs the executable search plan using the existing query and explicit filters and find/count intent where supplied. The classifier does not generate free-form filters, query rewrites, explanations, or arbitrary plans. Several paths for mixed visual/spoken queries remain proposed, not an explicit user rule. Record the structured routing decision, classifier model, and version. Make invalid decisions/plans and unavailable required modalities visible; do not silently switch paths. Routing does not establish evidence or generate the final answer. Do not silently guess ambiguous dates or timezones.
7. Execute the validated search plan with its explicit filters. Propose keyword and semantic search over the selected text paths to cover names such as Project XYZ and topic paraphrases. When several paths are selected, combine candidate rankings without treating scores from different encoders as interchangeable. Retrieve candidate intervals and group overlapping results.
8. Pass the candidate evidence and query to an analysis model with the required input capability. Visual questions need video or timestamped frames; spoken-topic questions use source-linked transcript/subtitle excerpts and their context. A visual description is not evidence of spoken words, and transcription output alone does not establish speaker identity. Validate structured results with match status, interval(s), and a short evidence description. Check that times are finite, ordered, and within the supplied source interval, then map them back to the source recording.
9. Return source IDs, source offsets, available capture timestamps, previews, surrounding context, and supporting transcript/subtitle excerpts for speech matches. Treat provider output as a proposed match. A retrieval score is not a probability that an event occurred.
10. Export a selected interval by re-encoding when accurate boundaries are required. Include a manifest with source hash, time offsets, processing version, model identity, and query. Do not describe this manifest as a legal chain-of-custody certification.

## Replaceable analysis models

Keep these interfaces distinct:

- Routing interface: score fixed route labels or independent yes/no questions from query and index/modality metadata. The backend validates typed outputs and constructs the search plan from them and existing query inputs. No free-form plan generation; no evidence or final answer generation. Perplexity Decider Flash v1.2 (4B) is the initial evaluation choice; thresholds, calibration, and final model choice remain open.
- Embedding interface: produce compatible query/source representations for each retrieval path. Visual and text paths can use different encoders; keep their versions separate.
- Analysis interface: inspect retrieved media or source-linked transcript/subtitle context and return structured event intervals. Validate each provider's input capabilities.

Implement the analysis interface first with Gemini, then with a local or remote server that supports an OpenAI-compatible multimodal endpoint. Validate both against the same output contract. Credentials remain in environment configuration. No paid model calls will run during ordinary automated tests.

Provider-specific media preparation stays inside its adapter. Video-capable providers receive supported video input; frame-capable providers receive ordered frames with timestamps. A text-only LLM cannot directly inspect footage: a caption-based route would need a captioning model and would be a separate baseline. Changing analysis provider should not require rebuilding embeddings. Changing the embedding model does.

Do not silently fall back to another provider after errors. Record timeouts, invalid responses, rate limits, and failed coverage separately from no-match results. Preserve configuration and attempt records so failures can be reproduced.

## External interface

Proposed endpoint groups:

| Interface | Behavior |
| --- | --- |
| Register camera / import recording | Validate input, store source metadata, return recording and job IDs |
| Get job / recording status | Return progress, failed intervals, and indexed coverage |
| Submit search / get search | Accept query, explicit filters, and chosen analysis provider; return asynchronous status and evidence results |
| Read evidence media | Serve only registered assets with byte-range support |
| Request export / get export | Produce an accurate clip and source manifest through a durable job |
| Record review | Save accepted/rejected results and corrected time intervals |

Apply pagination and bounded query/media sizes. Accept media uploads or administrator-configured import roots; never expose arbitrary filesystem reads through request paths. Bind locally by default and require authentication before access from other machines. Serve registered media by opaque ID, not user-supplied path. Use separate job states for queued, running, succeeded, and failed.

## Scope across files and dependencies

Implementation must include package configuration, backend modules, database schema/migrations, worker entry point, media utilities, encoder and provider adapters, environment example, Compose startup, tests, fixtures, and operating instructions. There are no existing exports or callers in this workspace.

Primary integrity risks are incorrect timestamps, lost work after worker interruption, duplicate imports or jobs, incomplete search coverage, and fabricated model intervals. Primary access risks are unsafe media paths and unintended media or credential exposure. These need concrete handling in the initial implementation.

## Milestones and checks

1. Import, durable jobs, media storage, source timing, and status. Check corrupt media, duplicate content, worker restart, and variable frame rate/time mapping.
2. Visual, description, and speech/subtitle retrieval, filtered search, result grouping, and playback/export. Check time filters, overlapping intervals, index-version mismatch, clip boundaries, and missing coverage. Include a meeting-topic query, exact project-name and paraphrase queries, transcript/source time mapping, absent audio/subtitles, and explicit transcription failures. No transcription or retrieval accuracy is assumed before these checks.
   Routing checks: speech-only, visual-only, mixed visual/spoken, unavailable required modality, and invalid typed output or backend plan. Check fixed-label decisions and calibration before choosing thresholds. Compare end-to-end evidence recall with an all-path search baseline to measure whether routing loses relevant evidence. These are verification criteria, not completed tests.
3. Pretrained tracking and focused candidates, measured against the full-scene baseline. Check that detection failures do not erase indexed coverage.
4. Gemini and local-compatible analysis adapters, structured output validation, and source evidence. Check timeouts, malformed outputs, out-of-range times, no-match cases, and stable index use when providers change.
5. End-to-end evaluation and operational handoff. Use a small rights-cleared, manually reviewed video set; measure candidate recall, final interval accuracy, indexing throughput, query latency, and restart behavior. Use a short synthetic media fixture for deterministic timing tests; it is not a semantic retrieval benchmark.

The first usable release must complete import -> index -> query -> analyze -> source playback/export. A fake provider may support deterministic tests, but does not satisfy the runtime model integration milestone.

## Deferred work and uncertainty

Defer fine-tuning, reinforcement learning, live RTSP ingestion, cross-camera identity matching, and a custom frontend. The backend can be exercised through its generated interactive documentation and a small end-to-end client.

Provider credentials, local Docker/FFmpeg availability, selected encoder accuracy, pretrained detector/tracker compatibility, data download rights, actual Sol access, and performance remain unverified. Choosing the exact pretrained retrieval/tracking models requires a small compatibility and license check before their implementation. Do not claim production readiness, complete retrieval, or paper-level accuracy before measurement.
