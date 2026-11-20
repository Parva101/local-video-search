"""LoRA fine-tuning of the pinned Qwen3-VL-4B base on exported app traces.

Re-planned stack (third integration failure stopped trl/datasets iteration):
a plain PyTorch loop with peft LoRA and a collator under our control. Runs
inside the pinned vLLM research container on Sol; smoke mode gates any long
run; no application dependency changes.
"""

import argparse
import json
import math
import os
from pathlib import Path
import time

from PIL import Image

BASE_MANIFEST_DEFAULT = "/scratch/psheta12/video-search-finetune-20261120/base-model-manifest.json"


def event(name, **fields):
    print(json.dumps({"event": name, **fields}), flush=True)


def load_manifest(path: Path) -> Path:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    base = Path(manifest["checkpoint_path"])
    if manifest["model_id"] != "Qwen/Qwen3-VL-4B-Instruct" \
            or manifest["revision"] != "ebb281ec70b05090aa6165b016eac8ec08e71b17":
        raise ValueError("Base model manifest does not match the pinned checkpoint")
    missing = [name for name in manifest["files"] if not (base / name).is_file()]
    if missing:
        raise ValueError(f"Missing base files: {missing}")
    return base


def load_rows(path: Path, data_root: Path, limit=None):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        content, images = [], []
        for part in row["messages"][0]["content"]:
            if part["type"] == "image":
                content.append({"type": "image"})
                # Dataset builders may emit platform-specific separators; normalize.
                name = part["image"].replace("\\", "/").removeprefix("frames/")
                images.append(str((data_root / "frames" / name).resolve()))
            else:
                content.append({"type": "text", "text": part["text"]})
        rows.append({"prompt": [{"role": "user", "content": content}],
                     "answer": row["messages"][1]["content"], "images": images})
        if limit and len(rows) >= limit:
            break
    missing = [path for row in rows for path in row["images"] if not Path(path).is_file()]
    if missing:
        raise FileNotFoundError(f"Dataset image paths do not resolve: {missing[:3]}")
    return rows


def build_batch(samples, processor, device):
    texts, image_lists, prompt_lengths, opened = [], [], [], []
    for sample in samples:
        prompt_text = processor.apply_chat_template(sample["prompt"], tokenize=False,
                                                    add_generation_prompt=True)
        prompt_lengths.append(len(processor.tokenizer(prompt_text, add_special_tokens=False)["input_ids"]))
        full = sample["prompt"] + [{"role": "assistant", "content": sample["answer"]}]
        texts.append(processor.apply_chat_template(full, tokenize=False, add_generation_prompt=False))
        images = [Image.open(path).convert("RGB") for path in sample["images"]]
        opened.extend(images)
        image_lists.append(images)
    batch = processor(text=texts, images=image_lists, padding=True,
                      truncation=True, max_length=4096, return_tensors="pt")
    for image in opened:
        image.close()
    labels = batch["input_ids"].clone()
    labels[labels == processor.tokenizer.pad_token_id] = -100
    for row, length in enumerate(prompt_lengths):
        labels[row, :length] = -100
    batch["labels"] = labels
    # Pass the processor's full tensor contract through; guessing key names
    # (and dropping one the model needs) caused a whole failure class.
    return {key: value.to(device) for key, value in batch.items() if hasattr(value, "to")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-manifest", type=Path, default=Path(BASE_MANIFEST_DEFAULT))
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--per-device-batch", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--warmup-steps", type=int, default=3)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--batch-probe", action="store_true",
                        help="Build one batch on CPU, print keys and shapes, and exit without loading the model")
    args = parser.parse_args()
    started = time.monotonic()

    import torch
    import transformers
    import peft
    event("versions", torch=torch.__version__, transformers=transformers.__version__,
          peft=peft.__version__, cuda=torch.cuda.is_available())

    base = load_manifest(args.base_manifest)
    event("base_verified", checkpoint=str(base))

    from torch.utils.data import DataLoader
    from transformers import AutoProcessor, AutoModelForMultimodalLM

    processor = AutoProcessor.from_pretrained(base, local_files_only=True, trust_remote_code=False)
    processor.tokenizer.padding_side = "right"
    if args.batch_probe:
        rows = load_rows(args.data / "train.jsonl", args.data, limit=2)
        batch = build_batch(rows, processor, "cpu")
        keys = {key: list(value.shape) for key, value in batch.items()}
        event("batch_probe", keys=keys)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "batch-probe.json").write_text(json.dumps(keys, indent=2, sort_keys=True) + "\n",
                                                   encoding="utf-8")
        return
    model = AutoModelForMultimodalLM.from_pretrained(
        base, local_files_only=True, trust_remote_code=False, use_safetensors=True,
        dtype=torch.bfloat16, device_map=None,
    ).cuda()
    for parameter in model.parameters():
        parameter.requires_grad_(False)

    from peft import LoraConfig, get_peft_model

    lora = LoraConfig(r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=0.05, bias="none",
                      task_type="CAUSAL_LM", target_modules="all-linear")
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()
    model.train()
    device = "cuda"

    train_rows = load_rows(args.data / "train.jsonl", args.data, limit=192 if args.smoke else None)
    eval_rows = load_rows(args.data / "eval.jsonl", args.data, limit=8 if args.smoke else None)
    event("data_loaded", train=len(train_rows), eval=len(eval_rows), smoke=args.smoke)

    optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad),
                                  lr=args.learning_rate, weight_decay=0.0)
    steps_per_epoch = math.ceil(len(train_rows) / args.per_device_batch / args.grad_accum)
    total_steps = args.max_steps if args.smoke else max(1, steps_per_epoch * args.epochs)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer, max_lr=args.learning_rate, total_steps=total_steps,
        pct_start=0.1, anneal_strategy="cos")

    def run_batches(rows, train=True):
        losses = []
        loader = DataLoader(rows, batch_size=args.per_device_batch, shuffle=train,
                             drop_last=False, collate_fn=lambda batch: batch)
        for batch_rows in loader:
            batch = build_batch(batch_rows, processor, device)
            output = model(**batch)
            losses.append(float(output.loss.detach()))
        return losses

    optimizer_step = 0
    micro_step = 0
    trainable = [p for p in model.parameters() if p.requires_grad]
    for epoch in range(args.epochs if not args.smoke else 1):
        model.train()
        loader = DataLoader(train_rows, batch_size=args.per_device_batch, shuffle=True,
                            drop_last=True, collate_fn=lambda batch: batch)
        for batch_rows in loader:
            batch = build_batch(batch_rows, processor, device)
            output = model(**batch)
            (output.loss / args.grad_accum).backward()
            micro_step += 1
            if micro_step % args.grad_accum == 0:
                torch.nn.utils.clip_grad_norm_(trainable, 1.0)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
                optimizer_step += 1
                if optimizer_step % 5 == 0:
                    event("train_step", step=optimizer_step, loss=round(float(output.loss.detach()), 4))
                if args.smoke and optimizer_step >= args.max_steps:
                    break
        if args.smoke and optimizer_step >= args.max_steps:
            break
        eval_losses = run_batches(eval_rows, train=False) if eval_rows else []
        event("epoch_done", epoch=epoch + 1,
              eval_loss=round(sum(eval_losses) / len(eval_losses), 4) if eval_losses else None)
        adapter = args.out / "adapter"
        model.save_pretrained(str(adapter), safe_serialization=True)
        processor.save_pretrained(str(adapter))

    adapter = args.out / ("adapter-smoke" if args.smoke else "adapter")
    model.save_pretrained(str(adapter), safe_serialization=True)
    processor.save_pretrained(str(adapter))
    if args.smoke:
        gate = args.out / "smoke-gate.json"
        gate.write_text(json.dumps({"passed": True, "steps": optimizer_step,
                                    "train_samples_seen": len(train_rows)}, indent=2) + "\n",
                        encoding="utf-8")
        event("smoke_gate_written", path=str(gate))
    event("training_complete", adapter=str(adapter),
          elapsed_seconds=round(time.monotonic() - started, 1))


if __name__ == "__main__":
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    main()
