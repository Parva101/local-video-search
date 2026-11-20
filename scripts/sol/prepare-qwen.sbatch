#!/bin/bash
#SBATCH --job-name=video-qwen-prepare
#SBATCH --partition=public
#SBATCH --qos=class
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=01:00:00

set -euo pipefail
RUN_ROOT="/scratch/$USER/video-search-qwen"
SIF="$RUN_ROOT/vllm-0.20.0-cu129.sif"
mkdir -p "$RUN_ROOT/hf"
export APPTAINER_CACHEDIR="$RUN_ROOT/apptainer-cache"
if [ ! -f "$SIF" ]; then
    LOCAL_ROOT=$(mktemp -d "/tmp/video-search-qwen-$SLURM_JOB_ID-XXXXXX")
    export APPTAINER_TMPDIR="$LOCAL_ROOT"
    apptainer build --mksquashfs-args "-processors $SLURM_CPUS_PER_TASK -mem 8G" \
        "$LOCAL_ROOT/runtime.sif" docker://vllm/vllm-openai@sha256:51fdfe717fa0505c177dddc46bd38c22fc1f2156ba14d1b1cd63f78eaa60fd32
    mv "$LOCAL_ROOT/runtime.sif" "$SIF"
    rmdir "$LOCAL_ROOT"
fi
apptainer exec --cleanenv --bind /scratch --env HF_HOME="$RUN_ROOT/hf" \
    --env PYTHONNOUSERSITE=1 --env SLURM_JOB_ID="$SLURM_JOB_ID" "$SIF" \
    python3 "$RUN_ROOT/scripts/prepare_qwen.py" "$RUN_ROOT" "$SIF"
