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
1. Project description: a self-hosted video archive search app, public at github.com/Parva101/local-video-search under MIT. Import a folder or upload a video, index visual/description/speech evidence, ask text or image questions, and get model-checked timestamped intervals with playback and occurrence counting.
2. Capabilities shipped under the 19 November 2026 autonomous mandate: reference-image queries (pinned SigLIP2 space, unit-sum-text-image-l2-v1); capture dates with file-derived bulk dating and calendar scoping (today/last-7/last-30 days with visible keyword detection); local Whisper-base ASR plus SRT/VTT subtitle import with a speech search path; budget-bounded occurrence counting via /count-events with half-second merge and honest partial reporting; an all-videos scope in the browser. Schema is v6 (additive migrations; live upgrades v4 to v5 to v6 proved). The earlier visual/description/hybrid paths, bounded verification, reranking and extent experiments are unchanged.
3. Benchmark and research: the private Charades-STA pilot (1,460-attempt ledger) and its results remain unchanged and closed. UniVTG training reproduced the released reference (60.04% vs 60.19% full test) and the IoU-quality adaptation was rejected. SDST is skipped: both runtime jobs failed on libGL (nncore reintroduced the GUI OpenCV wheel) and Google Drive still blocks the data archive. Any future benchmark claim must name its comparison class.
4. Results and validation: 535 model-enabled Docker tests pass, two private-checkout skips, two existing warnings. Every new capability has a real browser end-to-end proof saved under evaluation/ (image-query, calendar-scoping, speech-search, event-counting result JSONs), all with zero console errors. The hosted ASU Gemma service is configured in the ignored .env.
5. Remaining: a fresh-machine Compose run before broad announcements; nonzero audio-origin ASR offsets; the fresh untouched-benchmark evaluation (mandate stage 7); Decider routing and OCR remain unbuilt. Speech and counting stay labelled experimental.
6. Records: DECISIONS.md, RULES.md, LESSONS.md and PLAN.md are current through the release. Work continues autonomously under the 19 November mandate with plans, proof and honest limits.
