"""Bounded source checks with explicit evidence and stopping limits."""

import math

from video_search import analysis, media, store
from video_search.vlm import VLMError


POLICY_VERSION = "distinct-intervals-one-gap-refinement-v1"


def _key(candidate):
    return (str(candidate["recording_id"]), candidate["start_seconds"], candidate["end_seconds"])


def _overlaps(left, right):
    return (str(left["recording_id"]) == str(right["recording_id"])
            and max(left["start_seconds"], right["start_seconds"]) < min(left["end_seconds"], right["end_seconds"]))


def next_candidate(candidates, inspected):
    """Defer overlapping hits; retain them if no distinct hit remains."""
    if not candidates:
        raise ValueError("At least one candidate is required")
    return next((index for index, item in enumerate(candidates)
                 if not any(_overlaps(item, previous) for previous in inspected)), 0)


def refinement_interval(verification):
    """Choose the half containing the largest gap in actual source samples."""
    start, end = verification["inspection_start_seconds"], verification["inspection_end_seconds"]
    stamps = sorted({start, end, *(item["source_seconds"] for item in verification["samples"])})
    left, right = max(zip(stamps, stamps[1:]), key=lambda pair: (pair[1] - pair[0], -pair[0]))
    midpoint = (start + end) / 2
    return (start, midpoint) if (left + right) / 2 < midpoint else (midpoint, end)


def _unique_seconds(candidates):
    intervals = {}
    for item in candidates:
        intervals.setdefault(str(item["recording_id"]), []).append((item["start_seconds"], item["end_seconds"]))
    seconds = 0.0
    for windows in intervals.values():
        previous_end = 0.0
        for start, end in sorted(windows):
            seconds += max(0, end - max(start, previous_end))
            previous_end = max(previous_end, end)
    return seconds


def check_candidates(settings, query, candidates, max_checks=3, policy="adaptive", start_seconds=None, end_seconds=None):
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 1000:
        raise ValueError("Query must contain 1..1000 characters")
    if type(max_checks) is not int or not 1 <= max_checks <= 12:
        raise ValueError("Check budget must be between one and twelve")
    if policy not in {"ranked", "adaptive"}:
        raise ValueError("Policy must be ranked or adaptive")
    if any(value is not None and (not math.isfinite(value) or value < 0) for value in (start_seconds, end_seconds)):
        raise ValueError("Search times must be finite and nonnegative")
    if end_seconds is not None and end_seconds <= (start_seconds or 0):
        raise ValueError("Search end must follow its start")
    if len(candidates) > 100:
        raise ValueError("At most 100 candidates may be checked")

    pending, recordings, keys = [], {}, set()
    duplicates = 0
    for candidate in candidates:
        recording_id, start, end = _key(candidate)
        if not all(math.isfinite(value) for value in (start, end)) or not 0 <= start < end or end - start > 30:
            raise ValueError("Candidate bounds must be finite, ordered, and at most 30 seconds apart")
        if recording_id not in recordings:
            recordings[recording_id] = store.get_recording(settings.database_url, recording_id)
        recording = recordings[recording_id]
        if recording is None or end > recording["metadata"]["duration_seconds"]:
            raise ValueError("Candidate must belong to an existing recording and stay within it")
        if candidate.get("source_status") != "available":
            raise media.MediaError("source_unavailable", "Candidate source is unavailable", recording_id=recording_id,
                                   source_status=candidate.get("source_status"))
        start, end = max(start, start_seconds or 0), min(end, end_seconds if end_seconds is not None else end)
        if start >= end:
            raise ValueError("Candidate does not overlap the requested scope")
        item = {**candidate, "recording_id": recording_id, "start_seconds": start, "end_seconds": end}
        if "build_id" in item:
            item["build_id"] = str(item["build_id"])
        if _key(item) in keys:
            duplicates += 1
        else:
            keys.add(_key(item))
            pending.append(item)

    checks, inspected, seen = [], [], set()
    refinement, refinement_created = None, False
    stop_reason = "candidates_exhausted"
    while len(checks) < max_checks:
        pending = [item for item in pending if _key(item) not in seen]
        if refinement is not None and _key(refinement) in seen:
            refinement = None
        if not pending and refinement is None:
            break
        index = next_candidate(pending, inspected) if pending and policy == "adaptive" else 0
        distinct = bool(pending) and not any(_overlaps(pending[index], item) for item in inspected)
        # Spend a check on a separate candidate before refining uncertain evidence.
        if refinement is not None and (len(checks) >= 2 or not distinct):
            candidate, refinement, reason = refinement, None, "dense_refinement"
        else:
            candidate = pending.pop(index)
            reason = "distinct_candidate" if policy == "adaptive" and inspected and distinct else "ranked_candidate"
        try:
            verification = analysis.verify(settings, recordings[candidate["recording_id"]], query,
                                           candidate["start_seconds"], candidate["end_seconds"], context=0)
        except (media.MediaError, VLMError) as exc:
            exc.details["completed_evidence_checks"] = [step["verification"]["id"] for step in checks]
            raise
        seen.add(_key(candidate))
        inspected.append(candidate)
        checks.append({"candidate": candidate, "verification": verification, "reason": reason})
        if verification["result"]["status"] == "match":
            stop_reason = "match_found"
            break
        if policy == "adaptive" and not refinement_created and verification["result"]["status"] == "insufficient_evidence":
            start, end = refinement_interval(verification)
            refinement = {**candidate, "start_seconds": start, "end_seconds": end}
            refinement_created = True
    if stop_reason != "match_found" and len(checks) == max_checks:
        stop_reason = "budget_exhausted"
    return {
        "status": "match" if stop_reason == "match_found" else "insufficient_evidence",
        "stop_reason": stop_reason, "policy": policy,
        "policy_version": POLICY_VERSION if policy == "adaptive" else "ranked-stop-on-match-v1",
        "checks": checks, "duplicate_candidates": duplicates,
        "budget": {"max_checks": max_checks, "max_frames": 8 * max_checks, "calls": len(checks),
                   "http_attempts": sum(step["verification"]["result"]["_trace"]["http_attempts"] for step in checks),
                   "sent_frame_slots": sum(len(step["verification"]["samples"]) * step["verification"]["result"]["_trace"]["http_attempts"] for step in checks),
                   "cost_note": "Calls and frames count completed logical checks. HTTP attempts and sent frame slots include retries; provider compute and failed-attempt token use are unknown.",
                   "frames": sum(len(step["verification"]["samples"]) for step in checks),
                   "inspected_seconds": sum(item["end_seconds"] - item["start_seconds"] for item in inspected),
                   "unique_inspected_seconds": _unique_seconds(inspected)},
        "complete_video_coverage": False, "supports_absence_or_counts": False,
        "scope_note": "Only sampled frames were checked. Matches do not prove complete event coverage; missing matches do not prove absence or a count.",
    }
