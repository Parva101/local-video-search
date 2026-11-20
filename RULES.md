# Project rules

[AGENTS.md](AGENTS.md) is the authoritative source for writing, coding, approval, planning, review, and record-keeping instructions. This file records the user's project requirements; it does not add new coding rules.

## User requirements

- Prefer Voyager MCP for ASU account access, documentation, job submission, and monitoring where supported. Reuse established authentication and avoid repeated manual sign-ins.
- Build an open-source project that users can download and run on their own computers.
- Accept a local directory containing one or more recorded video files and build a searchable index.
- Also provide a local browser flow to upload a video, index it, send text queries and inspect the answers.
- Distribute the local application and database setup with Docker Compose. Handle application package and database setup in the supplied project configuration.
- Focus on the backend pipeline before model training or fine-tuning.
- Support queries about visible actions, objects, event times, and counts, with source footage available as evidence.
- Support spoken-topic search through timestamped speech transcripts and existing subtitles/captions, alongside visual search. Link results to source recordings and time intervals.
- Use a dedicated classifier or discriminative typed-decision model before retrieval to choose the search path for each query, not a general chat LLM prompted to emit routing text or JSON. The backend builds the search plan from validated typed decisions. Initially test `perplexity-ai/pplx-decider-flash-v1.2` (4B); decide whether to keep it from measured performance. Thresholds and the final choice remain open.
- Support text queries and the discussed image-plus-text query format. Model capability and evaluation remain to be established.
- Allow existing analysis models, including optional closed-source APIs, while the final model choice remains open.
- Use local PostgreSQL with pgvector for SQL records and embeddings. Keep original video files in local file storage.
- Do not require a cloud database or hosted vector service for local indexing. Optional cloud model calls can have separate usage charges.

## Decision status

Record major choices and their reasons in [DECISIONS.md](DECISIONS.md). Keep proposals separate from confirmed decisions. A design proposal is not a claim that the software exists or that a benchmark result has been reproduced.

- Historical authorization, now superseded: the user allowed independent implementation for the previous indexing and chat.md improvement stage. The replacement AGENTS.md now requires inspection, explanation and approval before code changes.
- On 14 November 2026, the user authorized research-led performance experiments, implementation of the selected ideas and longer Sol training. Review existing research before choosing what to build. For a long submitted run, give the user its job details and expected duration; leave it running instead of repeatedly tailing it. Follow course-account limits and preserve unrelated jobs.
- On 19 November 2026, the user mandated autonomous implementation without per-step approval until the complete product works end to end: import, index, text and image questions, model-verified intervals with playback, counting use cases, real-upload testing, and an honest best-in-class evaluation. Skip the SDST route. Keep the AGENTS.md discipline of plans, proof, tests and honest limits.
- On 20 November 2026, the user required automated monitoring for long Sol jobs: never wait for the user to report failures. Keep the "VideoSearchSolMonitor" scheduled task healthy, add every new long job to `.codex-backups/sol-monitor/watch.json`, and treat `ALERT.md` as the first thing any session reads.
