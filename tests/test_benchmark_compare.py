from copy import deepcopy
import json

import pytest

from video_search.benchmark_compare import case_predictions, summarize


CONDITIONS = ("ranked_fixed", "uniform_extent", "extent")


def manifest():
    return {"name": "synthetic", "split": "held-out-pilot", "provenance": "Synthetic labels only",
            "videos": {"one": {"duration_seconds": 30}, "two": {"duration_seconds": 30}},
            "queries": [{"id": "q1", "query": "secret query text", "scope_video_ids": ["one"],
                         "targets": [{"video_id": "one", "start_seconds": 5, "end_seconds": 15}]},
                        {"id": "q2", "query": "another secret", "scope_video_ids": ["one"],
                         "targets": [{"video_id": "one", "start_seconds": 5, "end_seconds": 15}]},
                        {"id": "q3", "query": "private label", "scope_video_ids": ["two"],
                         "targets": [{"video_id": "two", "start_seconds": 5, "end_seconds": 15}]}]}


def proposal(video="one", start=5, end=15, support="all", complete=True):
    return {"recording_id": "recording-" + video, "start_seconds": start, "end_seconds": end,
            "query_support": support, "complete": complete,
            "onset": {"state": "observed", "lower_seconds": 4, "upper_seconds": 6},
            "offset": {"state": "observed", "lower_seconds": 14, "upper_seconds": 16}}


def case(query="q1", video="one", condition="extent", start=5, end=15):
    interval = {"start_seconds": start, "end_seconds": end}
    recording = "recording-" + video
    checks = [{"candidate": {"recording_id": recording, "source_status": "available"},
               "verification": {"id": f"{query}-{condition}-{i}", "recording_id": recording,
                                "checked_by_model": True,
                                "samples": [{"source_seconds": 5 + j} for j in range(8)],
                                "result": {"status": "match", "intervals": [interval],
                                           "_trace": {"frame_sha256": [f"{j:064x}" for j in range(8)], "http_attempts": 1}}}} for i in range(3)]
    result = {"status": "match", "checks": checks,
              "budget": {"calls": 3, "frames": 24, "http_attempts": 3, "sent_frame_slots": 24,
                         "unique_frames": 8, "max_checks": 3, "max_frames": 24}}
    if condition != "ranked_fixed":
        result["proposals"] = [proposal(video, start, end)]
    return {"query_id": query, "video_id": video, "recording_id": recording,
            "condition": condition, "result": result, "elapsed_seconds": 2.0, "http_attempts": 3}


def cases():
    return [case(query, video, condition) for query, video in [("q1", "one"), ("q2", "one"), ("q3", "two")]
            for condition in CONDITIONS]


def test_complete_grid_and_aggregate_are_private_by_construction():
    result = summarize(manifest(), cases())
    aggregate = result["aggregate"]
    for condition in CONDITIONS:
        row = aggregate["conditions"][condition]
        assert row["primary_percent"]["R1@IoU=0.5"] == 100
        assert row["primary_percent"]["mIoU"] == 100
        assert row["cost"]["logical_calls"] == 9
        assert row["cost"]["input_frame_slots"] == 72
        assert row["cost"]["latency_p95_seconds"] == 2
    text = json.dumps(aggregate)
    assert all(secret not in text for secret in ["secret query text", "another secret", "private label", "q1", "recording-one"])
    assert len(result["private_per_query"]["extent"]) == 3
    assert aggregate["paired_comparisons"]["extent_minus_uniform_extent"]["matched_three_check_queries"] == 3


def test_ranked_predictions_preserve_check_and_interval_order():
    row = case(condition="ranked_fixed")
    row["result"]["checks"][0]["verification"]["result"]["intervals"] = [
        {"start_seconds": 10, "end_seconds": 12}, {"start_seconds": 2, "end_seconds": 4}]
    before = deepcopy(row)
    predicted = case_predictions(row)
    assert [(p["start_seconds"], p["end_seconds"]) for p in predicted[:2]] == [(10, 12), (2, 4)]
    assert row == before


def test_partial_and_point_proposals_are_abstentions_without_invented_duration():
    row = case()
    row["result"]["proposals"] = [proposal(support="partial", complete=False),
                                    proposal(start=None, end=None, complete=False)]
    assert case_predictions(row) == []
    data = cases()
    data[2] = row
    result = summarize(manifest(), data)["aggregate"]["conditions"]["extent"]
    assert result["abstention_rate"] == pytest.approx(1 / 3)
    assert result["unresolved_proposals"] == 1
    assert result["partial_proposals"] == 1
    assert result["primary_percent"]["mIoU"] == pytest.approx(200 / 3)


@pytest.mark.parametrize("change", ["missing", "duplicate", "extra", "wrong_video", "wrong_recording", "failed", "unavailable"])
def test_invalid_grid_or_source_fails_instead_of_dropping_a_case(change):
    rows = cases()
    if change == "missing":
        rows.pop()
    elif change == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif change == "extra":
        rows.append(case(query="unknown"))
    elif change == "wrong_video":
        rows[0]["video_id"] = "two"
    elif change == "wrong_recording":
        rows[0]["result"]["checks"][0]["verification"]["recording_id"] = "another-recording"
    elif change == "failed":
        rows[0]["error"] = {"code": "provider_failed"}
    else:
        rows[0]["result"]["checks"][0]["candidate"]["source_status"] = "changed"
    with pytest.raises(ValueError):
        summarize(manifest(), rows)


@pytest.mark.parametrize("values", [(float("nan"), 15), (5, float("inf")), (5, 31), (None, 15), (15, 5)])
def test_malformed_proposal_is_not_ignored_even_if_partial(values):
    rows = cases()
    rows[2]["result"]["proposals"][0].update(start_seconds=values[0], end_seconds=values[1],
                                             query_support="partial", complete=False)
    with pytest.raises(ValueError):
        summarize(manifest(), rows)


def test_reference_target_bounds_do_not_relax_media_predictions():
    data = manifest()
    data["videos"]["one"].update(duration_seconds=14.9, annotation_duration_seconds=30)
    with pytest.raises(ValueError):
        summarize(data, cases())


def test_costs_count_retries_and_actual_work_instead_of_caps():
    rows = cases()
    rows[2]["result"]["budget"].update(http_attempts=4, sent_frame_slots=32)
    rows[2]["http_attempts"] = 4
    rows[2]["result"]["checks"][0]["verification"]["result"]["_trace"]["http_attempts"] = 2
    short = rows[5]
    short["result"]["checks"] = short["result"]["checks"][:2]
    short["result"]["budget"].update(calls=2, frames=16, http_attempts=2, sent_frame_slots=16)
    short["http_attempts"] = 2
    report = summarize(manifest(), rows)["aggregate"]
    cost = report["conditions"]["extent"]["cost"]
    assert cost["logical_calls"] == 8
    assert cost["http_attempts"] == 9
    assert cost["input_frame_slots"] == 64 and cost["sent_frame_slots"] == 72
    assert report["paired_comparisons"]["extent_minus_uniform_extent"]["matched_three_check_queries"] == 2
    assert report["paired_comparisons"]["extent_minus_uniform_extent"]["matched_input_and_request_queries"] == 1


def test_grouped_paired_bootstrap_is_deterministic_and_does_not_bootstrap_individual_queries():
    rows = cases()
    for row in rows:
        if row["condition"] == "uniform_extent":
            row["result"]["proposals"][0].update(start_seconds=20, end_seconds=25, complete=False)
    first = summarize(manifest(), rows)
    second = summarize(manifest(), rows)
    paired = first["aggregate"]["paired_comparisons"]["extent_minus_uniform_extent"]
    assert first == second
    assert paired["source_groups"] == 2 and paired["queries"] == 3
    assert paired["bootstrap_repetitions"] == 2000
    assert paired["metrics"]["mIoU"]["delta_percentage_points"] == 100
    assert paired["metrics"]["mIoU"]["ci95_percentage_points"] == [100, 100]
    assert paired["small_group_warning"] is True


def test_complete_claim_localization_failure_is_only_a_proxy_and_brackets_are_measured():
    rows = cases()
    rows[2]["result"]["proposals"][0].update(end_seconds=29.5,
                                             offset={"state": "observed", "lower_seconds": 29, "upper_seconds": 30})
    aggregate = summarize(manifest(), rows)["aggregate"]["conditions"]["extent"]
    assert aggregate["boundary_diagnostics"]["complete_claim_localization_failure_rate"] == pytest.approx(1 / 3)
    assert aggregate["boundary_diagnostics"]["onset_coverage_given_observed"] == 1
    assert aggregate["boundary_diagnostics"]["onset_midpoint_mae_seconds"] == 0
    assert "proxy" in aggregate["boundary_diagnostics"]["note"]


@pytest.mark.parametrize("field,value", [("calls", 2), ("frames", 23), ("http_attempts", 2), ("sent_frame_slots", 23)])
def test_inconsistent_budget_is_an_error(field, value):
    rows = cases()
    rows[0]["result"]["budget"][field] = value
    with pytest.raises(ValueError):
        summarize(manifest(), rows)


@pytest.mark.parametrize("change", ["missing_hashes", "wrong_hash", "not_model_checked", "trace_attempts"])
def test_missing_or_inconsistent_model_trace_fails(change):
    rows = cases()
    verification = rows[0]["result"]["checks"][0]["verification"]
    if change == "missing_hashes":
        verification["result"]["_trace"].pop("frame_sha256")
    elif change == "wrong_hash":
        verification["result"]["_trace"]["frame_sha256"][0] = "not-a-hash"
    elif change == "not_model_checked":
        verification["checked_by_model"] = False
    else:
        verification["result"]["_trace"]["http_attempts"] = 2
    with pytest.raises(ValueError):
        summarize(manifest(), rows)


def test_reference_numerical_cases_have_expected_recall_and_miou_percentages():
    data = manifest()
    data["videos"]["one"]["duration_seconds"] = 100
    data["queries"] = [{"id": f"q{i}", "query": "synthetic reference case", "scope_video_ids": ["one"],
                        "targets": [{"video_id": "one", "start_seconds": 0, "end_seconds": 10}]} for i in range(6)]
    intervals = [(0, 10), (0, 10 / .7), (0, 20), (0, 10 / .3), (50, 60), (70, 80)]
    rows = [case(f"q{i}", condition="ranked_fixed", start=start, end=end) for i, (start, end) in enumerate(intervals)]
    primary = summarize(data, rows, conditions=("ranked_fixed",))["aggregate"]["conditions"]["ranked_fixed"]["primary_percent"]
    assert primary["R1@IoU=0.3"] == pytest.approx(100 * 4 / 6)
    assert primary["R1@IoU=0.5"] == 50
    assert primary["R1@IoU=0.7"] == pytest.approx(100 * 2 / 6)
    assert primary["mIoU"] == pytest.approx(100 * 2.5 / 6)


def test_larger_caps_cannot_be_mixed_into_the_frozen_three_check_pilot():
    rows = cases()
    rows[2]["result"]["budget"].update(max_checks=6, max_frames=48)
    with pytest.raises(ValueError, match="separate report"):
        summarize(manifest(), rows)


def test_predeclared_duration_and_reference_edge_strata_include_every_query():
    data = manifest()
    data["videos"]["two"].update(duration_seconds=30.1, annotation_duration_seconds=30)
    targets = [("q1", "one", 0, 5), ("q2", "one", 5, 10), ("q3", "two", 5, 15),
               ("q4", "two", 15, 30), ("q5", "two", 14.9999995, 29.9999995), ("q6", "two", 20, 29.999)]
    data["queries"] = [{"id": query, "query": "private diagnostic label", "scope_video_ids": [video],
                        "targets": [{"video_id": video, "start_seconds": start, "end_seconds": end}]}
                       for query, video, start, end in targets]
    rows = [case(query, video, condition, start, end) for query, video, start, end in targets for condition in CONDITIONS]
    for row in rows:
        if row["condition"] == "extent" and row["query_id"] == "q1":
            row["result"].update(proposals=[], status="insufficient_evidence")
    before_data, before_rows = deepcopy(data), deepcopy(rows)
    report = summarize(data, rows)["aggregate"]
    extent = report["conditions"]["extent"]["strata"]
    duration = extent["event_duration"]
    assert set(duration) == {"up_to_5_seconds", "over_5_to_10_seconds", "over_10_seconds"}
    assert all(group["query_count"] == 2 and group["video_count"] == 1 for group in duration.values())
    assert duration["up_to_5_seconds"]["primary_percent"] == {"R1@IoU=0.5": 50, "R1@IoU=0.7": 50, "mIoU": 50}
    assert duration["over_5_to_10_seconds"]["primary_percent"]["mIoU"] == 100
    edges = extent["reference_edge"]
    assert edges["touches_reference_edge"]["query_count"] == 3
    assert edges["touches_reference_edge"]["video_count"] == 2
    assert edges["interior"]["query_count"] == 3 and edges["interior"]["video_count"] == 2
    assert report["conditions"]["ranked_fixed"]["primary_percent"]["mIoU"] == 100
    assert "private diagnostic label" not in json.dumps(report)
    assert data == before_data and rows == before_rows


def test_empty_strata_are_omitted_without_changing_primary_metrics():
    report = summarize(manifest(), cases())["aggregate"]["conditions"]["extent"]
    assert set(report["strata"]["event_duration"]) == {"over_5_to_10_seconds"}
    assert set(report["strata"]["reference_edge"]) == {"interior"}
    assert report["primary_percent"]["R1@IoU=0.5"] == report["strata"]["reference_edge"]["interior"]["primary_percent"]["R1@IoU=0.5"] == 100


@pytest.mark.parametrize("stamp", [0, 6.9])
def test_baseline_point_evidence_is_preserved_and_scores_as_interval_abstention(stamp):
    row = case(condition="ranked_fixed", start=stamp, end=stamp)
    before = deepcopy(row)
    assert case_predictions(row) == []
    assert row == before
    rows = cases()
    rows[0] = row
    report = summarize(manifest(), rows)
    baseline = report["aggregate"]["conditions"]["ranked_fixed"]
    assert baseline["point_only_queries"] == 1
    assert baseline["point_evidence_count"] == 3
    assert baseline["primary_percent"]["R1@IoU=0.5"] == pytest.approx(200 / 3)
    assert baseline["primary_percent"]["mIoU"] == pytest.approx(200 / 3)
    private = report["private_per_query"]["ranked_fixed"][0]
    assert private["predictions"] == [] and private["top1_iou"] == 0
    assert private["point_evidence_seconds"] == [stamp, stamp, stamp]
    assert private["point_only"] is True


def test_mixed_baseline_points_and_intervals_keep_nonzero_prediction_order():
    row = case(condition="ranked_fixed")
    row["result"]["checks"][0]["verification"]["result"]["intervals"] = [
        {"start_seconds": 0, "end_seconds": 0}, {"start_seconds": 5, "end_seconds": 15},
        {"start_seconds": 6.9, "end_seconds": 6.9}, {"start_seconds": 2, "end_seconds": 4}]
    for check in row["result"]["checks"][1:]:
        check["verification"]["result"].update(status="no_match", intervals=[])
    before = deepcopy(row)
    assert [(p["start_seconds"], p["end_seconds"]) for p in case_predictions(row)] == [(5, 15), (2, 4)]
    rows = cases()
    rows[0] = row
    report = summarize(manifest(), rows)
    baseline = report["aggregate"]["conditions"]["ranked_fixed"]
    assert baseline["point_evidence_count"] == 2 and baseline["point_only_queries"] == 0
    assert baseline["primary_percent"]["R1@IoU=0.5"] == 100
    assert report["private_per_query"]["ranked_fixed"][0]["top1_iou"] == 1
    assert "relative order" in report["aggregate"]["point_evidence_note"]
    assert row == before


@pytest.mark.parametrize("start,end", [(-1, -1), (31, 31), (7.1, 6.9), (float("nan"), 6.9)])
def test_invalid_baseline_points_and_reversed_bounds_still_fail(start, end):
    rows = cases()
    rows[0] = case(condition="ranked_fixed", start=start, end=end)
    with pytest.raises(ValueError):
        summarize(manifest(), rows)


def test_extent_proposal_cannot_turn_a_point_into_a_duration():
    rows = cases()
    rows[2]["result"]["proposals"][0].update(start_seconds=6.9, end_seconds=6.9, complete=False)
    with pytest.raises(ValueError):
        summarize(manifest(), rows)


def capped_cases(max_checks):
    rows = cases()
    for row in rows:
        row["result"]["checks"] = row["result"]["checks"][:max_checks]
        row["result"]["budget"].update(calls=max_checks, frames=8 * max_checks, http_attempts=max_checks,
                                         sent_frame_slots=8 * max_checks, max_checks=max_checks, max_frames=8 * max_checks)
        row["http_attempts"] = max_checks
    return rows


@pytest.mark.parametrize("max_checks", [1, 2])
def test_predeclared_smaller_caps_keep_all_queries_and_paired_metrics(max_checks):
    report = summarize(manifest(), capped_cases(max_checks), max_checks=max_checks)["aggregate"]
    assert report["configured_cap"] == {"max_checks": max_checks, "max_frames": 8 * max_checks}
    paired = report["paired_comparisons"]["extent_minus_uniform_extent"]
    assert paired["matched_full_budget_queries"] == 3
    assert paired["matched_three_check_queries"] == 0
    assert paired["metrics"]["mIoU"]["delta_percentage_points"] == 0
    assert report["conditions"]["extent"]["primary_percent"]["mIoU"] == 100
    cost = report["conditions"]["extent"]["cost"]
    assert cost["actual_full_budget_queries"] == 3
    assert "controller" in cost["latency_scope"] and "excludes retrieval" in cost["latency_scope"]


@pytest.mark.parametrize("declared,requested", [(1, 2), (2, 1), (2, 3)])
def test_recorded_caps_must_match_the_requested_report(declared, requested):
    with pytest.raises(ValueError, match="caps"):
        summarize(manifest(), capped_cases(declared), max_checks=requested)


@pytest.mark.parametrize("value", [True, 0, 7, 1.5])
def test_invalid_report_caps_fail_before_scoring(value):
    with pytest.raises(ValueError):
        summarize(manifest(), cases(), max_checks=value)


def test_full_budget_match_count_uses_declared_cap_and_actual_work():
    rows = capped_cases(2)
    row = rows[2]
    row["result"]["checks"] = row["result"]["checks"][:1]
    row["result"]["budget"].update(calls=1, frames=8, http_attempts=1, sent_frame_slots=8)
    row["http_attempts"] = 1
    report = summarize(manifest(), rows, max_checks=2)["aggregate"]
    assert report["paired_comparisons"]["extent_minus_uniform_extent"]["matched_full_budget_queries"] == 2
