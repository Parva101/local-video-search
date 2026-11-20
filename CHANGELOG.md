# Changelog

All notable changes to Local Video Search. Dates are 2026 (America/Phoenix).

## 0.2.0 — product completion release

- Reference-image questions: `image_base64` on `/search` and `/evidence-search`, pinned SigLIP2 image space, `unit-sum-text-image-l2-v1` recipe; browser attach control.
- Calendar scoping: capture dates per recording (explicit or file-derived bulk dating at the browser time zone), `start_date`/`end_date` filters, today/last-7/last-30 keyword detection with visible applied scopes.
- Speech and subtitle search: pinned local Whisper-base ASR through durable jobs, SRT/VTT import, `speech` search path with dense+lexical RRF; schema v6.
- Occurrence counting: `/count-events` with verified events, half-second merge, budget-bounded honest partial reporting; browser count mode.
- All-videos scope in the browser; per-recording visual and speech index controls.
- Pinned fine-tuning pipeline: Qwen3-VL-4B LoRA on exported production traces, smoke-gated with local-first validation; acceptance eval v2 reached 100 percent schema validity (see evaluation/finetune-adapter-eval-v2.json).
- Automated Sol job monitoring (scheduled task + alert file) and a 40-role team process (TEAM.md) for wave-based improvement.
- Schema upgraded v4 → v6 additively; 535+ model-enabled tests; every capability has a real browser end-to-end evidence file under evaluation/.
- MIT license; enterprise README with quick start, operations and sample-questions documentation.

## 0.1.0 — initial release

- Import (folder + uploads), durable leased jobs, visual (SigLIP2) search, hosted description indexing, hybrid fusion, bounded source verification, optional reranking, extent experiments, playback, saved traces.
