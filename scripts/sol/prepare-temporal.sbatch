#!/bin/bash
#SBATCH --job-name=video-temporal-data
#SBATCH --partition=public
#SBATCH --qos=class
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00

set -euo pipefail
ROOT="${TEMPORAL_ROOT:?Set TEMPORAL_ROOT to the separate research directory}"
SIF="/scratch/$USER/video-search-qwen/vllm-0.20.0-cu129.sif"
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
mkdir -p "$ROOT/python" "$ROOT/logs"
apptainer exec --cleanenv --bind /scratch --env PYTHONNOUSERSITE=1 "$SIF" \
    python3 -m pip install --no-deps --target "$ROOT/python" \
    gdown==5.2.0 scipy==1.15.3 beautifulsoup4==4.13.4 soupsieve==2.7
apptainer exec --cleanenv --bind /scratch \
    --env PYTHONNOUSERSITE=1 --env PYTHONPATH="$ROOT/python" \
    "$SIF" python3 "$ROOT/project/scripts/sol/prepare_temporal.py" "$ROOT"
