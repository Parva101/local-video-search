"""Paired, source-group diagnostics for the private Charades-STA pilot."""

import math
import random

from video_search.evaluation import evaluate, temporal_iou, validate_manifest


CONDITIONS = ("ranked_fixed", "uniform_extent", "extent")
BOOTSTRAP_REPETITIONS = 2000
BOOTSTRAP_SEED = 20261108


def _number(value, name, *, integer=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            or value < 0 or (integer and not isinstance(value, int))):
        raise ValueError(f"{name} must be a finite nonnegative {'integer' if integer else 'number'}")
    return value


def _interval(start, end, duration=None, *, allow_point=False):
    _number(start, "start_seconds")
    _number(end, "end_seconds")
    if (start > end if allow_point else start >= end) or (duration is not None and end > duration):
        raise ValueError("Prediction interval must be ordered and inside actual media")


def _proposal(proposal, duration=None):
    if not isinstance(proposal, dict):
        raise ValueError("Proposal must be a structured object")
    support = proposal.get("query_support")
    if support not in {"all", "partial", "unknown"} or type(proposal.get("complete")) is not bool:
        raise ValueError("Proposal support and completeness must be explicit")
    start, end = proposal.get("start_seconds"), proposal.get("end_seconds")
    if start is None or end is None:
        if start is not None or end is not None or proposal["complete"]:
            raise ValueError("Unresolved proposal bounds must both be null and cannot be complete")
    else:
        _interval(start, end, duration)
    for edge in ("onset", "offset"):
        bracket = proposal.get(edge)
        if not isinstance(bracket, dict) or bracket.get("state") not in {"observed", "open", "unknown"}:
            raise ValueError("Proposal must retain explicit boundary states")
        lower, upper = bracket.get("lower_seconds"), bracket.get("upper_seconds")
        for value in (lower, upper):
            if value is not None and (_number(value, "bracket bound") > (duration if duration is not None else math.inf)):
                raise ValueError("Boundary bracket is outside actual media")
        if lower is not None and upper is not None and lower > upper:
            raise ValueError("Boundary bracket is reversed")
        if bracket["state"] == "observed" and (lower is None or upper is None):
            raise ValueError("Observed boundary needs both bracket bounds")
    if proposal["complete"] and (support != "all" or any(proposal[edge]["state"] != "observed" for edge in ("onset", "offset"))):
        raise ValueError("A complete proposal requires full query support and both observed edges")
    return support == "all" and start is not None


def case_predictions(case):
    """Keep model order; an unresolved point or partial query never gains a duration."""
    condition, result, video = case["condition"], case["result"], case["video_id"]
    if condition not in CONDITIONS:
        raise ValueError("Unknown benchmark condition")
    candidates = []
    if condition == "ranked_fixed":
        for step in result["checks"]:
            output = step["verification"]["result"]
            intervals = output["intervals"]
            if not isinstance(intervals, list) or output.get("status") not in {"match", "no_match", "insufficient_evidence"}:
                raise ValueError("Source check has an invalid status or interval list")
            if (output["status"] == "match") != bool(intervals):
                raise ValueError("Source check status and intervals conflict")
            for interval in intervals:
                _interval(interval["start_seconds"], interval["end_seconds"], allow_point=True)
                if interval["start_seconds"] == interval["end_seconds"]:
                    continue
                candidates.append({"video_id": video, "start_seconds": interval["start_seconds"],
                                   "end_seconds": interval["end_seconds"]})
    else:
        if not isinstance(result.get("proposals"), list):
            raise ValueError("Extent condition requires its proposal list")
        for proposal in result["proposals"]:
            if _proposal(proposal):
                candidates.append({"video_id": video, "start_seconds": proposal["start_seconds"],
                                   "end_seconds": proposal["end_seconds"]})
    return candidates


def _validate_case(case, query, videos, max_checks):
    if "error" in case or case.get("failed"):
        raise ValueError("Failed cases must be resolved or reported as an incomplete run, never dropped")
    if case.get("video_id") != query["scope_video_ids"][0]:
        raise ValueError("Case source is outside the frozen query scope")
    recording = case.get("recording_id")
    if not isinstance(recording, str) or not recording:
        raise ValueError("Case requires the expected local recording_id")
    _number(case["elapsed_seconds"], "elapsed_seconds")
    result = case.get("result")
    if not isinstance(result, dict) or "error" in result or result.get("status") not in {"match", "no_match", "insufficient_evidence"}:
        raise ValueError("Case has no successful structured result")
    checks, budget = result.get("checks"), result.get("budget")
    if not isinstance(checks, list) or not isinstance(budget, dict):
        raise ValueError("Case requires checks and actual work accounting")
    for field in ("calls", "frames", "http_attempts", "sent_frame_slots"):
        _number(budget[field], field, integer=True)
    if (budget["calls"] != len(checks) or budget["http_attempts"] < budget["calls"]
            or budget["sent_frame_slots"] < budget["frames"]):
        raise ValueError("Case work accounting is inconsistent")
    recorded_checks = _number(budget.get("max_checks"), "max_checks", integer=True)
    recorded_frames = _number(budget.get("max_frames"), "max_frames", integer=True)
    if (budget["calls"] > max_checks or budget["frames"] > 8 * max_checks or recorded_checks != max_checks
            or recorded_frames != 8 * max_checks):
        raise ValueError("Case caps differ from the configured report; use a separate report for other budgets")
    if "http_attempts" in case and (_number(case["http_attempts"], "case http_attempts", integer=True) != budget["http_attempts"]):
        raise ValueError("Gateway and source-check attempt counts differ")
    if "max_checks" in budget and _number(budget["max_checks"], "max_checks", integer=True) < budget["calls"]:
        raise ValueError("Check cap was exceeded")
    if "max_frames" in budget and _number(budget["max_frames"], "max_frames", integer=True) < budget["frames"]:
        raise ValueError("Frame cap was exceeded")
    duration, slots, attempts, sent_slots = videos[case["video_id"]]["duration_seconds"], 0, 0, 0
    for step in checks:
        candidate, verification = step["candidate"], step["verification"]
        if candidate.get("source_status") != "available" or candidate.get("recording_id") != recording or verification.get("recording_id") != recording:
            raise ValueError("Check source is unavailable or belongs to another recording")
        samples = verification.get("samples")
        if not isinstance(samples, list) or len(samples) != 8 or verification.get("checked_by_model") is not True:
            raise ValueError("Each frozen model check must retain eight input slots")
        for sample in samples:
            if _number(sample["source_seconds"], "source_seconds") >= duration:
                raise ValueError("Sample is outside actual media")
        slots += len(samples)
        trace = verification["result"].get("_trace", {})
        hashes = trace.get("frame_sha256")
        if (not isinstance(hashes, list) or len(hashes) != len(samples)
                or any(not isinstance(h, str) or len(h) != 64 or set(h) - set("0123456789abcdef") for h in hashes)):
            raise ValueError("Input frame hashes are missing or malformed")
        used = _number(trace.get("http_attempts"), "trace http_attempts", integer=True)
        if used < 1:
            raise ValueError("A completed check needs at least one request attempt")
        attempts += used
        sent_slots += len(samples) * used
        for interval in verification["result"].get("intervals", []):
            _interval(interval["start_seconds"], interval["end_seconds"], duration,
                      allow_point=case["condition"] == "ranked_fixed")
    if budget["frames"] != slots or budget["http_attempts"] != attempts or budget["sent_frame_slots"] != sent_slots:
        raise ValueError("Work totals do not match saved model traces")
    if "unique_frames" in budget and _number(budget["unique_frames"], "unique_frames", integer=True) > slots:
        raise ValueError("Unique frames exceed input slots")
    for proposal in result.get("proposals", []):
        if proposal.get("recording_id") != recording:
            raise ValueError("Proposal belongs to another recording")
        _proposal(proposal, duration)


def _percentile(values, fraction):
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _cost(cases, max_checks):
    budgets = [case["result"]["budget"] for case in cases]
    return {"logical_calls": sum(b["calls"] for b in budgets), "input_frame_slots": sum(b["frames"] for b in budgets),
            "http_attempts": sum(b["http_attempts"] for b in budgets),
            "sent_frame_slots": sum(b["sent_frame_slots"] for b in budgets),
            "unique_frames_sum_per_case": sum(b["unique_frames"] for b in budgets) if all("unique_frames" in b for b in budgets) else None,
            "latency_p50_seconds": _percentile([case["elapsed_seconds"] for case in cases], .5),
            "latency_p95_seconds": _percentile([case["elapsed_seconds"] for case in cases], .95),
            "latency_scope": "source-check/controller stage; excludes retrieval and indexing",
            "actual_full_budget_queries": sum(b["calls"] == max_checks and b["frames"] == 8 * max_checks for b in budgets),
            "actual_three_check_queries": sum(b["calls"] == 3 and b["frames"] == 24 for b in budgets),
            "note": "Actual source-check/controller work, excluding retrieval and the shared index. Repeated reference inputs and retries consume slots; provider retry compute is unknown."}


def _boundary_diagnostics(queries, cases):
    closed = {edge: [] for edge in ("onset", "offset")}
    midpoint_errors = {edge: [] for edge in closed}
    complete_failures, complete_claims = 0, 0
    for query, case in zip(queries, cases):
        eligible = [p for p in case["result"].get("proposals", []) if _proposal(p)]
        if not eligible:
            continue
        proposal, target = eligible[0], query["targets"][0]
        overlap = temporal_iou((proposal["start_seconds"], proposal["end_seconds"]), (target["start_seconds"], target["end_seconds"]))
        if proposal["complete"]:
            complete_claims += 1
            complete_failures += overlap < .5
        for edge, field in (("onset", "start_seconds"), ("offset", "end_seconds")):
            bracket = proposal[edge]
            if bracket["state"] == "observed":
                lower, upper = bracket["lower_seconds"], bracket["upper_seconds"]
                closed[edge].append(int(lower <= target[field] <= upper))
                midpoint_errors[edge].append(abs((lower + upper) / 2 - target[field]))
    result = {"top1_complete_claims": complete_claims,
              "complete_claim_localization_failure_rate": complete_failures / complete_claims if complete_claims else None,
              "note": "This is a top-one localization proxy at IoU0.5, not semantic false-completeness ground truth or a count of every event."}
    for edge in closed:
        result[edge + "_observed_queries"] = len(closed[edge])
        result[edge + "_coverage_given_observed"] = sum(closed[edge]) / len(closed[edge]) if closed[edge] else None
        result[edge + "_coverage_all_queries"] = sum(closed[edge]) / len(queries)
        result[edge + "_midpoint_mae_seconds"] = sum(midpoint_errors[edge]) / len(midpoint_errors[edge]) if midpoint_errors[edge] else None
    return result


def _strata(manifest, rows):
    groups = {"event_duration": {}, "reference_edge": {}}
    for query, row in zip(manifest["queries"], rows):
        target, video = query["targets"][0], query["scope_video_ids"][0]
        duration = target["end_seconds"] - target["start_seconds"]
        length_bin = "up_to_5_seconds" if duration <= 5 else "over_5_to_10_seconds" if duration <= 10 else "over_10_seconds"
        reference = manifest["videos"][video]
        reference_end = reference.get("annotation_duration_seconds", reference["duration_seconds"])
        touches_edge = abs(target["start_seconds"]) <= 1e-6 or abs(target["end_seconds"] - reference_end) <= 1e-6
        for axis, label in (("event_duration", length_bin), ("reference_edge", "touches_reference_edge" if touches_edge else "interior")):
            groups[axis].setdefault(label, []).append((video, row))
    return {axis: {label: {"query_count": len(items), "video_count": len({video for video, _ in items}),
                          "primary_percent": {"mIoU": 100 * sum(row["top1_iou"] for _, row in items) / len(items),
                                              **{f"R1@IoU={t}": 100 * sum(row["metrics"][f"R@1/IoU={t}"] for _, row in items) / len(items)
                                                 for t in ("0.5", "0.7")}}}
                   for label, items in buckets.items()} for axis, buckets in groups.items()}


def _paired(queries, left, right, left_cases, right_cases, max_checks):
    fields = {"mIoU": "top1_iou", **{f"R1@IoU={t}": f"R@1/IoU={t}" for t in ("0.3", "0.5", "0.7")}}
    groups = {}
    for query, a, b in zip(queries, left, right):
        differences = {name: (a[key] - b[key] if key == "top1_iou" else a["metrics"][key] - b["metrics"][key])
                       for name, key in fields.items()}
        groups.setdefault(query["scope_video_ids"][0], []).append(differences)
    names, rng = sorted(groups), random.Random(BOOTSTRAP_SEED)
    sums = {name: {field: sum(row[field] for row in rows) for field in fields} for name, rows in groups.items()}
    draws = {field: [] for field in fields}
    for _ in range(BOOTSTRAP_REPETITIONS):
        chosen = rng.choices(names, k=len(names))
        count = sum(len(groups[name]) for name in chosen)
        for field in fields:
            draws[field].append(100 * sum(sums[name][field] for name in chosen) / count)
    return {"source_groups": len(groups), "queries": len(queries), "bootstrap_repetitions": BOOTSTRAP_REPETITIONS,
            "bootstrap_seed": BOOTSTRAP_SEED, "small_group_warning": len(groups) < 30,
            "matched_full_budget_queries": sum(a["result"]["budget"]["calls"] == b["result"]["budget"]["calls"] == max_checks
                                                and a["result"]["budget"]["frames"] == b["result"]["budget"]["frames"] == 8 * max_checks
                                                for a, b in zip(left_cases, right_cases)),
            "matched_three_check_queries": sum(a["result"]["budget"]["calls"] == b["result"]["budget"]["calls"] == 3
                                                 and a["result"]["budget"]["frames"] == b["result"]["budget"]["frames"] == 24
                                                 for a, b in zip(left_cases, right_cases)),
            "matched_input_and_request_queries": sum(all(a["result"]["budget"][field] == b["result"]["budget"][field]
                                                          for field in ("calls", "frames", "http_attempts", "sent_frame_slots"))
                                                     for a, b in zip(left_cases, right_cases)),
            "metrics": {field: {"delta_percentage_points": 100 * sum(sums[name][field] for name in names) / len(queries),
                                "ci95_percentage_points": [_percentile(draws[field], .025), _percentile(draws[field], .975)]}
                        for field in fields},
            "note": "Paired bootstrap resamples whole source videos and retains all their queries. Equal caps are not equal actual work; this pilot does not establish SOTA."}


def summarize(manifest, cases, conditions=CONDITIONS, *, max_checks=3):
    """Return aggregate publication fields separately from private per-query diagnostics."""
    validate_manifest(manifest)
    if type(max_checks) is not int or not 1 <= max_checks <= 6:
        raise ValueError("Report max_checks must be an integer within1..6")
    if (not isinstance(conditions, (tuple, list)) or not conditions or len(set(conditions)) != len(conditions)
            or any(condition not in CONDITIONS for condition in conditions)):
        raise ValueError("Conditions must be distinct known benchmark policies")
    queries = manifest["queries"]
    if any(len(q["scope_video_ids"]) != 1 or len(q["targets"]) != 1 for q in queries):
        raise ValueError("The Charades pilot requires one supplied video and one target per query")
    if not isinstance(cases, list):
        raise ValueError("Cases must be a complete list")
    expected = {(str(query["id"]), condition) for query in queries for condition in conditions}
    indexed = {}
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Every case must be a structured object")
        query_id = case.get("query_id")
        if isinstance(query_id, bool) or not isinstance(query_id, (str, int)):
            raise ValueError("Case query ID must be a string or integer")
        condition = case.get("condition")
        if not isinstance(condition, str):
            raise ValueError("Every case requires its named condition")
        key = (str(query_id), condition)
        if key not in expected or key in indexed:
            raise ValueError("Case query/condition grid is unknown or duplicated")
        indexed[key] = case
    if set(indexed) != expected:
        raise ValueError("Missing query/condition cases; no failed queries may be dropped")
    reports, private, ordered = {}, {}, {}
    for condition in conditions:
        ordered[condition] = [indexed[(str(query["id"]), condition)] for query in queries]
        predictions = []
        partial = unresolved = 0
        point_evidence = []
        for query, case in zip(queries, ordered[condition]):
            _validate_case(case, query, manifest["videos"], max_checks)
            candidates = case_predictions(case)
            predictions.append({"query_id": query["id"], "candidates": candidates})
            point_evidence.append([interval["start_seconds"] for step in case["result"]["checks"]
                                   for interval in step["verification"]["result"].get("intervals", [])
                                   if condition == "ranked_fixed" and interval["start_seconds"] == interval["end_seconds"]])
            partial += sum(p["query_support"] == "partial" for p in case["result"].get("proposals", []))
            unresolved += sum(p["start_seconds"] is None for p in case["result"].get("proposals", []))
        scored = evaluate(manifest, predictions, ks=(1, 5))
        private[condition] = [{**row, "video_id": query["scope_video_ids"][0], "predictions": predicted["candidates"],
                               "point_evidence_seconds": points, "point_only": bool(points) and not predicted["candidates"]}
                              for query, row, predicted, points in zip(queries, scored["per_query"], predictions, point_evidence)]
        reports[condition] = {"query_count": len(queries), "primary_percent": {"mIoU": 100 * scored["mean_top1_iou"],
                              **{f"R1@IoU={t}": 100 * scored["metrics"][f"R@1/IoU={t}"] for t in ("0.3", "0.5", "0.7")}},
                              "rank5_diagnostic_percent": {t: 100 * scored["metrics"][f"R@5/IoU={t}"] for t in ("0.3", "0.5", "0.7")},
                              "abstention_rate": sum(not p["candidates"] for p in predictions) / len(queries),
                              "model_supported_query_rate": sum(bool(p["candidates"]) for p in predictions) / len(queries),
                              "point_evidence_count": sum(len(points) for points in point_evidence),
                              "point_only_queries": sum(bool(points) and not p["candidates"] for points, p in zip(point_evidence, predictions)),
                              "partial_proposals": partial, "unresolved_proposals": unresolved,
                              "cost": _cost(ordered[condition], max_checks), "boundary_diagnostics": _boundary_diagnostics(queries, ordered[condition]),
                              "strata": _strata(manifest, scored["per_query"])}
    paired = {"extent_minus_" + baseline: _paired(queries, private["extent"], private[baseline], ordered["extent"], ordered[baseline], max_checks)
              for baseline in ("uniform_extent", "ranked_fixed") if "extent" in conditions and baseline in conditions}
    return {"aggregate": {"comparison_version": "charades-source-paired-point-evidence-v2", "dataset": manifest["name"], "split": manifest["split"],
                           "configured_cap": {"max_checks": max_checks, "max_frames": 8 * max_checks},
                           "query_count": len(queries), "video_count": len({q["scope_video_ids"][0] for q in queries}),
                           "task": "supplied-video temporal grounding", "conditions": reports, "paired_comparisons": paired,
                           "strata_definition": "Predeclared diagnostics from canonical target duration: <=5s, >5..10s, >10s. Reference-edge touching means target start0 or target end at annotation duration within absolute1e-6s. Empty bins are omitted; these groups do not change selection or primary scoring.",
                           "point_evidence_note": "Point counts are raw zero-duration baseline match entries, including repeated timestamps. They remain evidence, never temporal interval predictions. Only nonzero intervals receive interval ranks; filtering preserves their relative order. A point-only query is a localization abstention with zero IoU.",
                           "protocol_note": "R1 and mIoU use VSLNet-compatible formulas and explicit author-processed targets. Plain rank5 is diagnostic; legacy TALL uses temporal NMS. No trained baseline or full benchmark reproduction is claimed.",
                           "limits": "Selected pilot only; few independent source groups and an unpinned hosted model limit confidence. Boundary completeness is a model estimate; speech and reliable counts are not evaluated."},
            "private_per_query": private}
