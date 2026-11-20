"""Paired summaries of frozen temporal-head tests; raw evidence stays private."""

import math
import random
import re
import statistics

from video_search.evaluation import temporal_iou
from video_search.temporal_training import score_predictions


SEEDS = (2018, 2019, 2020)
METRICS = ("R1@0.3", "R1@0.5", "R1@0.7", "mIoU")
IDENTITIES = ("metadata_sha256", "features_sha256", "training_driver_sha256", "driver_sha256")
BOOTSTRAP_SEED = 20261114


def _validate_rows(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("A complete nonempty query grid is required")
    keys = set()
    for row in rows:
        qid, vid = row["qid"], row["vid"]
        if (isinstance(qid, bool) or not isinstance(qid, (int, str)) or not str(qid)
                or str(qid) in keys or not isinstance(vid, str) or not vid):
            raise ValueError("Queries require unique IDs and source IDs")
        keys.add(str(qid))
        duration = row["duration"]
        if (isinstance(duration, bool) or not isinstance(duration, (int, float))
                or not math.isfinite(duration) or duration <= 0):
            raise ValueError("Source duration must be positive and finite")
        windows = row["relevant_windows"]
        if not isinstance(windows, list) or len(windows) != 1 or len(windows[0]) != 2:
            raise ValueError("This comparison requires one target interval per query")
        start, end = windows[0]
        if (any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
                for x in (start, end)) or not 0 <= start < end <= duration):
            raise ValueError("Target interval must be finite and within its source")


def _values(rows, predictions):
    values = []
    for row, prediction in zip(rows, predictions):
        first = prediction["pred_relevant_windows"][:1]
        iou = temporal_iou(tuple(first[0][:2]), tuple(row["relevant_windows"][0])) \
            if first and first[0][0] < first[0][1] else 0.
        values.append((float(iou >= .3), float(iou >= .5), float(iou >= .7), iou))
    return values


def _percent(metrics):
    return {key: 100 * metrics[key] for key in METRICS}


def _bootstrap(rows, vectors, repetitions):
    indices = {}
    for index, row in enumerate(rows):
        indices.setdefault(row["vid"], []).append(index)
    videos = sorted(indices)
    differences = {
        seed: {vid: tuple(sum(vectors[f"quality-{seed}"][i][metric]
                                  - vectors[f"baseline-{seed}"][i][metric] for i in positions)
                          for metric in range(4))
               for vid, positions in indices.items()}
        for seed in SEEDS}
    draws = [[] for _ in METRICS]
    rng = random.Random(BOOTSTRAP_SEED)
    for _ in range(repetitions):
        selected_seeds = rng.choices(SEEDS, k=len(SEEDS))
        selected_videos = rng.choices(videos, k=len(videos))
        count = len(SEEDS) * sum(len(indices[vid]) for vid in selected_videos)
        for metric, samples in enumerate(draws):
            samples.append(100 * sum(differences[seed][vid][metric]
                                     for seed in selected_seeds for vid in selected_videos) / count)
    intervals = {}
    for metric, samples in zip(METRICS, draws):
        quantiles = statistics.quantiles(samples, n=40, method="inclusive")
        intervals[metric] = [quantiles[0], quantiles[-1]]
    return intervals


def summarize(rows, reports, *, bootstrap_repetitions=2000):
    """Recompute every result, then resample paired seeds and shared source videos."""
    _validate_rows(rows)
    names = [f"{variant}-{seed}" for seed in SEEDS for variant in ("baseline", "quality")]
    if not isinstance(reports, dict) or set(reports) != set(names + ["author-reference"]):
        raise ValueError("Reports must contain the exact six-run and author-reference grid")
    if type(bootstrap_repetitions) is not int or bootstrap_repetitions < 2:
        raise ValueError("Bootstrap repetitions must be an integer of at least two")
    metrics, vectors, checkpoints = {}, {}, []
    first = reports[names[0]]
    if not isinstance(first, dict):
        raise ValueError("Every report must be a structured object")
    identity = {key: first.get(key) for key in IDENTITIES}
    for name in names + ["author-reference"]:
        report = reports[name]
        if not isinstance(report, dict) or not isinstance(report.get("predictions"), list):
            raise ValueError("Every report must contain its full prediction list")
        if type(report.get("evaluation_batch_size")) is not int or report["evaluation_batch_size"] != 32:
            raise ValueError("The controlled comparison requires batch size 32 for every report")
        for key in (*IDENTITIES, "checkpoint_sha256"):
            if not isinstance(report.get(key), str) or re.fullmatch(r"[0-9a-f]{64}", report[key]) is None:
                raise ValueError("Report artifact hashes must be SHA-256 identities")
        if any(report[key] != identity[key] for key in IDENTITIES):
            raise ValueError("Report data or evaluation source identities differ")
        if report.get("author_checkpoint") is not (name == "author-reference"):
            raise ValueError("Reference and controlled checkpoints are mislabeled")
        if name != "author-reference":
            checkpoints.append(report["checkpoint_sha256"])
        recomputed = score_predictions(rows, report["predictions"])
        saved = report["metrics"]
        if (not isinstance(saved, dict) or set(saved) != {"queries", *METRICS} or type(saved["queries"]) is not int
                or saved["queries"] != len(rows)):
            raise ValueError("Saved metrics do not describe the complete query grid")
        for key in METRICS:
            value = saved[key]
            if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                    or not math.isclose(value, recomputed[key], rel_tol=0, abs_tol=1e-10)):
                raise ValueError("Saved metrics differ from complete prediction scoring")
        metrics[name] = recomputed
        vectors[name] = _values(rows, report["predictions"])
    if len(set(checkpoints)) != len(names):
        raise ValueError("Controlled runs must have six distinct checkpoint identities")
    methods = {}
    for variant in ("baseline", "quality"):
        methods[variant] = {
            "per_seed_percent": {str(seed): _percent(metrics[f"{variant}-{seed}"]) for seed in SEEDS},
            "mean_percent": {key: 100 * statistics.mean(metrics[f"{variant}-{seed}"][key] for seed in SEEDS)
                             for key in METRICS},
            "sample_standard_deviation_percentage_points": {
                key: 100 * statistics.stdev(metrics[f"{variant}-{seed}"][key] for seed in SEEDS)
                for key in METRICS}}
    paired = {str(seed): {key: 100 * (metrics[f"quality-{seed}"][key] - metrics[f"baseline-{seed}"][key])
                         for key in METRICS} for seed in SEEDS}
    return {
        "version": "trained-temporal-comparison-v1", "units": "percent and percentage-point differences",
        "query_count": len(rows), "source_video_count": len({row["vid"] for row in rows}),
        "seed_pairs": len(SEEDS), "report_count": len(reports), "evaluation_batch_size": 32,
        "identities": identity,
        "methods": methods,
        "quality_minus_baseline": {
            "per_seed_percentage_points": paired,
            "mean_delta_percentage_points": {
                key: statistics.mean(paired[str(seed)][key] for seed in SEEDS) for key in METRICS},
            "ci95_percentage_points": _bootstrap(rows, vectors, bootstrap_repetitions),
            "bootstrap": {"repetitions": bootstrap_repetitions, "seed": BOOTSTRAP_SEED,
                          "method": "Paired seed pairs and source-video clusters, both sampled with replacement; the video draw is shared across sampled seed pairs.",
                          "warning": "Only three seed pairs; uncertainty estimates are limited."}},
        "author_reference": {"metrics_percent": _percent(metrics["author-reference"]),
                             "checkpoint_sha256": reports["author-reference"]["checkpoint_sha256"],
                             "comparison": "Separate pretrained reference; authors used their test-selection procedure. Not a same-training control."},
        "limits": ["Processed author Charades-STA release; not a canonical-label reproduction.",
                   "Seven test query strings and 562 shared test intervals differ from the canonical copy; maximum endpoint difference is 0.18534 seconds.",
                   "The old 69-query subset was exposed; this is not an untouched-test or SOTA claim.",
                   "Positive single-video interval retrieval only; no absent-query, corpus, repeated-event, count or long-video result.",
                   "All seeds are reported; no seed or model is selected using test performance."]}
