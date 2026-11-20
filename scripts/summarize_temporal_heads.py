"""Publish aggregate scores from the complete frozen temporal-head comparison."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from video_search.temporal_training import file_hash, read_metadata, score_predictions
from video_search.trained_results import IDENTITIES, METRICS, SEEDS, summarize


TEST_SHA256 = "fbf26493b5b1b7c08e3cb0b79e3ef400709229205cfea24745798292ba7eb7d6"


def native_reference(rows, report, matched):
    if (report.get("author_checkpoint") is not True or report.get("evaluation_batch_size") != 4
            or any(report.get(key) != matched[key] for key in (*IDENTITIES, "checkpoint_sha256"))):
        raise ValueError("Native reference must differ only in its declared batch size")
    metrics = score_predictions(rows, report["predictions"])
    if report["metrics"] != metrics:
        raise ValueError("Native reference saved metrics differ from recomputation")
    return {"evaluation_batch_size": 4, "metrics_percent": {key: 100 * metrics[key] for key in METRICS},
            "checkpoint_sha256": report["checkpoint_sha256"],
            "scope": "Separate check using author-config batch size; not part of the matched batch32 comparison."}


def publish(args):
    if file_hash(args.metadata) != TEST_SHA256:
        raise ValueError("Summary requires the pinned complete author test metadata")
    rows = read_metadata(args.metadata)
    if len(rows) != 3720 or len({row["vid"] for row in rows}) != 1334:
        raise ValueError("Full test query grid differs")
    freeze_raw = args.freeze.read_bytes()
    freeze = json.loads(freeze_raw)
    names = [f"{variant}-{seed}" for seed in SEEDS for variant in ("baseline", "quality")]
    if set(freeze["cases"]) != set(names + ["author-reference", "author-native-b4"]):
        raise ValueError("Frozen comparison grid differs")
    reports = {name: json.loads((args.reports / f"{name}.json").read_bytes())
               for name in names + ["author-reference"]}
    audit = json.loads((args.reports / "checkpoint-audit.json").read_bytes())
    for name in names:
        if (reports[name]["checkpoint_sha256"] != audit[name]["checkpoint_sha256"]
                or audit[name]["selected_epoch"] != freeze["selected_epochs"][name]):
            raise ValueError("Evaluated checkpoint differs from frozen validation selection")
    for report in reports.values():
        if (report["metadata_sha256"] != TEST_SHA256
                or report["driver_sha256"] != freeze["source_sha256"]["scripts/evaluate_temporal_head.py"]
                or report["training_driver_sha256"] != freeze["source_sha256"]["src/video_search/temporal_training.py"]):
            raise ValueError("Evaluated source differs from pre-test freeze")
    result = summarize(rows, reports)
    native = json.loads((args.reports / "author-native-b4.json").read_bytes())
    result["author_native_batch4"] = native_reference(rows, native, reports["author-reference"])
    result["freeze_sha256"] = hashlib.sha256(freeze_raw).hexdigest()
    result["selected_epochs"] = freeze["selected_epochs"]
    result["training_job"] = {"id": 1488158, "state": "COMPLETED", "exit_code": "0:0",
                              "elapsed_seconds": 16504, "gpu_count": 1, "epochs_per_run": 100}
    result["timing"] = {name: {key: report[key] for key in ("inference_seconds", "elapsed_seconds")}
                        for name, report in {**reports, "author-native-b4": native}.items()}
    result["timing_scope"] = "Per-case timers use released precomputed features; raw extraction and query encoding are excluded. Python/container startup precedes these timers."
    result["report_sha256"] = {name: file_hash(args.reports / f"{name}.json")
                               for name in names + ["author-reference", "author-native-b4"]}
    result["summary_source_sha256"] = file_hash(__file__)
    result["aggregation_source_sha256"] = file_hash(Path(__file__).parents[1] / "src/video_search/trained_results.py")
    raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as output:
        output.write(raw)
    print(json.dumps({key: result[key] for key in ("query_count", "methods", "quality_minus_baseline",
                                                  "author_reference", "author_native_batch4")}, allow_nan=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("metadata", "reports", "freeze", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    publish(parser.parse_args())
