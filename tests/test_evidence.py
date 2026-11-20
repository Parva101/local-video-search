from dataclasses import replace

import pytest

from video_search import evidence, media, store
from video_search.config import Settings
from video_search.vlm import VLMError
from video_search.worker import process_one
from test_vlm import endpoint, envelope


NO_MATCH = {"status": "no_match", "intervals": [], "observation": "No matching action is visible."}
UNCERTAIN = {"status": "insufficient_evidence", "intervals": [], "observation": "The frame gaps hide the action."}


def candidate(recording_id, start=0, end=.8):
    return {"recording_id": recording_id, "start_seconds": start, "end_seconds": end,
            "source_status": "available"}


@pytest.fixture
def imported(database_url, video_file):
    settings = Settings(database_url, video_file.parent)
    size, mtime = media.fingerprint(video_file)
    store.enqueue(database_url, video_file.name, size, mtime)
    assert process_one(settings)
    recording_id = str(store.list_recordings(database_url)[0]["id"])
    return settings, recording_id


def test_adaptive_defers_overlap_but_retains_the_candidate():
    first, overlap, distant = candidate("one", 0, 10), candidate("one", 8, 18), candidate("one", 20, 30)
    assert evidence.next_candidate([overlap, distant], [first]) == 1
    assert evidence.next_candidate([overlap], [first, distant]) == 0
    assert evidence.next_candidate([candidate("two", 0, 10), distant], [first]) == 0


def test_refinement_targets_largest_actual_frame_gap():
    checked = {"inspection_start_seconds": 2, "inspection_end_seconds": 10,
               "samples": [{"source_seconds": value} for value in (2, 3, 4, 5, 9)]}
    assert evidence.refinement_interval(checked) == (6, 10)


def test_distinct_candidate_recovery_and_equal_budget(imported):
    settings, recording_id = imported
    candidates = [candidate(recording_id, 0, .8), candidate(recording_id, .4, 1.2),
                  candidate(recording_id, 1.2, 2)]
    match = {"status": "match", "intervals": [{"start_seconds": 1.3, "end_seconds": 1.8}],
             "observation": "The action is visible."}
    with endpoint([(200, envelope(NO_MATCH)), (200, envelope(NO_MATCH))]) as (url, calls):
        baseline = evidence.check_candidates(replace(settings, qwen_base_url=url), "action", candidates,
                                             max_checks=2, policy="ranked")
        assert len(calls) == 2
    with endpoint([(200, envelope(NO_MATCH)), (200, envelope(match))]) as (url, calls):
        result = evidence.check_candidates(replace(settings, qwen_base_url=url), "action", candidates,
                                           max_checks=2)
        assert len(calls) == 2
    assert baseline["status"] == "insufficient_evidence"
    assert baseline["stop_reason"] == "budget_exhausted"
    assert result["status"] == "match" and result["stop_reason"] == "match_found"
    assert result["checks"][1]["candidate"]["start_seconds"] == 1.2
    assert baseline["budget"]["frames"] == result["budget"]["frames"] == 16
    assert result["budget"]["http_attempts"] == 2
    assert result["budget"]["sent_frame_slots"] == 16
    assert result["budget"]["unique_inspected_seconds"] == pytest.approx(1.6)
    assert result["complete_video_coverage"] is False
    assert result["supports_absence_or_counts"] is False
    for step in result["checks"]:
        saved = store.get_verification(settings.database_url, step["verification"]["id"])
        assert saved["response"]["_trace"]["frame_sha256"]


def test_refinement_follows_exploration_and_stays_in_scope(imported):
    settings, recording_id = imported
    candidates = [candidate(recording_id, 0, .8), candidate(recording_id, 1.2, 2)]
    with endpoint([(200, envelope(UNCERTAIN)), (200, envelope(NO_MATCH)),
                   (200, envelope(NO_MATCH))]) as (url, calls):
        result = evidence.check_candidates(replace(settings, qwen_base_url=url), "action", candidates,
                                           start_seconds=.2, end_seconds=1.8)
    assert len(calls) == result["budget"]["calls"] == 3
    assert [step["reason"] for step in result["checks"]] == ["ranked_candidate", "distinct_candidate", "dense_refinement"]
    assert result["checks"][1]["verification"]["inspection_start_seconds"] == 1.2
    refined = result["checks"][2]["verification"]
    assert .2 <= refined["inspection_start_seconds"] < refined["inspection_end_seconds"] <= .8
    assert refined["inspection_end_seconds"] - refined["inspection_start_seconds"] == pytest.approx(.3)
    assert all(.2 <= sample["source_seconds"] < 1.8 for step in result["checks"] for sample in step["verification"]["samples"])
    assert result["budget"]["frames"] == 24
    assert result["budget"]["inspected_seconds"] == pytest.approx(1.5)
    assert result["budget"]["unique_inspected_seconds"] == pytest.approx(1.2)


def test_duplicate_checks_are_not_repeated_and_no_match_is_not_absence(imported):
    settings, recording_id = imported
    item = candidate(recording_id)
    with endpoint([(200, envelope(NO_MATCH))]) as (url, calls):
        result = evidence.check_candidates(replace(settings, qwen_base_url=url), "action", [item, item])
    assert len(calls) == 1
    assert result["stop_reason"] == "candidates_exhausted"
    assert result["status"] == "insufficient_evidence"
    assert result["duplicate_candidates"] == 1


def test_empty_candidates_do_not_call_a_model(imported):
    settings, _ = imported
    result = evidence.check_candidates(settings, "action", [])
    assert result["checks"] == [] and result["budget"]["calls"] == 0
    assert result["stop_reason"] == "candidates_exhausted"


@pytest.mark.parametrize("options", [{"max_checks": 0}, {"max_checks": True}, {"max_checks": 13},
                                     {"policy": "unknown"}, {"start_seconds": float("nan")},
                                     {"start_seconds": 1, "end_seconds": .5}])
def test_invalid_options_fail_before_calls(imported, options):
    settings, recording_id = imported
    with pytest.raises(ValueError):
        evidence.check_candidates(settings, "action", [candidate(recording_id)], **options)


@pytest.mark.parametrize("start,end", [(0, 3), (-1, .5), (.5, .5), (float("nan"), 1)])
def test_invalid_candidates_fail_before_calls(imported, start, end):
    settings, recording_id = imported
    with pytest.raises(ValueError):
        evidence.check_candidates(settings, "action", [candidate(recording_id, start, end)])


def test_unavailable_source_is_an_error(imported):
    settings, recording_id = imported
    item = {**candidate(recording_id), "source_status": "changed"}
    with pytest.raises(media.MediaError, match="unavailable"):
        evidence.check_candidates(settings, "action", [item])


def test_source_change_is_not_silently_skipped(imported, video_file):
    settings, recording_id = imported
    with video_file.open("ab") as file:
        file.write(b"changed")
    with endpoint([(200, envelope(NO_MATCH))]) as (url, calls):
        with pytest.raises(media.MediaError) as caught:
            evidence.check_candidates(replace(settings, qwen_base_url=url), "action", [candidate(recording_id)])
    assert caught.value.code == "source_changed" and calls == []


def test_service_error_preserves_completed_check_ids(imported):
    settings, recording_id = imported
    with endpoint([(200, envelope(NO_MATCH)), (401, {"error": "test denial"})]) as (url, calls):
        with pytest.raises(VLMError) as caught:
            evidence.check_candidates(replace(settings, qwen_base_url=url), "action",
                                      [candidate(recording_id), candidate(recording_id, 1.2, 2)])
    assert len(calls) == 2
    assert len(caught.value.details["completed_evidence_checks"]) == 1
    saved_id = caught.value.details["completed_evidence_checks"][0]
    assert store.get_verification(settings.database_url, saved_id) is not None
