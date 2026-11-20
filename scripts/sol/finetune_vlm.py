"""LoRA fine-tuning of the pinned Qwen3-VL-4B base on exported app traces.

Runs inside the pinned vLLM research container on Sol with isolated research
packages; it changes no application dependency. Smoke mode (the default) runs a
short gate before any long training, mirroring the campaign's rules.
"""

import argparse
import json
import os
from pathlib import Path
import time

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


def load_dataset(path: Path, frames_root: Path, limit=None):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        content = []
        for part in row["messages"][0]["content"]:
            if part["type"] == "image":
                content.append({"type": "image", "image": str(frames_root / part["image"])})
            else:
                content.append(part)
        rows.append({"messages": [{"role": "user", "content": content},
                                  {"role": "assistant", "content": row["messages"][1]["content"]}],
                     "task": row["task"]})
        if limit and len(rows) >= limit:
            break
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-manifest", type=Path, default=Path(BASE_MANIFEST_DEFAULT))
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--per-device-batch", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--max-steps", type=int, default=20)
    args = parser.parse_args()
    started = time.monotonic()

    import torch
    import transformers
    import peft
    import trl
    event("versions", torch=torch.__version__, transformers=transformers.__version__,
          peft=peft.__version__, trl=trl.__version__, cuda=torch.cuda.is_available())

    base = load_manifest(args.base_manifest)
    event("base_verified", checkpoint=str(base))

    from transformers import AutoProcessor, AutoModelForMultimodalLM

    processor = AutoProcessor.from_pretrained(base, local_files_only=True, trust_remote_code=False)
    model = AutoModelForMultimodalLM.from_pretrained(
        base, local_files_only=True, trust_remote_code=False, use_safetensors=True,
        torch_dtype=torch.bfloat16, device_map=None,
    ).cuda().eval()

    from peft import LoraConfig, get_peft_model

    lora = LoraConfig(r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=0.05, bias="none",
                      task_type="CAUSAL_LM", target_modules="all-linear")
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()
    model.train()

    frames_root = args.data / "frames"
    train_rows = load_dataset(args.data / "train.jsonl", frames_root,
                              limit=64 if args.smoke else None)
    eval_rows = load_dataset(args.data / "eval.jsonl", frames_root, limit=8 if args.smoke else None)
    event("data_loaded", train=len(train_rows), eval=len(eval_rows), smoke=args.smoke)

    from trl import SFTConfig, SFTTrainer

    training_args = dict(
        output_dir=str(args.out),
        per_device_train_batch_size=args.per_device_batch,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.learning_rate,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_steps=5,
        save_strategy="epoch",
        bf16=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        remove_unused_columns=False,
        report_to=[],
        seed=2026,
        dataloader_num_workers=2,
    )
    if args.smoke:
        training_args.update(max_steps=args.max_steps, save_strategy="no", eval_strategy="no")
    else:
        training_args.update(num_train_epochs=args.epochs,
                             eval_strategy="steps", eval_steps=25, per_device_eval_batch_size=1)
    config = SFTConfig(**training_args, model_init_kwargs=None)

    def collate(features):
        texts, images = [], []
        for feature in features:
            text = processor.apply_chat_template(feature["messages"], tokenize=False, add_generation_prompt=False)
            texts.append(text)
            for part in feature["messages"][0]["content"]:
                if part.get("type") == "image":
                    images.append(part["image"])
        batch = processor(text=texts, images=[images] if images else None, padding=True,
                          truncation=True, max_length=4096, return_tensors="pt")
        labels = batch["input_ids"].clone()
        if "pixel_values_videos" in batch:
            raise ValueError("Video tensors must not appear for image-only fine-tuning")
        labels[labels == processor.tokenizer.pad_token_id] = -100
        batch["labels"] = labels
        return {key: value for key, value in batch.items() if key != "token_type_ids"}

    trainer = SFTTrainer(
        model=model,
        args=config,
        train_dataset=train_rows,
        eval_dataset=eval_rows or None,
        data_collator=collate,
    )
    event("training_start", smoke=args.smoke)
    trainer.train()
    adapter = args.out / ("adapter-smoke" if args.smoke else "adapter")
    model.save_pretrained(str(adapter), safe_serialization=True)
    processor.save_pretrained(str(adapter))
    event("training_complete", adapter=str(adapter), elapsed_seconds=round(time.monotonic() - started, 1))
    if args.smoke:
        gate = args.out / "smoke-gate.json"
        gate.write_text(json.dumps({"passed": True, "steps": args.max_steps,
                                    "train_samples_seen": len(train_rows)}, indent=2) + "\n", encoding="utf-8")
        event("smoke_gate_written", path=str(gate))


if __name__ == "__main__":
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    main()
