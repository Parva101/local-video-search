# Self-improvement: your archive trains the model

Every time you use this app, it writes down what its model saw and said. Each indexed window stores the model's description. Each question you ask stores the model's check and its answer. Those rows are exactly the shape the fine-tuning pipeline eats. So the app makes its own next training set while you use it. This page shows the loop.

## The loop

1. **Use the app normally.** Import folders, upload clips, ask questions in the browser. Nothing extra to do. Description rows land in `description_windows`; each verified question lands in `verification_runs`.
2. **Export the traces.** With the Compose services up, from the repository root:

   ```bash
   python scripts/export_training_traces.py
   ```

   This writes `descriptions.jsonl` and `verifications.jsonl` (no-BOM JSONL) under `.codex-backups/finetune-data/` plus `traces-manifest.json` with row counts and SHA-256 hashes. It refuses to overwrite an earlier export unless you pass `--force`, and it prints the exact next commands. The export needs the source videos under `.codex-backups/finetune-data/media/` for the next step — new uploads must also be mapped in the builder's `UPLOAD_MAP`.
3. **Build the chat dataset.** The builder extracts the frames that were actually sampled back then, and pairs them with the recorded answers. It also holds out the coffee fixtures and every tenth window for evaluation, so training never sees the test:

   ```bash
   python scripts/build_finetune_dataset.py
   ```

4. **Merge the hard negatives.** Real discrimination needs wrong-time, same-scene answers next to right ones. The licensed Charades-STA pilot provides them; the merge script offsets frame groups so nothing collides:

   ```bash
   python scripts/build_hard_negatives.py
   python scripts/merge_finetune_datasets.py
   ```

5. **Train, smoke first.** LoRA fine-tuning of the pinned Qwen3-VL-4B base runs on Sol ([`scripts/sol/finetune_vlm.py`](../scripts/sol/finetune_vlm.py)). Run the local path pre-flight, then a 20-step smoke on the GPU, then the full run. Never a long run without a passing smoke.
6. **Let the acceptance eval decide.** The trained adapter generates on the held-out rows and is scored against the recorded hosted answers: JSON validity, verification status agreement, summary word overlap. A measured pass wires the adapter in as a pinned local revision. A fail keeps the hosted path and the negative result goes in [PLAN.md](../PLAN.md). The gate is agreement at equal tasks — nothing else gets claimed.

Steps 2-6 are the same commands every cycle. Use the app more, export more rows, retrain, re-evaluate.

## The caveat you must keep in mind

The recorded answers are the hosted teacher's answers. The export copies what the hosted model actually said, not what a human checked. So this flywheel **distills that teacher; it does not create ground truth**. If the teacher misread a frame, the student inherits the error at full strength. The honest labels in the pipeline come from elsewhere: the licensed pilot's grounded positives and same-video hard negatives, which carry human annotations.

Three consequences, stated plainly:

- The acceptance gate measures agreement with the teacher, not truth. Read it as "the local student caught up to its teacher on these tasks", nothing more.
- Wrong hosted answers do not cancel out. Indexing diverse footage and asking careful questions raises the mix; a single dominant recording skews it (the first 284-row export drew 253 rows from one clip).
- The hosted path stays the default until an eval says otherwise. The loop earns its claim one measured pass at a time.

## Where the records live

`.codex-backups/finetune-data/` holds the exports, the built dataset and the manifest. That folder is machine-local and git-ignored. The hashes in `traces-manifest.json` are how two machines prove they trained on the same bytes.
