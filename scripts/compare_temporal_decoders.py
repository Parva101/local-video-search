"""Compare offline caption decoders without model calls or production DB writes."""

import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from video_search.evaluation import evaluate, temporal_iou, validate_manifest
from video_search.temporal_decode import decode


GRID = [{"sigma_seconds": sigma, "background_weight": weight}
        for sigma in (0, .5, 1, 2, 3) for weight in (0, .5)]
VERSION = "caption-curve-experiment-v1"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write((json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())


def source_hashes():
    return {name: digest(path.read_bytes()) for name, path in {
        "runner": Path(__file__),
        "decoder": Path(__file__).parents[1] / "src/video_search/temporal_decode.py",
        "evaluator": Path(__file__).parents[1] / "src/video_search/evaluation.py",
    }.items()}


def load_inputs(manifest_path, cache):
    raw = Path(manifest_path).read_bytes()
    manifest = json.loads(raw)
    validate_manifest(manifest)
    inputs, hashes = {}, {}
    for query in manifest["queries"]:
        if len(query["scope_video_ids"]) != 1:
            raise ValueError("This experiment requires a supplied video")
        video = query["scope_video_ids"][0]
        filename = digest(json.dumps(query["id"], sort_keys=True, allow_nan=False).encode()) + ".json"
        content = (Path(cache) / filename).read_bytes()
        item = json.loads(content)
        if item["request"]["query"] != query["query"] or len(item["request"]["recording_ids"]) != 1:
            raise ValueError("Cache request differs from the manifest query")
        recording = item["request"]["recording_ids"][0]
        for method in ("raw", "reranked"):
            if any(c["source_path"] != video + ".mp4" or c["recording_id"] != recording
                   or c["source_status"] != "available" for c in item[method]["results"]):
                raise ValueError("Cache source is outside the supplied video")
        keys = lambda name: {(c["start_seconds"], c["end_seconds"]) for c in item[name]["results"]}
        if keys("raw") != keys("reranked"):
            raise ValueError("Cached methods have different candidate pools")
        # Full-coverage validation occurs even when we score only the fixed baseline.
        decode(item["reranked"]["results"], manifest["videos"][video]["duration_seconds"])
        inputs[str(query["id"])] = item
        hashes[filename] = digest(content)
    return manifest, inputs, {"manifest_sha256": digest(raw), "cache_sha256": hashes}


def predictions(manifest, inputs, method, configuration=None):
    rows = []
    for query in manifest["queries"]:
        video = query["scope_video_ids"][0]
        item = inputs[str(query["id"])]
        if method in {"raw", "reranked"}:
            spans = item[method]["results"]
        elif method == "curve":
            spans = decode(item["reranked"]["results"], manifest["videos"][video]["duration_seconds"], **configuration)
        else:
            raise ValueError("Unknown experiment method")
        rows.append({"query_id": query["id"], "candidates": [
            {"video_id": video, "start_seconds": c["start_seconds"], "end_seconds": c["end_seconds"]}
            for c in spans]})
    return rows


def metrics(report):
    return {"R1_IoU_0.3": report["metrics"]["R@1/IoU=0.3"],
            "R1_IoU_0.5": report["metrics"]["R@1/IoU=0.5"],
            "R1_IoU_0.7": report["metrics"]["R@1/IoU=0.7"],
            "mean_IoU": report["mean_top1_iou"]}


def develop(manifest_path, cache, output):
    manifest, inputs, identity = load_inputs(manifest_path, cache)
    if manifest["split"] not in {"train", "development"}:
        raise ValueError("Select configurations only on the training development split")
    grid = []
    for configuration in GRID:
        result = evaluate(manifest, predictions(manifest, inputs, "curve", configuration))
        grid.append({"configuration": configuration, "metrics": metrics(result)})
    chosen = max(grid, key=lambda row: (row["metrics"]["R1_IoU_0.5"], row["metrics"]["mean_IoU"],
                                        row["metrics"]["R1_IoU_0.7"]))
    baseline = {method: metrics(evaluate(manifest, predictions(manifest, inputs, method)))
                for method in ("raw", "reranked")}
    freeze = {"version": VERSION, "sources": source_hashes(), "development": identity,
              "configuration": chosen["configuration"], "grid": grid, "baseline": baseline,
              "development_videos": sorted(manifest["videos"]), "query_count": len(manifest["queries"]),
              "selection": "Train-only R1@.5, then mean IoU, then R1@.7; first grid entry wins exact ties.",
              "limits": "Caption-score interpolation, not dense visual observation. Test subset was previously exposed. No novelty claim."}
    save_new(output, freeze)
    return {"chosen": chosen, "baseline": baseline, "query_count": len(manifest["queries"])}


def paired_interval(manifest, left, right, repetitions=2000):
    groups = {}
    left_rows = {str(row["query_id"]): row for row in left["per_query"]}
    right_rows = {str(row["query_id"]): row for row in right["per_query"]}
    for query in manifest["queries"]:
        key = str(query["id"])
        lrow, rrow = left_rows[key], right_rows[key]
        groups.setdefault(query["scope_video_ids"][0], []).append((
            lrow["metrics"]["R@1/IoU=0.5"] - rrow["metrics"]["R@1/IoU=0.5"],
            lrow["top1_iou"] - rrow["top1_iou"]))
    rng, values = random.Random(20261114), list(groups.values())
    samples = [[], []]
    for _ in range(repetitions):
        rows = [row for group in rng.choices(values, k=len(values)) for row in group]
        for index in range(2):
            samples[index].append(sum(row[index] for row in rows) / len(rows))
    return {name: [sorted(sample)[int(.025 * (repetitions - 1))],
                   sorted(sample)[int(.975 * (repetitions - 1))]]
            for name, sample in zip(("R1_IoU_0.5_delta_95_percent", "mean_IoU_delta_95_percent"), samples)}


def run_evaluation(manifest_path, cache, freeze_path, output):
    freeze_raw = Path(freeze_path).read_bytes()
    freeze = json.loads(freeze_raw)
    if freeze["version"] != VERSION or freeze["sources"] != source_hashes():
        raise ValueError("Frozen experiment code changed; use a new development run")
    manifest, inputs, identity = load_inputs(manifest_path, cache)
    if manifest["split"] not in {"test", "held-out-pilot"} or set(freeze["development_videos"]) & set(manifest["videos"]):
        raise ValueError("Evaluation must be source-disjoint from development")
    names = {"raw": None, "reranked": None, "curve_selected": freeze["configuration"],
             "curve_unsmoothed": GRID[0], "curve_smoothed": {"sigma_seconds": 1, "background_weight": 0},
             "curve_contrast": {"sigma_seconds": 1, "background_weight": .5}}
    reports = {}
    for name, configuration in names.items():
        rows = predictions(manifest, inputs, "curve" if configuration is not None else name, configuration)
        reports[name] = evaluate(manifest, rows)
    oracle = []
    for query in manifest["queries"]:
        video = query["scope_video_ids"][0]
        candidates = inputs[str(query["id"])]["raw"]["results"]
        oracle.append(max((temporal_iou((c["start_seconds"], c["end_seconds"]),
                                       (t["start_seconds"], t["end_seconds"]))
                           for c in candidates for t in query["targets"] if t["video_id"] == video), default=0))
    public = {"version": VERSION, "evaluation_status": "exploratory-previously-exposed-69-query-subset",
              "freeze_sha256": digest(freeze_raw), "sources": source_hashes(),
              "manifest_sha256": identity["manifest_sha256"], "query_count": len(manifest["queries"]),
              "video_count": len(manifest["videos"]), "selected_configuration": freeze["configuration"],
              "metrics_are_fractions": True, "methods": {name: metrics(value) for name, value in reports.items()},
              "candidate_oracle_R1_IoU_0.5": sum(x >= .5 for x in oracle) / len(oracle),
              "candidate_oracle_mean_IoU": sum(oracle) / len(oracle),
              "selected_minus_reranked": paired_interval(manifest, reports["curve_selected"], reports["reranked"]),
              "new_model_calls": 0, "bootstrap_unit": "source-video; 2000 resamples; seed 20261114",
              "limits": ["Caption estimates, not per-frame evidence; same old cached inputs.",
                         "Previously exposed pilot; no independent test, novelty or SOTA claim.",
                         "Single-interval decoder can merge repeated events; relative scores cannot prove absence.",
                         "No source inspection calls; original caption/index costs belong to the previous pilot."]}
    save_new(Path(output) / "private-results.json", {"reports": reports, "input_hashes": identity, "public": public})
    save_new(Path(output) / "aggregate.json", public)
    return public


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("develop", "evaluate"))
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--freeze", type=Path)
    args = parser.parse_args()
    if args.action == "develop":
        result = develop(args.manifest, args.cache, args.output)
    else:
        if args.freeze is None:
            parser.error("evaluate requires --freeze")
        result = run_evaluation(args.manifest, args.cache, args.freeze, args.output)
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
