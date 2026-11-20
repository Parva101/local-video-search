#!/bin/bash
#SBATCH --job-name=video-sdst-runtime
#SBATCH --partition=public
#SBATCH --qos=class
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00

set -euo pipefail
umask 077
ROOT="${SDST_ROOT:?Set SDST_ROOT to the new private reference directory}"
IMAGE="docker://mirror.gcr.io/pytorch/pytorch@sha256:42204bca460bb77cbd524577618e1723ad474e5d77cc51f94037fffbc2c88c6f"
CLIP_COMMIT="a1d071733d7111c9c014f024669f959182114e33"
mkdir -p "$ROOT/logs" "$ROOT/runtime-images" "$ROOT/runtime-cache"
exec 9>"$ROOT/.runtime.lock"
flock -n 9
export APPTAINER_CACHEDIR="$ROOT/runtime-cache"
SIF="$ROOT/runtime-images/pytorch-2.2.1-cu121.sif"
SCRIPT="$ROOT/project/scripts/sol/prepare_sdst_runtime.py"
if [[ ! -e "$SIF" ]]; then
    LOCAL_ROOT=$(mktemp -d "/tmp/video-search-sdst-$SLURM_JOB_ID-XXXXXX")
    export APPTAINER_TMPDIR="$LOCAL_ROOT"
    printf '{"event":"image_build_start","job":"%s"}\n' "$SLURM_JOB_ID"
    apptainer build --mksquashfs-args "-processors $SLURM_CPUS_PER_TASK -mem 8G" \
        "$LOCAL_ROOT/runtime.sif" "$IMAGE"
    # Copy fully before publishing the final name across filesystems.
    cp "$LOCAL_ROOT/runtime.sif" "$SIF.$SLURM_JOB_ID.partial"
    ln "$SIF.$SLURM_JOB_ID.partial" "$SIF"
    sha256sum "$SIF" > "$ROOT/runtime-images/image.sha256"
    printf '%s\n' "$IMAGE" > "$ROOT/runtime-images/image-source.txt"
    printf '{"event":"image_build_complete"}\n'
fi
[[ "$(cat "$ROOT/runtime-images/image-source.txt")" == "$IMAGE" ]]
sha256sum --check "$ROOT/runtime-images/image.sha256"
if [[ -e "$ROOT/runtime" ]]; then
    apptainer exec --cleanenv --bind /scratch \
        --env PYTHONNOUSERSITE=1 --env PYTHONDONTWRITEBYTECODE=1 \
        --env PYTHONPATH="$ROOT/runtime/python" --env OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK" \
        "$SIF" python3 -u "$SCRIPT" verify "$ROOT/runtime" "$SIF"
    exit 0
fi
STAGE=$(mktemp -d "$ROOT/runtime-staging-$SLURM_JOB_ID-XXXXXX")
git init "$STAGE/clip-git"
git -C "$STAGE/clip-git" remote add origin https://github.com/openai/CLIP.git
git -C "$STAGE/clip-git" fetch --depth 1 origin "$CLIP_COMMIT"
git -C "$STAGE/clip-git" checkout --detach FETCH_HEAD
[[ "$(git -C "$STAGE/clip-git" rev-parse HEAD)" == "$CLIP_COMMIT" ]]
git -C "$STAGE/clip-git" diff --exit-code HEAD
mkdir "$STAGE/clip-source"
git -C "$STAGE/clip-git" archive HEAD | tar -x -C "$STAGE/clip-source"
printf '%s\n' "$CLIP_COMMIT" > "$STAGE/clip-commit.txt"
apptainer exec --cleanenv --bind /scratch \
    --env PYTHONNOUSERSITE=1 --env PYTHONDONTWRITEBYTECODE=1 \
    --env PYTHONPATH="$STAGE/python" --env OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK" \
    --env WANDB_MODE=disabled \
    "$SIF" python3 -u "$SCRIPT" install "$STAGE" "$SIF"
[[ ! -e "$ROOT/runtime" ]]
mv -T "$STAGE" "$ROOT/runtime"
printf '{"event":"runtime_published","job":"%s"}\n' "$SLURM_JOB_ID"
