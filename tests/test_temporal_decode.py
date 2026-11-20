import math

import pytest

from video_search.temporal_decode import _project, decode


def windows(scores, step=1):
    return [{"start_seconds": i * step, "end_seconds": (i + 1) * step, "rerank_score": score}
            for i, score in enumerate(scores)]


def test_sustained_evidence_beats_an_isolated_peak_and_keeps_inputs():
    evidence = windows([0, 6, 0, 0, 0, 0, 3, 3, 3, 0, 0, 0])
    before = [dict(window) for window in evidence]
    result = decode(evidence, 12)
    assert result[0]["start_seconds"] == 6
    assert result[0]["end_seconds"] == 9
    assert result[0]["score"] == pytest.approx(5.25)
    assert result[0]["boundary_kind"] == "estimated"
    assert result[0]["checked_by_model"] is False
    assert result[0]["verified"] is False
    assert evidence == before


def test_overlap_projection_uses_duration_not_number_of_windows():
    evidence = [{"start_seconds": 0, "end_seconds": 2, "rerank_score": 0},
                {"start_seconds": .5, "end_seconds": 2, "rerank_score": 6}]
    curve, widths = _project(evidence, 2, 1, "rerank_score")
    assert curve == pytest.approx([2, 3])
    assert widths == [1, 1]
    assert decode(list(reversed(evidence)), 2) == decode(evidence, 2)


def test_fractional_final_cell_is_scored_by_its_true_width():
    evidence = [{"start_seconds": 0, "end_seconds": 2, "rerank_score": 0},
                {"start_seconds": 2, "end_seconds": 2.25, "rerank_score": 4}]
    result = decode(evidence, 2.25)
    assert result[0]["start_seconds"] == 2
    assert result[0]["end_seconds"] == 2.25
    assert result[0]["score"] == pytest.approx(8 / 9)


@pytest.mark.parametrize("scores", [[3], [3, 3, 3], [-4, -4, -4], [0, 0, 0]])
@pytest.mark.parametrize("sigma,background", [(0, 0), (1, 0), (0, .5), (1, 1)])
def test_flat_evidence_abstains_instead_of_inventing_an_event(scores, sigma, background):
    assert decode(windows(scores), len(scores), sigma_seconds=sigma, background_weight=background) == []


def test_gaussian_smoothing_changes_boundaries_without_crossing_source():
    evidence = windows([0, 0, 0, 1, 0, 0, 0])
    result = decode(evidence, 7, sigma_seconds=1)
    assert len(result) == 1
    assert 0 <= result[0]["start_seconds"] < result[0]["end_seconds"] <= 7
    assert result[0]["start_seconds"] == 2
    assert result[0]["end_seconds"] == 5


def test_background_contrast_retains_a_relative_score_not_a_probability():
    result = decode(windows([0, 2, 0, 0, 0]), 5, background_weight=.5)
    assert result[0]["start_seconds"] == 1
    assert result[0]["end_seconds"] == 2
    assert result[0]["score"] > 1


def test_equal_disjoint_peaks_choose_the_first_deterministically():
    result = decode(windows([0, 1, 0, 1, 0]), 5)
    assert result[0]["start_seconds"] == 1
    assert result[0]["end_seconds"] == 4
    isolated = decode(windows([1, 0, 0, 1]), 4)
    assert isolated[0]["start_seconds"] == 0
    assert isolated[0]["end_seconds"] == 1


@pytest.mark.parametrize("evidence,duration", [
    ([], 2),
    ([{"start_seconds": .1, "end_seconds": 2, "rerank_score": 1}], 2),
    ([{"start_seconds": 0, "end_seconds": .9, "rerank_score": 1},
      {"start_seconds": 1, "end_seconds": 2, "rerank_score": 2}], 2),
    ([{"start_seconds": 0, "end_seconds": 1.9, "rerank_score": 1}], 2),
    ([{"start_seconds": 0, "end_seconds": 2, "rerank_score": 1}] * 2, 2),
    ([{"start_seconds": -1, "end_seconds": 2, "rerank_score": 1}], 2),
    ([{"start_seconds": 0, "end_seconds": 3, "rerank_score": 1}], 2),
    ([{"start_seconds": 1, "end_seconds": 1, "rerank_score": 1}], 2),
    ([{"start_seconds": 0, "end_seconds": 2}], 2),
    ([{"start_seconds": 0, "end_seconds": 2, "rerank_score": math.inf}], 2),
    ([{"start_seconds": 0, "end_seconds": 2, "rerank_score": math.nan}], 2),
    ([{"start_seconds": 0, "end_seconds": 2, "rerank_score": True}], 2),
])
def test_invalid_or_incomplete_evidence_is_an_error(evidence, duration):
    with pytest.raises(ValueError):
        decode(evidence, duration)


@pytest.mark.parametrize("kwargs", [{"step_seconds": 0}, {"step_seconds": -1},
    {"step_seconds": math.nan}, {"step_seconds": True}, {"step_seconds": .000001},
    {"sigma_seconds": -1}, {"sigma_seconds": math.inf}, {"sigma_seconds": 100},
    {"background_weight": -.1}, {"background_weight": 1.1}, {"score_field": ""}])
def test_invalid_or_excessive_grid_settings_are_errors(kwargs):
    with pytest.raises(ValueError):
        decode(windows([0, 1]), 2, **kwargs)


def test_small_step_and_custom_score_field():
    evidence = [{"start_seconds": 0, "end_seconds": .5, "visual": -.2},
                {"start_seconds": .5, "end_seconds": 1, "visual": .4}]
    result = decode(evidence, 1, score_field="visual", step_seconds=.25)
    assert result[0]["start_seconds"] == .5
    assert result[0]["end_seconds"] == 1
