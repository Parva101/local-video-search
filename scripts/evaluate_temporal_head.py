"""Score a frozen UniVTG checkpoint on the complete private author test release."""

import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import torch
from video_search.temporal_training import (Features, GroundingDataset, collate, file_hash,
    model_config, predictions, read_metadata, score_predictions, upstream_model)
from video_search import evaluation as evaluator


AUTHOR_TEST_SHA256 = "fbf26493b5b1b7c08e3cb0b79e3ef400709229205cfea24745798292ba7eb7d6"
AUTHOR_CHECKPOINT_SHA256 = "b3033d72ae5de5f99d9544b85ab0a0378998b0e8bfeb9db633a3e00c54960bb1"


def validate_training_protocol(protocol, state, config_path):
    from video_search.temporal_training import digest
    if (state["protocol_sha256"] != digest(protocol)
            or protocol["raw_author_config_sha256"] != file_hash(config_path)
            or protocol["evaluator_sha256"] != file_hash(evaluator.__file__)
            or protocol["source_sha256"] != file_hash(Path(__file__).parents[1] / "src/video_search/temporal_training.py")):
        raise ValueError("Checkpoint, source config or evaluator differs from the frozen run")


def load_weights(checkpoint, author=False):
    if author:
        if file_hash(checkpoint) != AUTHOR_CHECKPOINT_SHA256:
            raise ValueError("Released checkpoint differs from the verified download")
        # The author checkpoint stores its options as a Namespace; allow only that type.
        with torch.serialization.safe_globals([argparse.Namespace]):
            state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    else:
        state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if not isinstance(state, dict) or "model" not in state:
        raise ValueError("Checkpoint has no model state")
    return state


def evaluate(args):
    if type(args.batch_size) is not int or not 1 <= args.batch_size <= 128:
        raise ValueError("Evaluation batch size must be within 1..128")
    started = time.perf_counter()
    if not os.environ.get("SLURM_JOB_ID") or not torch.cuda.is_available():
        raise RuntimeError("Full inference requires an allocated Sol CUDA job")
    if file_hash(args.metadata) != AUTHOR_TEST_SHA256:
        raise ValueError("Evaluation requires the pinned complete author test release")
    if args.output.exists():
        raise FileExistsError(args.output)
    config = model_config(args.config)
    rows = read_metadata(args.metadata)
    if len(rows) != 3720 or len({row["vid"] for row in rows}) != 1334:
        raise ValueError("Official test query grid differs")
    state = load_weights(args.checkpoint, args.author_checkpoint)
    if not args.author_checkpoint:
        protocol = json.loads((args.checkpoint.parent / "protocol.json").read_bytes())
        validate_training_protocol(protocol, state, args.config)
        # The saved effective config includes deliberate from-scratch training overrides.
        config = protocol["config"]
        if {row["vid"] for row in rows} & (set(protocol["training_video_ids"]) | set(protocol["development_video_ids"])):
            raise ValueError("Training or development videos overlap test")
    features = Features(rows, args.slowfast, args.clip, args.text, use_tef=config["v_feat_dim"] == 2818)
    model, _ = upstream_model(args.upstream, config)
    model.load_state_dict(state["model"], strict=True)
    model.cuda().eval()
    loader = torch.utils.data.DataLoader(GroundingDataset(rows, features), batch_size=args.batch_size, collate_fn=collate)
    results = []
    inference_started = time.perf_counter()
    with torch.inference_mode():
        for meta, inputs, targets in loader:
            inputs = {key: value.cuda() for key, value in inputs.items()}
            targets = {key: value.cuda() for key, value in targets.items()}
            results.extend(predictions(model(**inputs), targets, meta))
    inference_seconds = time.perf_counter() - inference_started
    metrics = score_predictions(rows, results)
    report = {"metrics": metrics, "checkpoint_sha256": file_hash(args.checkpoint),
              "metadata_sha256": AUTHOR_TEST_SHA256, "features_sha256": features.sha256,
              "driver_sha256": file_hash(__file__), "training_driver_sha256": file_hash(Path(__file__).parents[1] / "src/video_search/temporal_training.py"),
              "author_checkpoint": args.author_checkpoint,
              "evaluation_batch_size": args.batch_size, "inference_seconds": inference_seconds,
              "elapsed_seconds": time.perf_counter() - started,
              "protocol": "Full author Charades-STA release; stable foreground ranking, duration scaling/clamp and 4dp; R1 only, no R5 NMS.",
              "limits": "Processed author labels differ from canonical labels. Released author checkpoint used authors' test selection. Padding makes batch size material; author config uses4. Timing uses precomputed features and excludes raw extraction/query encoding. No novelty claim.",
              "predictions": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, sort_keys=True, allow_nan=False)
    print(json.dumps({key: value for key, value in report.items() if key != "predictions"}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("upstream", "metadata", "slowfast", "clip", "text", "config", "checkpoint", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--author-checkpoint", action="store_true")
    parser.add_argument("--batch-size", type=int, default=32)
    evaluate(parser.parse_args())
