#!/bin/bash
#SBATCH --job-name=video-temporal-test
#SBATCH --partition=public
#SBATCH --qos=class
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --gres=gpu:a100:1
#SBATCH --time=01:00:00

set -euo pipefail
ROOT="${TEMPORAL_ROOT:?Set TEMPORAL_ROOT to the separate research directory}"
SIF="/scratch/$USER/video-search-qwen/vllm-0.20.0-cu129.sif"
RUNS="$ROOT/runs/strict-head-v3"
OUTPUT="$ROOT/evaluation/strict-head-v3-batch-control-v1"
mkdir -p "$OUTPUT"

evaluate_one() {
    local name="$1" checkpoint="$2" batch="$3"
    shift 3
    apptainer exec --nv --cleanenv --bind /scratch \
        --env PYTHONNOUSERSITE=1 --env PYTHONPATH="$ROOT/project/src:$ROOT/python" \
        --env SLURM_JOB_ID="$SLURM_JOB_ID" --env SLURM_CPUS_PER_TASK="$SLURM_CPUS_PER_TASK" \
        --env CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:?Slurm must assign a GPU}" \
        --env OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK" \
        "$SIF" python3 -u "$ROOT/project/scripts/evaluate_temporal_head.py" \
        --upstream "$ROOT/upstream" --metadata "$ROOT/data/charades_test.jsonl" \
        --slowfast "$ROOT/data/vid_slowfast" --clip "$ROOT/data/vid_clip" \
        --text "$ROOT/data/txt_clip" --config "$ROOT/data/opt.json" \
        --checkpoint "$checkpoint" --output "$OUTPUT/$name.json" --batch-size "$batch" "$@"
}

for seed in 2018 2019 2020; do
    for variant in baseline quality; do
        evaluate_one "$variant-$seed" "$RUNS/$variant-$seed/best.pt" 32
    done
done
evaluate_one author-reference "$ROOT/data/model_best.ckpt" 32 --author-checkpoint
evaluate_one author-native-b4 "$ROOT/data/model_best.ckpt" 4 --author-checkpoint
