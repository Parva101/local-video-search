**Talking to me**

Always talk in ASD-STE100 Simplified Technical English. Alway follow  Zinsser's four principles of quality writing:

1. Simplicity
2. Brevity
3. Clarity
4. Humanity

Cut the clutter. Keep the writing warm and human - a person wrote it, not a manual.


**Coding Rules**

- Always maintain a DECISIONS.md file which you update with all the major decisions we take and even if evaluate multiple paths but end up going with one clearly mention why, if not sure ask user.
- Also create a RULES.md and note down all rules that I mention but dont make unecessary rules if needed confirm with me.
- Avoid monkeypatching until specifically instructed by me and get approval from me if doing small patch edits.

* Keep diffs small; prefer targeted edits over wide refactors unless the full refactor is the explicit task or somthing we specifically discuss.
* Before writing new logic, search with `rg` for existing implementations.
* Follow YAGNI — do not add abstractions for speculative future use cases.

## 1. Plan before you touch code

- Before editing code to solve a bug or change behavior, inspect the issue first. Explain the evidence, the proposed solution, and any uncertainty. Ask the user for approval before making the edit. Do not assume the user's intended behavior when it is unclear.
- Make the plan extremely concise. Sacrifice grammar for the sake of concision.
- At the end of each plan, give me a list of unresolved questions to answer, if any.
- Long task: first tell me in 2-3 sentences what you think I'm after
- Start only after I say yes
- Write the steps to 'PLAN.md"
  each with how you'll prove it works
- Two failed tries on one step: stop, note what failed, re-plan
- Pausing mid-task: leave 'PLAN.md' so a new session can pick it up

## 2. Smallest change that works

Stay inside this task. Don't break anything that already works

- Tradeoff? Weigh UX (users), DX (the next dev) and AX (the next agent)
- No new dependencies, renames or refactors nobody asked for
- Back up before deleting or overwriting anything

## 3. Split work across subagents

- Explorer reads, worker edits, reviewer only reports and never edits
- Each gets one job, a done condition and a 5-line report
- Parallel is fine. Two agents on the same file is not
- Check the key claim in a report before you build on it

## 4. Own the bug

Reproduce it with my steps first. Can't reproduce it? Tell me what you need
Fix the cause, then run the same steps again
Never silence an error to make it go away
Verify before you say done
Run the tests and read the output yourself
UI: open it and try to break it: empty input, double submit, refresh
Didn't
run a check? Say so. An unrun check is not a pass
Report in 2-3 lines: what you picked, what you gave up, and why
6.
Write
down every correction
When I
correct you, add a line under Lessons: "When X, do Y"
Same mistake twice: the lesson is unclear. Rewrite it
Ask me before changing anything above Lessons

## 5. Error Handling

* Raise errors explicitly at the point of failure; never swallow exceptions silently.
* Use specific error types; avoid generic catch-alls that hide root causes.
* Fix root causes, not symptoms; no workaround shims unless the root fix is out of scope.
* No fallbacks or degraded-mode logic unless explicitly requested.
* External service calls: retry with exponential backoff, log each retry as a warning, re-raise the last error.
* Error messages must include: request params, response body, status codes, correlation IDs.
* Use structured logging fields — do not interpolate dynamic values into message strings.

## 6. Agentic Loops

* Treat an agent as an LLM calling tools in a loop: **Observe → Reason → Act → repeat** until a stop condition is met.
* Design long-running loops to be resumable. Persist checkpoints, scratchpads, or explicit state so work can continue after interruption.
* Scale effort to task complexity. Give explicit step budgets, completion criteria, and verification checks so the agent knows when to stop.
* Prefer append-only context for loop state when practical. Avoid rewriting prior observations just to restate them.
* Keep failed tool results and error evidence in context unless they contain sensitive data; the agent uses them to avoid repeating mistakes.

##7. Memory & Context
Design for four memory layers: working (current session), episodic (history), semantic (facts), and procedural (rules such as AGENTS.md).
For long tasks, externalize the plan and current progress to a scratchpad, state field, or task tracker and re-read it regularly to prevent drift.
Apply four context strategies deliberately: write, select, compress, and isolate.
Protect high-priority constraints and safety rules from decay or summarization; compact stale low-value context instead of letting it grow forever.
Keep execution traces for non-deterministic systems — every model call, tool action, and state transition should be inspectable.

# Lessons

Maintatin a LESSONS.md file. Newest on top. Delete what no longer applies.

## Project codebase
Keep updating this section below with relavant things as instructed:
1. Project description: A local video archive search application that imports recordings and retrieves candidate source intervals from text queries.
2. Capabilities: Docker app at localhost:8000 supports uploads, durable jobs, visual/description/hybrid retrieval, pinned optional reranking, bounded source checks, saved traces and playback. Schema v4 is intact. All 281 original description rows match the backup. The current 205-window index is ready; 48 earlier windows remain preserved. Gemma description v2, verification JSON v2 with point evidence, and extent task v5 have separate identities. Experimental missing-edge and uniform controllers keep sample brackets separate from raw evidence. Context recognition without a sample timestamp returns a logged localization abstention. Invalid shapes, source bounds and duplicate-timestamp conflicts still raise.
3. Benchmark: selective private Charades-STA preparation, an isolated PG schema, a durable 1,500-attempt gateway and complete-grid reports are implemented. The final exploratory pilot has 53 development queries and 69 evaluation queries from 25 videos, with all 207 comparison cases complete at two checks/16 slots each. An audit reused 53 development and 87 evaluation cases with unchanged raw results; 120 evaluation cases ran fresh. Old freezes and errors remain intact. The global ledger has 1,460 unique attempts; cached costs are counted once. No untouched-test, full-dataset SOTA or novelty claim is supported.
4. Results and validation: 377 model-enabled tests passed. Real browser controls and labelled UI network fixtures passed. API, worker and database are healthy; the test database is stopped. Extent R@1 at IoU 0.5 is 33.33%, uniform inspection 30.43%, and reranked retrieval 42.03%. Extent mean IoU is 28.86%, versus 35.89% for reranked retrieval. Stricter R@1 at IoU 0.7 improves to 13.04%, versus 4.35%, but 6 of 11 model-complete proposals fail localization at IoU 0.5. The new method stays optional. See README.md, PLAN.md, DECISIONS.md and evaluation/charades-point-aware-pilot-results.json. Licensed media, queries, labels and traces stay in ignored private storage.
5. Remaining: independent long-video/negative-query evaluation and reliable full-event localization. Speech/subtitle search, event counts, Decider and image-reference queries are unbuilt. No training or Sol job started. Future implementation requires inspection and approval under the instructions above.
6. Current approved campaign (14-15 November 2026): the user authorized research-led experiments and Sol training. The caption-curve pilot reaches 43.48% R1@IoU0.5 and 40.66% mean IoU, versus 42.03%/35.89% on the old exposed 69-query set; the recall interval includes zero. Training job 1488158 completed six 100-epoch UniVTG runs in 4h35m4s. Evaluation 1527713 completed all eight 3,720-query comparisons. Baseline mean R1@IoU0.5 is 60.04%, quality-target training 58.80%; reject the adaptation. The released reference at native batch4 reproduces 60.19%. Results: evaluation/trained-temporal-full-test-results.json and research/trained-head-results-2026-11-14.md. All sources, selected checkpoints and complete-grid identities were checked. Latest model-enabled Docker regression: 518 passed, two private-checkout skips, two existing warnings. Both skipped tests passed separately on the host. Original app defaults/indexes and the 1,460-attempt ledger remain unchanged. No novelty or SOTA is proved. Item 5's no-training statement is historical and superseded.
7. SDST preparation (15 November 2026): pinned source/checkpoint and exact archive checks are implemented in separate research scripts. Data job 1608962 failed before download; bounded Sol and later local probes proved Google Drive quota exceeded. No local archive or background transport is active. One delayed data retry, job 1609447, is scheduled after 24 hours; full data checks remain required. Runtime jobs 1609074 and 1609248 both failed before image layers due to Docker registry TLS timeouts. Under the two-failure rule, stop that path. A written re-plan verified the exact same image manifest/config and all 16 layer headers at Google's registry mirror. New CPU runtime job 1609446 uses that explicit mirror with unchanged image digest; estimated 20-60 minutes, two-hour wall limit. Both new jobs use zero GPUs. See PLAN.md and research/sdst-network-replan-2026-11-15.md; logs and source identities are in .codex-backups/sdst-launch-20261115. Keep sources frozen and leave long jobs for the user to check. Next: verify both preparations, then a short A100 ROI numeric, strict checkpoint and real-feature gate. No SDST GPU job, training or benchmark result exists yet.
