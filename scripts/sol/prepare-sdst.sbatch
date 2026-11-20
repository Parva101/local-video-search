#!/bin/bash
#SBATCH --job-name=video-sdst-data
#SBATCH --partition=public
#SBATCH --qos=class
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00

set -euo pipefail
ROOT="${SDST_ROOT:?Set SDST_ROOT to the new private reference directory}"
PREVIOUS="/scratch/$USER/video-search-temporal-20261114"
SIF="/scratch/$USER/video-search-qwen/vllm-0.20.0-cu129.sif"
COMMIT="ea8fa9fe1158c0bcdb60df2861450f4b69362f3e"
mkdir -p "$ROOT/logs"
[[ "$(df --output=avail -B1 "$ROOT" | tail -n 1)" -ge 107374182400 ]]
if [[ ! -d "$ROOT/upstream" ]]; then
    git init "$ROOT/upstream"
    git -C "$ROOT/upstream" remote add origin https://github.com/davidpujol/SDST.git
    git -C "$ROOT/upstream" fetch --depth 1 origin "$COMMIT"
    git -C "$ROOT/upstream" checkout --detach FETCH_HEAD
else
    [[ "$(git -C "$ROOT/upstream" rev-parse HEAD)" == "$COMMIT" ]]
    git -C "$ROOT/upstream" diff --exit-code HEAD
fi
python3 - "$ROOT" "$COMMIT" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root, commit = Path(sys.argv[1]), sys.argv[2]
upstream = root / "upstream"
assert subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip() == commit
subprocess.run(["git", "-C", str(upstream), "diff", "--exit-code", "HEAD"], check=True)
files = {}
for raw in subprocess.check_output(["git", "-C", str(upstream), "ls-files", "-z"]).split(b"\0"):
    if not raw:
        continue
    name = raw.decode("utf-8")
    path = upstream / name
    if path.is_symlink() or not path.resolve().is_relative_to(upstream.resolve()):
        raise ValueError("Unsafe tracked source path: " + name)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 ** 2), b""):
            digest.update(block)
    files[name] = digest.hexdigest()
payload = (json.dumps({"source_commit": commit, "files": files}, indent=2, sort_keys=True) + "\n").encode()
target = root / "source-identity.json"
if target.exists():
    assert target.read_bytes() == payload, "Existing source identity differs"
else:
    with target.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
print(json.dumps({"event": "host_source_verified", "source_commit": commit, "tracked_files": len(files)}), flush=True)
PY
apptainer exec --cleanenv --bind /scratch \
    --env PYTHONNOUSERSITE=1 --env PYTHONPATH="$PREVIOUS/python" \
    --env OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK" \
    "$SIF" python3 -u "$ROOT/project/scripts/sol/prepare_sdst.py" "$ROOT"
