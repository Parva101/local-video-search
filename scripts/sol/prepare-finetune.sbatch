#!/bin/bash
#SBATCH --job-name=video-finetune-base
#SBATCH --partition=public
#SBATCH --qos=class
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00

set -euo pipefail
umask 077
ROOT="${FINETUNE_ROOT:?Set FINETUNE_ROOT to the separate fine-tuning directory}"
SIF="/scratch/$USER/video-search-qwen/vllm-0.20.0-cu129.sif"
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
mkdir -p "$ROOT/logs" "$ROOT/data" "$ROOT/project"
exec > >(tee -a "$ROOT/logs/prepare-finetune-$SLURM_JOB_ID.log") 2>&1
# The pinned vLLM image ships huggingface_hub; nothing is installed.
apptainer exec --cleanenv --bind /scratch --env PYTHONNOUSERSITE=1 \
    --env HF_HUB_DISABLE_TELEMETRY=1 \
    "$SIF" python3 "$ROOT/project/scripts/sol/prepare_finetune.py" "$ROOT"
