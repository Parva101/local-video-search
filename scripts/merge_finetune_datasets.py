"""Merge the distillation dataset with the hard-negative dataset for training.

Both builders emit the same JSONL schema with image paths relative to a
dataset root ('frames/NNNNN/PP.jpg'). Frame group names collide between the
two, so hard-negative groups are copied with an index offset and their paths
rewritten. Licensed pilot frames stay inside ignored private storage.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 ** 2), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def rewrite(samples, offset):
    for sample in samples:
        content = sample["messages"][0]["content"]
        for part in content:
            if part.get("type") == "image":
                head, _, tail = part["image"].rpartition("/")
                group = head.rpartition("/")[2]
                part["image"] = f"{head.rpartition('/')[0]}/{int(group) + offset:05d}/{tail}"
    return samples


def write(path: Path, samples):
    with path.open("w", encoding="utf-8") as stream:
        for sample in samples:
            stream.write(json.dumps(sample, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distillation", type=Path, default=Path(".codex-backups/finetune-data/dataset"))
    parser.add_argument("--hard-negatives", type=Path, default=Path(".codex-backups/hard-negatives-dataset"))
    parser.add_argument("--output", type=Path, default=Path(".codex-backups/finetune-data/merged-dataset"))
    args = parser.parse_args()
    started = time.monotonic()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    merged_frames = output / "frames"
    if not merged_frames.exists():
        shutil.copytree(args.distillation / "frames", merged_frames)
    groups = {int(item.name) for item in merged_frames.iterdir() if item.is_dir()}
    offset = (max(groups) + 1) if groups else 0
    copied = 0
    for group in sorted((args.hard_negatives / "frames").iterdir()):
        if not group.is_dir():
            continue
        target = merged_frames / f"{int(group.name) + offset:05d}"
        shutil.copytree(group, target)
        copied += 1
    train = load(args.distillation / "train.jsonl") + rewrite(load(args.hard_negatives / "train.jsonl"), offset)
    evaluation = load(args.distillation / "eval.jsonl") + rewrite(load(args.hard_negatives / "test.jsonl"), offset)
    write(output / "train.jsonl", train)
    write(output / "eval.jsonl", evaluation)
    manifest = {
        "train": len(train), "eval": len(evaluation), "frame_group_offset": offset,
        "hard_negative_groups_copied": copied,
        "distillation_train": len(load(args.distillation / "train.jsonl")),
        "distillation_eval": len(load(args.distillation / "eval.jsonl")),
        "train_sha256": sha256(output / "train.jsonl"), "eval_sha256": sha256(output / "eval.jsonl"),
        "hard_negative_sha256_train": sha256(args.hard_negatives / "train.jsonl"),
        "hard_negative_sha256_test": sha256(args.hard_negatives / "test.jsonl"),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"event": "merge_complete", **manifest,
                      "elapsed_seconds": round(time.monotonic() - started, 1)}), flush=True)


if __name__ == "__main__":
    main()
