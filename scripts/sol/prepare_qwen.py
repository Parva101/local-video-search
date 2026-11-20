"""Download one immutable checkpoint in a scheduled CPU allocation."""

import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
import time

from huggingface_hub import snapshot_download
from packaging.version import Version

MODEL = "Qwen/Qwen3.6-27B"
REVISION = "6a9e13bd6fc8f0983b9b99948120bc37f49c13e9"


def main():
    assert os.environ.get("SLURM_JOB_ID"), "Run this through the scheduled preparation job"
    root, sif = map(Path, sys.argv[1:3])
    versions = {name: version(name) for name in ("vllm", "transformers", "torch", "huggingface-hub")}
    print(json.dumps({"event": "runtime_check", "versions": versions}), flush=True)
    if Version(versions["vllm"]) < Version("0.19.0"):
        raise RuntimeError("The selected container needs vLLM >=0.19.0; select a supported container explicitly")
    started = time.perf_counter()
    checkpoint = snapshot_download(
        MODEL, revision=REVISION, max_workers=4,
        allow_patterns=["*.json", "*.safetensors", "*.model", "*.txt", "*.jinja"],
    )
    config = json.loads((Path(checkpoint) / "config.json").read_text())
    if config.get("model_type") != "qwen3_5":
        raise RuntimeError("Unexpected checkpoint architecture")
    digest = hashlib.sha256()
    with sif.open("rb") as file:
        while block := file.read(8 * 1024 * 1024):
            digest.update(block)
    result = {"model": MODEL, "revision": REVISION, "checkpoint": checkpoint,
              "container": str(sif), "container_sha256": digest.hexdigest(),
              "versions": versions, "prepare_job_id": os.environ["SLURM_JOB_ID"],
              "prepare_seconds": time.perf_counter()-started}
    temporary = root / "prepared.json.tmp"
    temporary.write_text(json.dumps(result, indent=2)+"\n")
    temporary.replace(root / "prepared.json")
    print(json.dumps({"event": "prepared", **result}), flush=True)


if __name__ == "__main__":
    main()
