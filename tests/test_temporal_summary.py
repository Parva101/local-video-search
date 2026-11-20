import copy
import importlib.util
from pathlib import Path

import pytest

from video_search.temporal_training import score_predictions


spec = importlib.util.spec_from_file_location("temporal_summary", Path(__file__).parents[1] / "scripts/summarize_temporal_heads.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    rows = [{"qid": 1, "vid": "source", "duration": 4, "relevant_windows": [[1, 2]]}]
    predictions = [{"qid": 1, "vid": "source", "pred_relevant_windows": [[1, 2, .9]]}]
    report = {**{key: "a" * 64 for key in (*module.IDENTITIES, "checkpoint_sha256")},
              "predictions": predictions, "metrics": score_predictions(rows, predictions),
              "author_checkpoint": True, "evaluation_batch_size": 4}
    matched = {**report, "evaluation_batch_size": 32}
    return rows, report, matched


def test_native_reference_is_separate_and_aggregate_only():
    rows, report, matched = fixture()
    value = module.native_reference(rows, report, matched)
    assert value["metrics_percent"]["R1@0.5"] == 100
    assert value["evaluation_batch_size"] == 4
    assert "predictions" not in value


@pytest.mark.parametrize("change", ["hash", "batch", "metric", "reference"])
def test_native_reference_rejects_mixed_input_or_unverified_metrics(change):
    rows, report, matched = fixture()
    report = copy.deepcopy(report)
    if change == "hash":
        report["checkpoint_sha256"] = "b" * 64
    elif change == "batch":
        report["evaluation_batch_size"] = 32
    elif change == "metric":
        report["metrics"]["R1@0.5"] = .5
    else:
        report["author_checkpoint"] = False
    with pytest.raises(ValueError):
        module.native_reference(rows, report, matched)
