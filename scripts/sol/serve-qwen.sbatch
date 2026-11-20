#!/bin/bash
#SBATCH --job-name=video-qwen-test
#SBATCH --partition=public
#SBATCH --qos=class
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=96G
#SBATCH --gres=gpu:a100:1
#SBATCH --constraint=a100_80
#SBATCH --time=00:20:00

set -euo pipefail
RUN_ROOT="/scratch/$USER/video-search-qwen"
SIF="$RUN_ROOT/vllm-0.20.0-cu129.sif"
test -s "$RUN_ROOT/prepared.json"
test -s "$RUN_ROOT/server.env"
mkdir -p "$RUN_ROOT/flashinfer" "$RUN_ROOT/vllm-cache"
export HF_HOME="$RUN_ROOT/hf"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export VLLM_CACHE_ROOT="$RUN_ROOT/vllm-cache"
export PYTORCH_ALLOC_CONF=expandable_segments:True
export OMP_NUM_THREADS=8
PORT=18360
printf '{"host":"%s","port":%s,"job_id":"%s"}\n' "$(hostname -f)" "$PORT" "$SLURM_JOB_ID" > "$RUN_ROOT/endpoint.json"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
nvidia-smi --query-gpu=timestamp,index,name,memory.used,memory.total,utilization.gpu \
    --format=csv --loop=1 > "$RUN_ROOT/gpu-$SLURM_JOB_ID.csv" &
METRICS_PID=$!
trap 'kill "$METRICS_PID"' EXIT
apptainer exec --cleanenv --nv --bind /scratch --env-file "$RUN_ROOT/server.env" \
    --env PYTHONNOUSERSITE=1 \
    --env HF_HOME="$HF_HOME" --env HF_HUB_OFFLINE=1 --env TRANSFORMERS_OFFLINE=1 \
    --env VLLM_CACHE_ROOT="$VLLM_CACHE_ROOT" --env FLASHINFER_WORKSPACE_BASE="$RUN_ROOT/flashinfer" \
    --env CUDA_VISIBLE_DEVICES="$CUDA_VISIBLE_DEVICES" \
    --env PYTORCH_ALLOC_CONF="$PYTORCH_ALLOC_CONF" --env OMP_NUM_THREADS=8 \
    "$SIF" vllm serve Qwen/Qwen3.6-27B \
    --revision 6a9e13bd6fc8f0983b9b99948120bc37f49c13e9 \
    --dtype bfloat16 --tensor-parallel-size 1 --max-model-len 8192 \
    --max-num-seqs 1 --gpu-memory-utilization 0.90 --enforce-eager \
    --reasoning-parser qwen3 --limit-mm-per-prompt '{"image":8,"video":0}' \
    --structured-outputs-config '{"backend":"xgrammar","disable_any_whitespace":true}' \
    --mm-processor-kwargs '{"min_pixels":65536,"max_pixels":262144}' \
    --host 0.0.0.0 --port "$PORT" --no-enable-log-requests
