from dataclasses import replace
import subprocess

import pytest

from video_search import extent, media, store
from video_search.config import Settings
from video_search.vlm import VLMError
from video_search.worker import process_one
from test_vlm import endpoint, envelope


def answer(states, *, status="match", support="all", relation="not_applicable"):
    return {"status": status, "query_support": support, "sample_support": states,
            "anchor_relation": relation, "observation": "The supplied samples support this event state."}


def extent_envelope(content):
    return envelope({key: value for key, value in content.items() if key != "status"})


@pytest.fixture
def imported(database_url, tmp_path):
    video = tmp_path / "extent.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64:r=10:d=32",
                    "-c:v", "mpeg4", str(video)], check=True, capture_output=True, timeout=30)
    settings = Settings(database_url, tmp_path)
    store.enqueue(database_url, video.name, *media.fingerprint(video))
    assert process_one(settings)
    recording = str(store.list_recordings(database_url)[0]["id"])
    return settings, {"recording_id": recording, "start_seconds": 10.0, "end_seconds": 20.0,
                      "source_status": "available"}


def test_brackets_require_adjacent_absent_and_present_samples():
    samples = [{"source_seconds": t} for t in range(8)]
    brackets = extent.sample_brackets(samples, ["absent", "present", "present", "unknown", "absent", "absent", "absent", "absent"])
    assert brackets["onset"] == {"state": "observed", "lower_seconds": 0, "upper_seconds": 1}
    assert brackets["offset"]["state"] == "unknown"
    assert brackets["offset"]["lower_seconds"] == 2


def test_extent_joins_only_reference_linked_checks_and_keeps_raw_evidence(imported):
    settings, candidate = imported
    replies = [answer(["present"] * 8),
               answer(["absent", "absent", "present", "present", "present", "present", "present", "present"], relation="same_event"),
               answer(["present", "present", "present", "present", "absent", "absent", "absent", "absent"], relation="same_event")]
    with endpoint([(200, extent_envelope(r)) for r in replies]) as (url, calls):
        result = extent.check_candidates(replace(settings, qwen_base_url=url), "a visible action", [candidate])
    assert len(calls) == 3
    assert result["budget"]["frames"] == 24 and result["budget"]["calls"] == 3
    assert result["budget"]["unique_frames"] <= 22
    assert result["stop_reason"] == "event_bounded"
    proposal = result["proposals"][0]
    assert proposal["complete"] is True
    assert proposal["end_seconds"] - proposal["start_seconds"] > 10
    assert proposal["onset"]["state"] == proposal["offset"]["state"] == "observed"
    assert proposal["verified"] is False and proposal["estimate_type"] == "sample-bracket-midpoints"
    assert len(proposal["supporting_check_ids"]) == 3
    seed = result["checks"][0]["verification"]
    for check in result["checks"]:
        v = check["verification"]
        assert len(v["samples"]) == 8
        saved = store.get_verification(settings.database_url, v["id"])
        assert saved["spec"]["task"] == "extent"
        assert saved["spec"]["controller_policy"] == "extent"
        assert saved["response"]["_extent"]["inspection_reason"] == check["reason"]
        assert saved["response"]["_trace"]["prompt_version"] == "source-sample-extent-json-v5"
        assert saved["response"]["_trace"]["status_derivation"] == "new-sample-support-v1"
        assert saved["response"]["_trace"]["query_support_scope"] == "all-input-samples-v1"
        if v["reference"]:
            assert v["reference"]["verification_id"] == seed["id"]
            assert v["result"]["_trace"]["frame_sha256"][v["reference"]["sample_index"]] == v["reference"]["frame_sha256"]
    assert result["complete_video_coverage"] is False
    assert result["supports_absence_or_counts"] is False


@pytest.mark.parametrize("relation", ["different_event", "unknown"])
def test_different_or_uncertain_neighbor_never_extends_seed(imported, relation):
    settings, candidate = imported
    replies = [answer(["present"] * 8), answer(["present"] * 8, relation=relation)]
    with endpoint([(200, extent_envelope(r)) for r in replies]) as (url, calls):
        result = extent.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate], max_checks=2)
    proposal = result["proposals"][0]
    assert not proposal["complete"]
    assert proposal["start_seconds"] >= 10 and proposal["end_seconds"] < 20
    assert len(proposal["supporting_check_ids"]) == 1
    assert result["stop_reason"] == "budget_exhausted" and len(calls) == 2


def test_scope_bounds_and_open_file_edges_do_not_become_observed(imported):
    settings, candidate = imported
    replies = [answer(["present"] * 8)]
    with endpoint([(200, extent_envelope(r)) for r in replies]) as (url, calls):
        result = extent.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate],
                                         start_seconds=10, end_seconds=20)
    assert len(calls) == 1
    assert not result["proposals"][0]["complete"]
    assert result["proposals"][0]["onset"]["state"] == "open"
    assert result["stop_reason"] == "scope_exhausted"


def test_partial_query_is_not_a_complete_event(imported):
    settings, candidate = imported
    reply = answer(["absent", "present", "present", "present", "absent", "absent", "absent", "absent"], support="partial")
    with endpoint([(200, extent_envelope(reply))]) as (url, calls):
        result = extent.check_candidates(replace(settings, qwen_base_url=url), "two required actions", [candidate], max_checks=1)
    assert len(calls) == 1 and not result["proposals"][0]["complete"]
    assert result["proposals"][0]["query_support"] == "partial"


def test_reference_only_all_support_cannot_upgrade_partial_seed_or_complete_event(imported):
    settings, candidate = imported
    replies = [answer(["present"] * 8, support="partial"),
               answer(["absent"] * 7 + ["present"], status="no_match", relation="unknown"),
               answer(["present"] + ["absent"] * 7, status="no_match", relation="unknown")]
    with endpoint([(200, extent_envelope(r)) for r in replies]) as (url, calls):
        result = extent.check_candidates(replace(settings, qwen_base_url=url), "two required actions", [candidate])
    p = result["proposals"][0]
    assert len(calls) == 3 and p["query_support"] == "partial" and not p["complete"]
    assert p["onset"]["state"] == p["offset"]["state"] == "observed"
    assert len(p["supporting_check_ids"]) == 3
    for check in result["checks"][1:]:
        v = check["verification"]
        assert v["result"]["status"] == "no_match" and v["result"]["query_support"] == "all"
        assert v["result"]["intervals"] == []
        saved = store.get_verification(settings.database_url, v["id"])
        assert saved["response"]["query_support"] == "all"
        assert saved["response"]["_trace"]["query_support_scope"] == "all-input-samples-v1"


def test_service_failure_preserves_completed_ids(imported):
    settings, candidate = imported
    with endpoint([(200, extent_envelope(answer(["present"] * 8))), (401, {"error": "test denial"})]) as (url, calls):
        with pytest.raises(VLMError) as error:
            extent.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate])
    assert len(calls) == 2
    ids = error.value.details["completed_evidence_checks"]
    assert len(ids) == 1 and store.get_verification(settings.database_url, ids[0])


def test_no_match_checks_other_candidates_without_claiming_absence(imported):
    settings, candidate = imported
    other = {**candidate, "start_seconds": 0.0, "end_seconds": 10.0}
    reply = answer(["absent"] * 8, status="no_match", support="unknown")
    with endpoint([(200, extent_envelope(reply))]) as (url, calls):
        result = extent.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate, candidate, other])
    assert len(calls) == 2 and result["duplicate_candidates"] == 1
    assert result["status"] == "insufficient_evidence" and result["proposals"] == []


def test_unlocalized_context_support_checks_next_candidate_without_a_false_event(imported):
    settings, candidate = imported
    other = {**candidate, "start_seconds": 0.0, "end_seconds": 10.0}
    replies = [answer(["absent"] * 8, support="all"),
               answer(["unknown"] * 8, status="insufficient_evidence", support="unknown")]
    with endpoint([(200, extent_envelope(r)) for r in replies]) as (url, calls):
        result = extent.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate, other], max_checks=2)
    assert len(calls) == 2 and len(result["checks"]) == 2
    assert result["status"] == "insufficient_evidence" and result["proposals"] == []
    assert result["checks"][1]["candidate"]["start_seconds"] == 0.0
    first = result["checks"][0]["verification"]
    assert first["reference"] is None and first["result"]["intervals"] == []
    assert first["result"]["status"] == "insufficient_evidence"
    saved = store.get_verification(settings.database_url, first["id"])
    assert saved["response"]["sample_support"] == ["absent"] * 8
    assert saved["response"]["query_support"] == "all"
    assert saved["response"]["_trace"]["status_derivation"] == "context-unlocalized-abstention-v2"
    assert saved["response"]["_trace"]["localization_warning"] == "context_support_without_localized_samples"


def test_invalid_source_fails_before_a_model_call(imported):
    settings, candidate = imported
    with pytest.raises(media.MediaError):
        extent.check_candidates(settings, "action", [{**candidate, "source_status": "changed"}])


def test_changed_source_hash_fails_before_a_model_call(imported):
    settings, candidate = imported
    with settings.media_root.joinpath("extent.mp4").open("ab") as video:
        video.write(b"changed")
    with endpoint([(200, extent_envelope(answer(["present"] * 8)))]) as (url, calls):
        with pytest.raises(media.MediaError) as error:
            extent.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate])
    assert error.value.code == "source_changed" and not calls


def test_complete_seed_spends_extra_budget_only_when_requested(imported):
    settings, candidate = imported
    other = {**candidate, "start_seconds": 0.0, "end_seconds": 10.0}
    reply = answer(["absent", "present", "present", "present", "absent", "absent", "absent", "absent"])
    with endpoint([(200, extent_envelope(reply))]) as (url, calls):
        production = extent.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate, other])
    assert len(calls) == 1 and production["stop_reason"] == "event_bounded"
    with endpoint([(200, extent_envelope(reply))]) as (url, calls):
        controlled = extent.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate, other],
                                               max_checks=2, spend_budget=True)
    assert len(calls) == 2 and len(controlled["proposals"]) == 2
    assert controlled["checks"][1]["reason"] == "budget_control_seed"
    assert controlled["checks"][1]["verification"]["reference"] is None
    assert controlled["stop_reason"] == "budget_exhausted"


def test_absent_neighbors_bracket_the_seed_without_merging_another_event(imported):
    settings, candidate = imported
    replies = [answer(["present"] * 8),
               answer(["absent"] * 7 + ["present"], status="no_match", support="unknown", relation="unknown"),
               answer(["present"] + ["absent"] * 7, status="no_match", support="unknown", relation="unknown")]
    with endpoint([(200, extent_envelope(r)) for r in replies]) as (url, calls):
        result = extent.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate])
    p = result["proposals"][0]
    assert len(calls) == 3 and p["complete"]
    assert p["onset"]["lower_seconds"] < 10 < p["onset"]["upper_seconds"]
    assert p["offset"]["lower_seconds"] < 20 < p["offset"]["upper_seconds"]


def test_unknown_neighbor_cannot_close_a_boundary(imported):
    settings, candidate = imported
    replies = [answer(["present"] * 8),
               answer(["unknown"] * 7 + ["present"], status="insufficient_evidence", support="unknown", relation="unknown")]
    with endpoint([(200, extent_envelope(r)) for r in replies]) as (url, calls):
        result = extent.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate], max_checks=2)
    assert len(calls) == 2
    assert not result["proposals"][0]["complete"]
    assert result["proposals"][0]["onset"]["state"] == "open"


def test_separated_positive_runs_are_not_linked_even_when_model_says_same_event(imported):
    settings, candidate = imported
    replies = [answer(["present"] * 8),
               answer(["absent", "present", "present", "absent", "absent", "absent", "absent", "present"], relation="same_event")]
    with endpoint([(200, extent_envelope(r)) for r in replies]) as (url, calls):
        result = extent.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate], max_checks=2)
    p = result["proposals"][0]
    assert len(calls) == 2 and len(p["supporting_check_ids"]) == 1
    assert p["first_present_seconds"] >= 10 and not p["complete"]


def test_uniform_control_keeps_a_known_edge_and_uses_the_same_sampling_recipe(imported):
    settings, candidate = imported
    seed = answer(["absent", "present", "present", "present", "present", "present", "present", "present"])
    before = answer(["absent"] * 7 + ["present"], status="no_match", support="unknown", relation="unknown")
    after = answer(["present"] + ["absent"] * 7, status="no_match", support="unknown", relation="unknown")
    with endpoint([(200, extent_envelope(r)) for r in [seed, before, after]]) as (url, calls):
        uniform = extent.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate], policy="uniform_extent")
    assert len(calls) == 3 and uniform["proposals"][0]["complete"]
    assert uniform["checks"][1]["reason"] == "uniform_before"
    with endpoint([(200, extent_envelope(r)) for r in [seed, after]]) as (url, calls):
        adaptive = extent.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate])
    assert len(calls) == 2 and adaptive["proposals"][0]["complete"]
    assert adaptive["checks"][1]["reason"] == "extent_after"
    assert adaptive["proposals"][0]["onset"] == uniform["proposals"][0]["onset"]
    for output in [uniform, adaptive]:
        assert output["budget"]["frames"] <= 24
        for step in output["checks"][1:]:
            v = step["verification"]
            assert len([s for s in v["samples"] if not s["is_reference"]]) == 7
            assert v["new_end_seconds"] - v["new_start_seconds"] <= 8.75


def test_two_seed_occurrences_remain_separate_and_do_not_claim_complete_query(imported):
    settings, candidate = imported
    reply = answer(["absent", "present", "present", "absent", "absent", "present", "present", "absent"])
    with endpoint([(200, extent_envelope(reply))]) as (url, calls):
        result = extent.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate])
    p = result["proposals"][0]
    assert len(calls) == 1 and len(result["checks"][0]["verification"]["result"]["intervals"]) == 2
    assert not p["complete"] and p["run_count"] == 2
    assert p["end_seconds"] < 15
    assert all(t < 15 for t in p["evidence_points_seconds"])
    assert result["stop_reason"] == "event_unresolved"


@pytest.mark.parametrize("reference_state", ["absent", "unknown"])
def test_negative_neighbor_with_inconsistent_reference_cannot_close_edge(imported, reference_state):
    settings, candidate = imported
    replies = [answer(["present"] * 8),
               answer(["absent"] * 7 + [reference_state], status="no_match", support="unknown", relation="unknown"),
               answer(["present"] + ["absent"] * 7, status="no_match", support="unknown", relation="unknown")]
    with endpoint([(200, extent_envelope(r)) for r in replies]) as (url, calls):
        result = extent.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate])
    p = result["proposals"][0]
    assert len(calls) == 3 and not p["complete"]
    assert p["onset"]["state"] == "open" and p["offset"]["state"] == "observed"
    assert result["checks"][1]["verification"]["id"] in p["unlinked_check_ids"]
    assert len(p["supporting_check_ids"]) == 2
    saved = store.get_verification(settings.database_url, result["checks"][1]["verification"]["id"])
    assert saved["response"]["sample_support"][-1] == reference_state
    assert saved["response"]["anchor_relation"] == "unknown"


def test_inconsistent_reference_preserves_known_edge_and_query_support(imported):
    settings, candidate = imported
    replies = [answer(["absent", "present", "present", "present", "present", "present", "present", "present"], support="partial"),
               answer(["present"] * 7 + ["unknown"], relation="same_event")]
    with endpoint([(200, extent_envelope(r)) for r in replies]) as (url, calls):
        result = extent.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate],
                                         max_checks=2, policy="uniform_extent")
    p = result["proposals"][0]
    assert len(calls) == 2 and p["query_support"] == "partial" and not p["complete"]
    assert p["onset"]["state"] == "observed" and p["onset"]["lower_seconds"] >= 10
    assert p["auxiliary_check_ids"] == [] and len(p["unlinked_check_ids"]) == 1


def test_one_uncertain_positive_sample_does_not_invent_an_interval(imported):
    settings, candidate = imported
    reply = answer(["unknown", "present", "unknown", "absent", "absent", "absent", "absent", "absent"], support="partial")
    with endpoint([(200, extent_envelope(reply))]) as (url, calls):
        result = extent.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate], max_checks=1)
    p = result["proposals"][0]
    assert len(calls) == 1 and p["start_seconds"] is None and p["end_seconds"] is None
    assert len(p["evidence_points_seconds"]) == 1 and not p["complete"]
    assert result["checks"][0]["verification"]["result"]["intervals"] == []


@pytest.mark.parametrize("start,end,scope", [(0, 10, {"end_seconds": 10}), (22, 32, {"start_seconds": 22})])
def test_recording_edges_are_open_without_outside_evidence(imported, start, end, scope):
    settings, candidate = imported
    with endpoint([(200, extent_envelope(answer(["present"] * 8)))]) as (url, calls):
        result = extent.check_candidates(replace(settings, qwen_base_url=url), "action",
                                         [{**candidate, "start_seconds": start, "end_seconds": end}], **scope)
    assert len(calls) == 1 and result["stop_reason"] == "scope_exhausted"
    assert not result["proposals"][0]["complete"]
    assert result["proposals"][0]["onset" if start == 0 else "offset"]["state"] == "open"


def test_dense_packet_can_resolve_both_edges_of_a_short_event():
    seed = {"id": "seed", "recording_id": "one", "samples": [{"source_seconds": t, "is_reference": False} for t in range(10, 18)],
            "result": answer(["unknown", "unknown", "present", "unknown", "unknown", "absent", "absent", "absent"])}
    p = extent._seed(seed)
    stamps = [8.5, 9.5, 10.5, 11.5, 12, 12.5, 13.5, 14.5]
    check = {"id": "dense", "reference": {"sample_index": 4, "source_seconds": 12},
             "samples": [{"source_seconds": t, "is_reference": i == 4} for i, t in enumerate(stamps)],
             "result": answer(["absent", "absent", "present", "present", "present", "present", "absent", "absent"], relation="same_event")}
    assert extent._extend(p, check, "before")
    assert p["complete"] and p["start_seconds"] == 10 and p["end_seconds"] == 13
    assert p["first_present_seconds"] == 10.5 and p["last_present_seconds"] == 12.5


def test_same_event_claim_cannot_bridge_a_previously_observed_absence():
    seed = {"id": "seed", "recording_id": "one", "samples": [{"source_seconds": t, "is_reference": False} for t in range(10, 18)],
            "result": answer(["absent", "present", "present", "unknown", "unknown", "unknown", "absent", "absent"], support="partial")}
    p = extent._seed(seed)
    check = {"id": "later", "reference": {"sample_index": 0, "source_seconds": 11},
             "samples": [{"source_seconds": t, "is_reference": i == 0} for i, t in enumerate(range(11, 19))],
             "result": answer(["present"] * 8, relation="same_event")}
    assert not extent._extend(p, check, "after")
    assert p["query_support"] == "partial" and p["last_present_seconds"] == 12
    assert p["unlinked_check_ids"] == ["later"] and not p["complete"]


def test_uncertain_action_samples_do_not_become_match_intervals(imported):
    settings, candidate = imported
    reply = answer(["unknown"] * 8, status="insufficient_evidence", support="partial")
    with endpoint([(200, extent_envelope(reply))]) as (url, calls):
        result = extent.check_candidates(replace(settings, qwen_base_url=url), "all required actions", [candidate], max_checks=1)
    assert len(calls) == 1 and result["proposals"] == []
    assert result["checks"][0]["verification"]["result"]["sample_support"] == ["unknown"] * 8
    assert result["checks"][0]["verification"]["result"]["intervals"] == []
