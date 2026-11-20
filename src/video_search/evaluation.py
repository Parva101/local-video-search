"""Temporal retrieval diagnostics; not a replacement for a dataset's official evaluator."""

import math


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def _interval(start, end, duration=None):
    _number(start, "start_seconds")
    _number(end, "end_seconds")
    if not 0 <= start < end or (duration is not None and end > duration):
        raise ValueError("Interval must be ordered, nonnegative, and inside the video")


def temporal_iou(left, right):
    _interval(*left)
    _interval(*right)
    intersection = max(0, min(left[1], right[1]) - max(left[0], right[0]))
    return intersection / (left[1] - left[0] + right[1] - right[0] - intersection)


def _key(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
        raise ValueError("Query IDs must be nonempty strings or integers")
    return str(value)


def validate_manifest(manifest):
    for field in ("name", "split", "provenance"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            raise ValueError(f"Manifest requires {field}")
    videos = manifest.get("videos")
    if not isinstance(videos, dict) or not videos:
        raise ValueError("Manifest requires video durations")
    for video_id, video in videos.items():
        if not isinstance(video_id, str) or not video_id.strip():
            raise ValueError("Video IDs must be nonempty strings")
        if _number(video["duration_seconds"], "duration_seconds") <= 0:
            raise ValueError("Video duration must be positive")
        if "annotation_duration_seconds" in video and _number(video["annotation_duration_seconds"], "annotation_duration_seconds") <= 0:
            raise ValueError("Annotation duration must be positive")
    queries = manifest.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("Manifest requires queries")
    seen = set()
    for query in queries:
        key = _key(query["id"])
        if key in seen:
            raise ValueError("Duplicate query ID")
        seen.add(key)
        if not isinstance(query.get("query"), str) or not query["query"].strip():
            raise ValueError("Query must contain text")
        scope = query.get("scope_video_ids")
        if not isinstance(scope, list) or not scope or len(set(scope)) != len(scope) or any(v not in videos for v in scope):
            raise ValueError("Query requires a valid, nonempty video scope")
        targets = query.get("targets")
        if not isinstance(targets, list):
            raise ValueError("Query targets must be a list; use [] only for an annotated absent event")
        target_keys = set()
        for target in targets:
            _validate_candidate(target, videos, target=True)
            if target["video_id"] not in scope:
                raise ValueError("Target is outside the query scope")
            identity = (target["video_id"], target["start_seconds"], target["end_seconds"])
            if identity in target_keys:
                raise ValueError("Duplicate target interval")
            target_keys.add(identity)


def _validate_candidate(candidate, videos, *, target=False):
    if candidate.get("video_id") not in videos:
        raise ValueError("Unknown prediction or target video ID")
    video = videos[candidate["video_id"]]
    duration = video.get("annotation_duration_seconds", video["duration_seconds"]) if target else video["duration_seconds"]
    _interval(candidate["start_seconds"], candidate["end_seconds"], duration)
    if "score" in candidate:
        _number(candidate["score"], "score")


def _predictions(manifest, predictions):
    validate_manifest(manifest)
    if not isinstance(predictions, list):
        raise ValueError("Predictions must be a list")
    indexed = {}
    for item in predictions:
        key = _key(item["query_id"])
        if key in indexed:
            raise ValueError("Duplicate prediction query ID")
        if not isinstance(item.get("candidates"), list):
            raise ValueError("Each prediction requires a ranked candidates list")
        for candidate in item["candidates"]:
            _validate_candidate(candidate, manifest["videos"])
        for field in ("calls", "frames", "elapsed_seconds"):
            if field in item and (_number(item[field], field) < 0 or (field != "elapsed_seconds" and not isinstance(item[field], int))):
                raise ValueError(f"Invalid {field}")
        indexed[key] = item
    if set(indexed) != {_key(q["id"]) for q in manifest["queries"]}:
        raise ValueError("Prediction query IDs must match manifest exactly; missing or extra queries are errors")
    return indexed


def evaluate(manifest, predictions, ks=(1, 3, 5), thresholds=(.3, .5, .7)):
    """Score ranked list order; targets never enter retrieval. Rates are in [0, 1]."""
    indexed = _predictions(manifest, predictions)
    if not ks or any(isinstance(k, bool) or not isinstance(k, int) or k < 1 for k in ks) or len(set(ks)) != len(ks):
        raise ValueError("ks must contain distinct positive integers")
    if not thresholds or any(not 0 < _number(t, "threshold") <= 1 for t in thresholds) or len(set(thresholds)) != len(thresholds):
        raise ValueError("thresholds must be distinct and within (0, 1]")
    per_query, positives, negatives = [], [], []
    for query in manifest["queries"]:
        prediction = indexed[_key(query["id"])]
        targets, candidates = query["targets"], prediction["candidates"]
        row = {"query_id": query["id"], "target_count": len(targets), "candidate_count": len(candidates), "metrics": {}}
        if targets:
            row["top1_iou"] = max((temporal_iou((c["start_seconds"], c["end_seconds"]),
                                                (t["start_seconds"], t["end_seconds"]))
                                    for c in candidates[:1] for t in targets if c["video_id"] == t["video_id"]), default=0)
            for k in ks:
                best = [max((temporal_iou((c["start_seconds"], c["end_seconds"]),
                                         (t["start_seconds"], t["end_seconds"]))
                             for c in candidates[:k] if c["video_id"] == t["video_id"]), default=0)
                        for t in targets]
                for threshold in thresholds:
                    hits = sum(iou >= threshold for iou in best)
                    suffix = f"@{k}/IoU={threshold:g}"
                    row["metrics"]["R" + suffix] = int(hits > 0)
                    row["metrics"]["target_coverage" + suffix] = hits / len(targets)
                    row["metrics"]["all_targets" + suffix] = int(hits == len(targets))
            positives.append(row)
        else:
            row["abstained"] = not candidates
            negatives.append(row)
        per_query.append(row)
    metrics = {key: sum(q["metrics"][key] for q in positives) / len(positives)
               for key in positives[0]["metrics"]} if positives else {}
    cost = {field + "_total": sum(p[field] for p in predictions) if all(field in p for p in predictions) else None
            for field in ("calls", "frames", "elapsed_seconds")}
    return {"evaluator_version": "temporal-diagnostics-v1", "name": manifest["name"], "split": manifest["split"],
            "provenance": manifest["provenance"], "metrics": metrics,
            "counts": {"queries": len(per_query), "positive_queries": len(positives), "negative_queries": len(negatives)},
            "negative_abstention_rate": sum(q["abstained"] for q in negatives) / len(negatives) if negatives else None,
            "mean_top1_iou": sum(q["top1_iou"] for q in positives) / len(positives) if positives else None,
            "cost": cost, "per_query": per_query,
            "limits": "Diagnostic rates, not official mAP. Candidate order is preserved. No claim of complete event labels or benchmark superiority."}


def search_requests(manifest, recording_map, path="description", limit=10, task="supplied_video"):
    validate_manifest(manifest)
    if path not in {"visual", "description", "hybrid"} or task not in {"supplied_video", "corpus"}:
        raise ValueError("Unknown search path or task")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Search limit must be within 1..100")
    if (set(recording_map) != set(manifest["videos"]) or any(not isinstance(v, str) or not v.strip() for v in recording_map.values())
            or len(set(recording_map.values())) != len(recording_map)):
        raise ValueError("Recording mapping must match manifest videos exactly and use distinct nonempty recording IDs")
    return [(query["id"], {"query": query["query"], "path": path, "limit": limit,
                          "recording_ids": [recording_map[v] for v in (manifest["videos"] if task == "corpus" else query["scope_video_ids"])]})
            for query in manifest["queries"]]


def qvhighlights_rows(manifest, predictions):
    """Export moment predictions only; rank scores preserve the supplied order."""
    indexed = _predictions(manifest, predictions)
    rows = []
    for query in manifest["queries"]:
        scope = query["scope_video_ids"]
        candidates = indexed[_key(query["id"])]["candidates"]
        if len(scope) != 1 or any(c["video_id"] != scope[0] for c in candidates):
            raise ValueError("QVHighlights export requires one supplied video and no cross-video predictions")
        rows.append({"qid": query["id"], "vid": scope[0], "pred_relevant_windows":
                     [[c["start_seconds"], c["end_seconds"], 1 / rank] for rank, c in enumerate(candidates, 1)]})
    return rows
