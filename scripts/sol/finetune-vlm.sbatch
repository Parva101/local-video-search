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
# A venv with system site packages sees the container's torch and transformers
# and only adds peft/trl; constraints pin them so an incompatible peft/trl
# fails at install time instead of shadowing compiled container packages.
if [[ ! -x "$ROOT/venv/bin/python3" ]]; then
    apptainer exec --cleanenv --bind /scratch --nv "$SIF" \
        python3 -m venv --system-site-packages "$ROOT/venv"
    printf 'transformers==5.6.2\ntorch==2.11.0\n' > "$ROOT/training-constraints.txt"
    apptainer exec --cleanenv --bind /scratch --nv --env PYTHONNOUSERSITE=1 "$SIF" \
        "$ROOT/venv/bin/pip" install --no-cache-dir -c "$ROOT/training-constraints.txt" peft trl
fi
ARGS=(--data "$ROOT/dataset" --out "$ROOT/runs/finetune-v1")
if [[ "$MODE" == "probe" ]]; then
    ARGS+=(--batch-probe)
elif [[ "$MODE" == "smoke" ]]; then
    ARGS+=(--smoke)
elif [[ "$MODE" == "eval" ]]; then
    ARGS+=(--eval-only --adapter "$ROOT/runs/finetune-v1/adapter")
else
    ARGS+=(--epochs 2)
fi
apptainer exec --cleanenv --bind /scratch --nv \
    --env PYTHONNOUSERSITE=1 --env HF_HUB_DISABLE_TELEMETRY=1 \
    --env PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    "$SIF" "$ROOT/venv/bin/python3" "$ROOT/project/scripts/sol/finetune_vlm.py" "${ARGS[@]}"
printf '{"event":"job_done","mode":"%s","exit":0}\n' "$MODE"
