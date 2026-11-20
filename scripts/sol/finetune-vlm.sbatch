#!/bin/bash
#SBATCH --job-name=video-vlm-lora
#SBATCH --partition=public
#SBATCH --qos=class
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=02:00:00

set -euo pipefail
umask 077
ROOT="${FINETUNE_ROOT:?Set FINETUNE_ROOT to the fine-tuning research directory}"
SIF="/scratch/$USER/video-search-qwen/vllm-0.20.0-cu129.sif"
MODE="${FINETUNE_MODE:-smoke}"
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export APPTAINERENV_CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
mkdir -p "$ROOT/logs" "$ROOT/runs"
exec > >(tee -a "$ROOT/logs/finetune-$MODE-$SLURM_JOB_ID.log") 2>&1
# Isolated research packages only; the application environment is untouched.
if [[ ! -d "$ROOT/python/trl" ]]; then
    apptainer exec --cleanenv --bind /scratch --env PYTHONNOUSERSITE=1 \
        --nv "$SIF" python3 -m pip install --no-cache-dir --target "$ROOT/python" \
        "peft==0.18.0" "trl==0.24.0" "accelerate==1.11.0" "datasets==4.2.0"
fi
ARGS=(--data "$ROOT/dataset" --out "$ROOT/runs/finetune-v1")
if [[ "$MODE" == "smoke" ]]; then
    ARGS+=(--smoke)
else
    ARGS+=(--epochs 2)
fi
apptainer exec --cleanenv --bind /scratch --nv \
    --env PYTHONNOUSERSITE=1 --env PYTHONPATH="$ROOT/python" \
    --env HF_HUB_DISABLE_TELEMETRY=1 \
    "$SIF" python3 "$ROOT/project/scripts/sol/finetune_vlm.py" "${ARGS[@]}"
printf '{"event":"job_done","mode":"%s","exit":0}\n' "$MODE"
