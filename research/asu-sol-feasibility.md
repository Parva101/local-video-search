# ASU Sol: small model project feasibility

Checked November 4, 2026. This note uses public documentation. It does not confirm the user's account limits or current queue state.

## Conclusion

A small, self-hosted tool-use model is a reasonable project to test on Sol. Start with one GPU and a 1B-4B parameter model. Use LoRA, or QLoRA if GPU memory is limited. This size is a planning estimate, not a measured fit or runtime promise. Model architecture, sequence length, batch size, and software affect the result. Hugging Face documents adapter training on a quantized base model, which supports this approach. [PEFT quantization guide](https://huggingface.co/docs/peft/developer_guides/quantization)

## Access and job limits

- Use `myaccounts` to see the account and QoS available to this user. General access in ordinary speech does not establish access to the Slurm `general` partition.
- `htc` with `public` QoS accepts CPU and GPU jobs for up to four hours without preemption. `public` supports jobs up to seven days.
- `general` with `private` QoS uses idle lab hardware. Owners can cancel these jobs. Cancelled jobs do not restart automatically; save checkpoints and resume them in a new job.
- Course access has separate limits. It must not be treated as standard research access.

These are published limits, not confirmed account permissions. [ASU partitions and QoS](https://docs.rc.asu.edu/partitions-and-qos/)

The current resource guide lists A100 80GB GPUs in `public`, `htc`, and `general`. H100 and H200 resources are listed in `general` and `htc`. Request a GPU type only after checking the account and available resources. `--mem` requests host RAM, not extra GPU memory. [ASU resource requests](https://docs.rc.asu.edu/requesting-resources/)

The hardware inventory includes private, reserved, and temporarily unavailable nodes. It is not a promise that a user can obtain each listed GPU. [ASU hardware inventory](https://docs.rc.asu.edu/supercomputer-hardware/)

Recent resource use affects queue priority. Plan for queue delays; do not promise a fixed project runtime from the GPU list alone. [ASU fairshare](https://docs.rc.asu.edu/fairshare/)

## Practical project plan

The following is a proposed plan, not an ASU requirement:

1. Confirm account QoS, then run a short one-GPU test. Record GPU model, memory use, and training speed.
2. Test the unchanged model on fixed tool-use tasks before training. Use public or newly created synthetic examples with clear use rights.
3. Train a small adapter. Save model, optimizer, and training state so the job can resume.
4. Compare the same model before and after training. Keep test tasks separate from training data. Report task success, wrong tool calls, latency, and peak GPU memory.
5. Save the adapter, data split, configuration, result files, and a short demo outside temporary cluster storage.

Run training and model inference in allocated compute jobs. ASU describes login nodes as suitable for simple, non-computational work. [ASU new user guide](https://docs.rc.asu.edu/new-user-guide/)

Use Sol for training and measured inference runs. A permanent public demo needs a separate hosting plan: the documented cluster allocations have finite duration. This is an inference from the job limits above, not a statement that ASU prohibits every form of service hosting.

Scratch storage is temporary and has no backup. Files not accessed for 90 days are subject to removal. Keep a separate copy of final checkpoints and results. [ASU scratch policy](https://docs.rc.asu.edu/scratch/)

No account was accessed and no GPU job was run. Exact memory fit, queue delay, runtime, local demo hardware, and model/data licenses remain unchecked.
