# Project team — Local Video Search

An organization of 40 specialist roles, all running as GLM-5.3 subagents in waves.
Rule one: an agent never edits outside its lane. Rule two: every wave is reviewed,
tested, committed and pushed by the tech lead (the main session) before the next
wave starts. Rule three: every agent reports in at most five lines: what it built,
what it proved, what it gave up.

## Squads, roles and lanes

### Search & Retrieval (6)
1. Visual search engineer — `store.search_visual`, encoder contract
2. Text/description search engineer — `store.search_descriptions`, reranker bridge
3. Speech search engineer — `store.search_speech`, transcript ranking
4. Fusion & ranking engineer — RRF policies, hybrid scoring
5. Coverage & reporting engineer — scope/coverage semantics across paths
6. Search performance engineer — latency, indexes, query plans

### Verification & Evidence (5)
7. Verifier contract engineer — `vlm.py` prompts and schemas
8. Boundary/extent engineer — `extent.py` controllers
9. Counting engineer — `/count-events` partitioning and merge
10. Trace & export engineer — saved traces, evidence integrity
11. Negative-query honesty engineer — absence claims, abstentions

### Speech & Transcripts (4)
12. ASR engineer — `speech.py` transcription quality and speed
13. Subtitle engineer — SRT/VTT parsing and import UX
14. Audio-origin engineer — nonzero stream origins, offset correction
15. Transcript UX engineer — speech cards, playback, labels

### Training squad (5)
16. Dataset engineer — `build_finetune_dataset.py`, hard negatives
17. Trainer engineer — `finetune_vlm.py` loop and checkpoints
18. Eval harness engineer — acceptance metrics and reports
19. Distillation engineer — teacher record cleaning, dedupe
20. Flywheel engineer — supervision capture during app use

### Frontend & UX (6)
21. Search UX engineer — query form, paths, scopes
22. Evidence presentation engineer — answer cards, playback
23. Corpus UX engineer — all-videos, library, dates
24. Accessibility engineer — labels, focus, contrast
25. Mobile engineer — responsive behavior
26. Polish engineer — visual consistency, microcopy

### Platform (5)
27. Jobs/worker engineer — leases, retries, recovery
28. Migration engineer — schema versions, upgrade paths
29. Backup/restore engineer — dump/restore tooling and docs
30. Monitoring engineer — `monitor_sol_jobs.ps1`, alerting, ops log
31. Security engineer — headers, secrets, upload hardening

### Quality (5)
32. Backend test engineer — store/API/worker coverage
33. Frontend test engineer — static/UI checks, browser flows
34. Regression engineer — full-suite health, flake control
35. Release engineer — versioning, changelog, tag hygiene
36. Fresh-install engineer — clean-machine Compose validation

### Research (4)
37. Benchmark engineer — stage-7 untouched evaluation design
38. Routing engineer — Decider experiment
39. OCR engineer — screen text as a source type
40. Best-in-class analyst — honest comparisons for every claim

## Wave plan

Waves run 4-6 parallel agents on non-overlapping lanes. Each wave ends with:
review → full model-enabled test suite → commit → push → PLAN.md note.
Wave 1 (in flight): backend tests (32), docs & sample questions (product),
hard-negative dataset builder (16), frontend polish (21/24/26), API/store
hardening (9/31). Integration owner: the main session.
