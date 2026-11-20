#!/bin/bash
#SBATCH --job-name=video-temporal-head
#SBATCH --partition=public
#SBATCH --qos=class
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --gres=gpu:a100:1
#SBATCH --time=08:00:00

set -euo pipefail
ROOT="${TEMPORAL_ROOT:?Set TEMPORAL_ROOT to the separate research directory}"
ACTION="${TEMPORAL_ACTION:-smoke}"
SIF="/scratch/$USER/video-search-qwen/vllm-0.20.0-cu129.sif"
RUNS="$ROOT/runs/strict-head-v3"
if [[ "$ACTION" != smoke && "$ACTION" != train ]]; then
    echo "TEMPORAL_ACTION must be smoke or train" >&2
    exit 2
fi
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
mkdir -p "$RUNS" "$ROOT/logs"

run_one() {
    local variant="$1" seed="$2" output="$3"
    apptainer exec --nv --cleanenv --bind /scratch \
        --env PYTHONNOUSERSITE=1 \
        --env PYTHONPATH="$ROOT/project/src:$ROOT/python" \
        --env SLURM_JOB_ID="$SLURM_JOB_ID" \
        --env SLURM_CPUS_PER_TASK="$SLURM_CPUS_PER_TASK" \
        --env CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:?Slurm must assign a GPU}" \
        --env OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK" \
        "$SIF" python3 -u "$ROOT/project/scripts/train_temporal.py" "$ACTION" \
        --upstream "$ROOT/upstream" --metadata "$ROOT/data/charades_train.jsonl" \
        --slowfast "$ROOT/data/vid_slowfast" --clip "$ROOT/data/vid_clip" \
        --text "$ROOT/data/txt_clip" --config "$ROOT/data/opt.json" \
        --output "$output" --variant "$variant" --seed "$seed" \
        --epochs 100 --batch-size 32 --learning-rate 0.0001 --steps 20
}

if [[ "$ACTION" == smoke ]]; then
    run_one baseline 2018 "$RUNS/smoke-baseline-$SLURM_JOB_ID"
    run_one quality 2018 "$RUNS/smoke-quality-$SLURM_JOB_ID"
else
    for seed in 2018 2019 2020; do
        for variant in baseline quality; do
            run_one "$variant" "$seed" "$RUNS/$variant-$seed"
        done
    done
fi
