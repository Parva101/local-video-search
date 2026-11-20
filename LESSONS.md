When a scheduled sender targets a window by title and the wait is long, pin the window handle at arm time and use that handle at send time; window titles mutate (OpenCode renames its session window as the chat grows), and a send-time title lookup fails on the renamed window.

When a ctypes call fails with "function not found", check the function's documented owning DLL first; SetThreadExecutionState lives in kernel32, not user32.

When a clean Apptainer environment runs a Slurm GPU job, explicitly forward the scheduler's CUDA_VISIBLE_DEVICES mask.

When the user asks for performance research, rank paper-backed ideas first; implement only the selected experiments and judge them against a strong control.

When a short training gate precedes a long job, include validation and checkpoint save/load; batch timing alone does not test the epoch path.

When validating rounded model output, use the same numeric precision as its documented postprocessing; do not repair the output or use an arbitrary tolerance.

When clip recognition has no supporting sample timestamp, keep the raw judgments and return a localization abstention; keep invalid shapes, source bounds and duplicate-timestamp conflicts as errors.

When a stronger simple baseline beats a new method, report it first; do not claim a win from a weaker comparison.

When a model sees both a reference and new evidence, define each output field's scope explicitly; keep context support separate from new-evidence presence.

When the input fixes a model field's allowed values, send a role-specific response schema; do not rely only on a prompt and a later guard.

When a model output repeats a deterministic rule from validated fields, compute that field in code and record its derivation; do not ask the model to repeat the rule.

When creating an exact-byte JSON checkpoint on Windows, write canonical UTF-8 bytes; do not use text output that changes line endings.

When inserting new classes between an existing request class and its trailing decorated methods, re-read the file after the edit; a model_validator can silently attach to the wrong class and fail every later request with a confusing attribute error.

When a rebuilt container serves changed static assets, force-refresh the cached script before browser checks; a fresh HTML page can still run a stale script from the browser cache. Version asset URLs when they change.

When a pip pin conflicts with a dependency's own requirement (nncore's opencv-python next to our headless pin), both get installed into one target and the collision wins silently at import; constrain the dependency or install it with --no-deps.

When pip installs into a `--target` directory, its dependencies (including torch) land there and PYTHONPATH shadowing breaks the container's compiled operators; build a venv with `--system-site-packages` inside the container and pin the container's versions as constraints so incompatibilities fail at install time.

When a monitor cannot reach the system it watches, it must keep any existing alert and announce blindness; clearing the alert on a failed poll is worse than having no monitor.

# Lessons

- When a model uses separate description and verification prompts, test both on the failed recording and version each task without invalidating unrelated indexes.

- When a hosted gateway accepts a decoding option, test the actual reply before assuming it applied the option; version prompt changes and test the failed interval.
- When source verification finds a sub-action, measure full-event temporal overlap separately; a match status does not prove complete evidence.
- When a retrieval policy improves one known public example, keep it experimental and retain a fixed-pool baseline before making a wider claim.

- When a short-video smoke test passes, do not treat it as proof that long-video indexing is reliable; test long recordings and scene changes separately.

- When a model status requires related fields, encode that rule in the output JSON schema as well as local validation.
- When constrained JSON generation repeats whitespace, inspect the raw reply and use the runtime's supported compact-output setting; keep all output checks.
- When a serving runtime changes, check its pinned argument definitions before submitting a GPU job. A CUDA build can require a GPU even to display CLI help.

- When checking Python packages in an Apptainer image, disable user-site packages and record their paths before concluding that the image has the wrong version. A clean environment still mounts the user's home folder.

- When a model server returns metadata, redact credentials from headers and nested values before logging or storing its reply.
- When the coding assistant labels a smoke set, mark the labels as provisional and state that independent human review is still needed.
- When preparing an Apptainer image on Sol, use node-local temporary storage and check build options against the installed command before submitting a job.

- When implementing a retrieval baseline, state clearly that its embedding model does not replace the discussed vision-language model for descriptions and source-video verification, and report those stages as incomplete.
- When Voyager MCP is connected, use its account and job tools first and check submission-token health before asking the user to sign in again.
- When the user specifies a decision model, distinguish a dedicated classifier from a general LLM prompted to emit routing text.
- When video search must cover spoken discussion, index timestamped speech and subtitles alongside visual evidence.
