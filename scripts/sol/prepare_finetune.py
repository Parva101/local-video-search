"""Download and verify the pinned fine-tuning base checkpoint on Sol.

Records exact file hashes so the training job can prove it uses the same
checkpoint. No GPU work and no application changes happen here.
"""

import hashlib
import json
import os
from pathlib import Path
import time

MODEL_ID = "Qwen/Qwen3-VL-4B-Instruct"
REVISION = "ebb281ec70b05090aa6165b016eac8ec08e71b17"
FILES = [
    "chat_template.json", "config.json", "generation_config.json", "merges.txt",
    "model-00001-of-00002.safetensors", "model-00002-of-00002.safetensors",
    "model.safetensors.index.json", "preprocessor_config.json",
    "tokenizer.json", "tokenizer_config.json", "video_preprocessor_config.json",
    "vocab.json",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 ** 2), b""):
            digest.update(block)
    return digest.hexdigest()


def event(name, **fields):
    print(json.dumps({"event": name, **fields}), flush=True)


def prepare(root: str):
    started = time.monotonic()
    root = Path(root)
    cache = root / "huggingface"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    from huggingface_hub import snapshot_download

    event("download_start", model=MODEL_ID, revision=REVISION)
    path = snapshot_download(MODEL_ID, revision=REVISION, allow_patterns=FILES,
                             local_dir=cache / "qwen3-vl-4b-instruct")
    files = {}
    for name in FILES:
        item = Path(path) / name
        if not item.is_file():
            raise ValueError(f"Missing checkpoint file: {name}")
        files[name] = sha256(item)
    manifest = {
        "model_id": MODEL_ID, "revision": REVISION, "files": files,
        "checkpoint_path": str(Path(path).resolve()),
        "scope": "CPU download and hash verification only; no training or inference",
    }
    manifest_path = root / "base-model-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    event("manifest_written", path=str(manifest_path), files=len(files),
          elapsed_seconds=round(time.monotonic() - started, 1))
    data_dir = root / "data"
    if data_dir.is_dir():
        for name in sorted(p.name for p in data_dir.glob("*.jsonl")):
            event("supervision_recorded", file=name, sha256=sha256(data_dir / name))
    event("prepare_complete")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    prepare(parser.parse_args().root)
