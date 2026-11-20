"""Estimate one event's extent from bounded, reference-linked source checks."""

import math

from video_search import analysis, evidence, media, store
from video_search.vlm import VLMError


POLICY_VERSION = "seed-anchor-event-brackets-v1"
NEIGHBOR_SECONDS = 8.75


def sample_brackets(samples, states):
    """Bracket the first present run; an unknown sample never becomes an observed edge."""
    if len(samples) != len(states) or not samples:
        raise ValueError("Samples and states must be nonempty and have the same length")
    if any(state not in {"present", "absent", "unknown"} for state in states):
        raise ValueError("Unknown sample state")
    stamps = [sample["source_seconds"] for sample in samples]
    if any(not math.isfinite(t) for t in stamps) or stamps != sorted(stamps):
        raise ValueError("Sample timestamps must be finite and ordered")
    runs, start = [], None
    for index, state in enumerate([*states, "absent"]):
        if state == "present" and start is None:
            start = index
        elif state != "present" and start is not None:
            runs.append((start, index - 1))
            start = None
    if not runs:
        return None
    first, last = runs[0]
    onset = {"state": "open" if first == 0 else "observed" if states[first - 1] == "absent" else "unknown",
             "lower_seconds": None if first == 0 else stamps[first - 1], "upper_seconds": stamps[first]}
    offset = {"state": "open" if last == len(states) - 1 else "observed" if states[last + 1] == "absent" else "unknown",
              "lower_seconds": stamps[last], "upper_seconds": None if last == len(states) - 1 else stamps[last + 1]}
    return {"onset": onset, "offset": offset, "first_present_seconds": stamps[first],
            "last_present_seconds": stamps[last], "run_count": len(runs)}


def _new_evidence(verification):
    pairs = [(sample, state) for sample, state in zip(verification["samples"], verification["result"]["sample_support"])
             if not sample["is_reference"]]
    return [sample for sample, _ in pairs], [state for _, state in pairs]


def _estimate(proposal):
    onset, offset = proposal["onset"], proposal["offset"]
    start = ((onset["lower_seconds"] + onset["upper_seconds"]) / 2
             if onset["state"] == "observed" else proposal["first_present_seconds"])
    end = ((offset["lower_seconds"] + offset["upper_seconds"]) / 2
           if offset["state"] == "observed" else proposal["last_present_seconds"])
    proposal["start_seconds"], proposal["end_seconds"] = (start, end) if start < end else (None, None)
    proposal["complete"] = (onset["state"] == offset["state"] == "observed"
                            and proposal["query_support"] == "all" and proposal["run_count"] == 1 and start < end)


def _seed(verification):
    samples, states = _new_evidence(verification)
    bounds = sample_brackets(samples, states)
    if bounds is None:
        return None
    proposal = {**bounds, "recording_id": verification["recording_id"],
                "query_support": verification["result"]["query_support"],
                "supporting_check_ids": [verification["id"]], "unlinked_check_ids": [], "auxiliary_check_ids": [],
                "evidence_points_seconds": [sample["source_seconds"] for sample, state in zip(samples, states)
                                            if state == "present" and bounds["first_present_seconds"] <= sample["source_seconds"] <= bounds["last_present_seconds"]],
                "absence_points_seconds": [sample["source_seconds"] for sample, state in zip(samples, states) if state == "absent"],
                "verified": False, "estimate_type": "sample-bracket-midpoints",
                "scope_note": "Model-linked event estimate from sampled evidence; continuous visibility and semantic completeness are not certified."}
    _estimate(proposal)
    return proposal


def _extend(proposal, verification, side):
    samples, states = _new_evidence(verification)
    bounds = sample_brackets(samples, states)
    edge = "onset" if side == "before" else "offset"
    if verification["result"]["sample_support"][verification["reference"]["sample_index"]] != "present":
        proposal["unlinked_check_ids"].append(verification["id"])
        return False
    if proposal[edge]["state"] == "observed":
        proposal["auxiliary_check_ids"].append(verification["id"])
        return True
    if bounds is None and verification["result"]["status"] == "no_match" and all(state == "absent" for state in states):
        if side == "before" and samples[-1]["source_seconds"] < proposal["first_present_seconds"]:
            proposal[edge] = {"state": "observed", "lower_seconds": samples[-1]["source_seconds"],
                              "upper_seconds": proposal["first_present_seconds"]}
        elif side == "after" and samples[0]["source_seconds"] > proposal["last_present_seconds"]:
            proposal[edge] = {"state": "observed", "lower_seconds": proposal["last_present_seconds"],
                              "upper_seconds": samples[0]["source_seconds"]}
        else:
            proposal["unlinked_check_ids"].append(verification["id"])
            return False
    elif (bounds is not None and bounds["run_count"] == 1 and verification["result"]["status"] == "match"
          and verification["result"]["anchor_relation"] == "same_event"
          and (bounds["offset" if side == "before" else "onset"]["state"] == "open"
               or bounds["first_present_seconds"] <= verification["reference"]["source_seconds"] <= bounds["last_present_seconds"])
          and ((side == "before" and bounds["first_present_seconds"] <= proposal["first_present_seconds"])
               or (side == "after" and bounds["last_present_seconds"] >= proposal["last_present_seconds"]))):
        old_first, old_last = proposal["first_present_seconds"], proposal["last_present_seconds"]
        if (any(bounds["first_present_seconds"] <= t <= bounds["last_present_seconds"] for t in proposal["absence_points_seconds"])
                or any(state == "absent" and old_first <= sample["source_seconds"] <= old_last
                       for sample, state in zip(samples, states))):
            proposal["unlinked_check_ids"].append(verification["id"])
            return False
        proposal[edge] = bounds[edge]
        opposite = "offset" if side == "before" else "onset"
        if (proposal[opposite]["state"] != "observed" and bounds[opposite]["state"] == "observed"
                and bounds["first_present_seconds"] <= old_first <= old_last <= bounds["last_present_seconds"]):
            proposal[opposite] = bounds[opposite]
        proposal["first_present_seconds"] = min(old_first, bounds["first_present_seconds"])
        proposal["last_present_seconds"] = max(old_last, bounds["last_present_seconds"])
        proposal["evidence_points_seconds"].extend(sample["source_seconds"] for sample, state in zip(samples, states) if state == "present")
        if verification["result"]["query_support"] == "all":
            proposal["query_support"] = "all"
    else:
        proposal["unlinked_check_ids"].append(verification["id"])
        return False
    proposal["supporting_check_ids"].append(verification["id"])
    proposal["absence_points_seconds"] = sorted(set(proposal["absence_points_seconds"])
                                                   | {sample["source_seconds"] for sample, state in zip(samples, states) if state == "absent"})
    proposal["evidence_points_seconds"] = sorted(set(proposal["evidence_points_seconds"]))
    _estimate(proposal)
    return True


def _request_window(proposal, side, frontier, scope_start, scope_end, policy):
    edge = proposal["onset" if side == "before" else "offset"]
    if policy == "extent" and edge["state"] == "unknown" and edge["lower_seconds"] is not None and edge["upper_seconds"] is not None:
        lower, upper = edge["lower_seconds"], edge["upper_seconds"]
        middle = (lower + upper) / 2
        return max(scope_start, middle - NEIGHBOR_SECONDS / 2), min(scope_end, middle + NEIGHBOR_SECONDS / 2)
    if side == "before":
        return max(scope_start, frontier[0] - NEIGHBOR_SECONDS), frontier[0]
    return frontier[1], min(scope_end, frontier[1] + NEIGHBOR_SECONDS)


def check_candidates(settings, query, candidates, max_checks=3, policy="extent", start_seconds=None, end_seconds=None, *, spend_budget=False):
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 1000:
        raise ValueError("Query must contain 1..1000 characters")
    if type(max_checks) is not int or not 1 <= max_checks <= 6 or policy not in {"extent", "uniform_extent"}:
        raise ValueError("Extent policy requires one to six checks and a known policy")
    if type(spend_budget) is not bool:
        raise ValueError("spend_budget must be a boolean")
    if not isinstance(candidates, list) or len(candidates) > 100:
        raise ValueError("At most 100 candidates may be inspected")
    if any(value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)
                                or not math.isfinite(value) or value < 0) for value in (start_seconds, end_seconds)):
        raise ValueError("Search times must be finite and nonnegative")
    if end_seconds is not None and end_seconds <= (start_seconds or 0):
        raise ValueError("Search end must follow its start")
    pending, recordings, keys = [], {}, set()
    duplicates = 0
    for candidate in candidates:
        rid, start, end = str(candidate["recording_id"]), candidate["start_seconds"], candidate["end_seconds"]
        if any(not isinstance(t, (int, float)) or isinstance(t, bool) or not math.isfinite(t) for t in (start, end)) or not 0 <= start < end or end - start > 10:
            raise ValueError("Extent seeds require ordered, finite intervals of at most ten seconds")
        if rid not in recordings:
            recordings[rid] = store.get_recording(settings.database_url, rid)
        recording = recordings[rid]
        if recording is None or end > recording["metadata"]["duration_seconds"]:
            raise ValueError("Candidate must stay inside an existing recording")
        if candidate.get("source_status") != "available":
            raise media.MediaError("source_unavailable", "Extent candidate source is unavailable", recording_id=rid,
                                   source_status=candidate.get("source_status"))
        start, end = max(start, start_seconds or 0), min(end, end_seconds if end_seconds is not None else end)
        if start >= end:
            raise ValueError("Candidate does not overlap the requested scope")
        item = {**candidate, "recording_id": rid, "start_seconds": start, "end_seconds": end}
        if "build_id" in item:
            item["build_id"] = str(item["build_id"])
        key = evidence._key(item)
        if key in keys:
            duplicates += 1
        else:
            keys.add(key)
            pending.append(item)
    checks, inspected, seen, proposals = [], [], set(), []
    anchor, proposal, seed_candidate = None, None, None
    blocked, frontier, uniform_turn = set(), None, 0
    stop_reason = "candidates_exhausted"
    try:
        while len(checks) < max_checks:
            side = None
            if proposal is not None and (proposal["complete"] or proposal["onset"]["state"] == proposal["offset"]["state"] == "observed"):
                if not spend_budget:
                    stop_reason = ("event_bounded" if proposal["complete"] else
                                   "query_incomplete" if proposal["query_support"] != "all" else "event_unresolved")
                    break
                anchor["image"].close()
                anchor, proposal, seed_candidate, frontier = None, None, None, None
                blocked, uniform_turn = set(), 0
            if proposal is None:
                pending = [item for item in pending if evidence._key(item) not in seen]
                if not pending:
                    break
                candidate = pending.pop(0)
                start, end = candidate["start_seconds"], candidate["end_seconds"]
                reason = "budget_control_seed" if spend_budget and checks else "ranked_seed"
            else:
                rid = proposal["recording_id"]
                scope_start = start_seconds or 0
                scope_end = min(recordings[rid]["metadata"]["duration_seconds"], end_seconds if end_seconds is not None else math.inf)
                sides = (["before", "after"] if uniform_turn % 2 == 0 else ["after", "before"]) if policy == "uniform_extent" else [s for s, edge in [("before", "onset"), ("after", "offset")] if proposal[edge]["state"] != "observed"]
                chosen = None
                for option in sides:
                    if option in blocked:
                        continue
                    bounds = _request_window(proposal, option, frontier, scope_start, scope_end, policy)
                    if bounds[0] < bounds[1] and (rid, *bounds) not in seen:
                        chosen = option, *bounds
                        break
                    blocked.add(option)
                if chosen is None:
                    stop_reason = "scope_exhausted"
                    if spend_budget and any(evidence._key(item) not in seen for item in pending):
                        anchor["image"].close()
                        anchor, proposal, seed_candidate, frontier = None, None, None, None
                        blocked, uniform_turn = set(), 0
                        continue
                    break
                side, start, end = chosen
                candidate = {**seed_candidate, "start_seconds": start, "end_seconds": end}
                reason = "extent_" + side if policy == "extent" else "uniform_" + side
                uniform_turn += 1
            rid = candidate["recording_id"]
            try:
                verification, retained = analysis.inspect_extent(settings, recordings[rid], query, start, end, anchor,
                                                                policy=policy, reason=reason)
            except (media.MediaError, VLMError) as exc:
                exc.details["completed_evidence_checks"] = [step["verification"]["id"] for step in checks]
                raise
            seen.add((rid, start, end))
            inspected.append(candidate)
            checks.append({"candidate": candidate, "verification": verification, "reason": reason})
            if proposal is None and verification["result"]["status"] == "match":
                proposal = _seed(verification)
                proposals.append(proposal)
                anchor, seed_candidate, frontier = retained, candidate, [start, end]
            elif proposal is not None:
                if _extend(proposal, verification, side):
                    frontier[0], frontier[1] = min(frontier[0], start), max(frontier[1], end)
                else:
                    blocked.add(side)
        if not spend_budget and proposal and proposal["complete"]:
            stop_reason = "event_bounded"
        elif len(checks) == max_checks:
            stop_reason = "budget_exhausted"
    finally:
        if anchor is not None:
            anchor["image"].close()
    attempts = sum(check["verification"]["result"]["_trace"]["http_attempts"] for check in checks)
    unique = {(check["verification"]["recording_id"], sample["source_seconds"], digest)
              for check in checks for sample, digest in zip(check["verification"]["samples"], check["verification"]["result"]["_trace"]["frame_sha256"])}
    return {"status": "match" if proposals else "insufficient_evidence", "policy": policy,
            "policy_version": POLICY_VERSION, "stop_reason": stop_reason, "checks": checks,
            "proposals": proposals, "duplicate_candidates": duplicates, "spend_budget": spend_budget,
            "budget": {"max_checks": max_checks, "max_frames": 8 * max_checks, "calls": len(checks),
                       "frames": 8 * len(checks), "http_attempts": attempts, "sent_frame_slots": 8 * attempts,
                       "unique_frames": len(unique), "inspected_seconds": sum(i["end_seconds"] - i["start_seconds"] for i in inspected),
                       "unique_inspected_seconds": evidence._unique_seconds(inspected),
                       "cost_note": "Frame slots include repeated references; new-window duration excludes reference-only gaps. Provider retry compute is unknown."},
            "complete_video_coverage": False, "supports_absence_or_counts": False,
            "scope_note": "Only sampled evidence was inspected. Event brackets and completeness are model estimates, not continuous-coverage guarantees or counts."}
