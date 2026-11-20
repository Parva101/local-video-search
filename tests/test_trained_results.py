import copy
import json

import pytest

from video_search.temporal_training import score_predictions
from video_search.trained_results import METRICS, SEEDS, summarize


def fixtures():
    rows = [{"qid": i, "vid": f"private-source-{i // 2}", "query": "private-query-text",
             "duration": 4., "relevant_windows": [[1., 2.]]} for i in range(4)]
    reports = {}
    names = [f"{variant}-{seed}" for seed in SEEDS for variant in ("baseline", "quality")]
    for index, name in enumerate(names + ["author-reference"]):
        hit = name.startswith("quality") or name == "author-reference"
        predicted = [{"qid": row["qid"], "vid": row["vid"],
                      "pred_relevant_windows": [[1., 2., .9] if hit else [2., 3., .9]]} for row in rows]
        reports[name] = {**{key: "a" * 64 for key in ("metadata_sha256", "features_sha256", "training_driver_sha256", "driver_sha256")},
                         "checkpoint_sha256": f"{index + 1:064x}", "author_checkpoint": name == "author-reference",
                         "evaluation_batch_size": 32,
                         "metrics": score_predictions(rows, predicted), "predictions": predicted}
    return rows, reports


def test_exact_constant_gain_bootstrap_and_private_aggregate():
    rows, reports = fixtures()
    before = copy.deepcopy(reports)
    result = summarize(rows, reports, bootstrap_repetitions=50)
    assert result["query_count"] == 4 and result["source_video_count"] == 2
    assert result["report_count"] == 7 and result["seed_pairs"] == 3
    assert result["methods"]["quality"]["mean_percent"] == {key: 100. for key in METRICS}
    assert result["quality_minus_baseline"]["ci95_percentage_points"] == {key: [100., 100.] for key in METRICS}
    assert all(v == 0 for v in result["methods"]["quality"]["sample_standard_deviation_percentage_points"].values())
    encoded = json.dumps(result)
    assert not any(text in encoded for text in ("private-source", "private-query-text", "predictions", '"qid"'))
    assert reports == before


def test_point_top1_stays_zero_and_is_not_promoted():
    rows, reports = fixtures()
    for seed in SEEDS:
        report = reports[f"quality-{seed}"]
        for prediction in report["predictions"]:
            prediction["pred_relevant_windows"] = [[1., 1., .9], [1., 2., .8]]
        report["metrics"] = score_predictions(rows, report["predictions"])
    result = summarize(rows, reports, bootstrap_repetitions=10)
    assert result["methods"]["quality"]["mean_percent"] == {key: 0. for key in METRICS}


@pytest.mark.parametrize("change", ["missing_report", "missing_query", "wrong_order", "wrong_video", "metadata_hash",
                                   "driver_hash", "duplicate_checkpoint", "reference_flag", "saved_metric",
                                   "missing_hash", "batch_size"])
def test_rejects_incomplete_or_mixed_results(change):
    rows, reports = fixtures()
    target = reports["quality-2018"]
    if change == "missing_report":
        reports.pop("baseline-2020")
    elif change == "missing_query":
        target["predictions"].pop()
    elif change == "wrong_order":
        target["predictions"].reverse()
    elif change == "wrong_video":
        target["predictions"][0]["vid"] = "another-source"
    elif change == "metadata_hash":
        target["metadata_sha256"] = "b" * 64
    elif change == "driver_hash":
        target["training_driver_sha256"] = "b" * 64
    elif change == "duplicate_checkpoint":
        target["checkpoint_sha256"] = reports["baseline-2018"]["checkpoint_sha256"]
    elif change == "reference_flag":
        target["author_checkpoint"] = True
    elif change == "saved_metric":
        target["metrics"]["R1@0.5"] = .5
    elif change == "missing_hash":
        reports["baseline-2018"].pop("metadata_sha256")
    elif change == "batch_size":
        reports["author-reference"]["evaluation_batch_size"] = 4
    with pytest.raises(ValueError):
        summarize(rows, reports, bootstrap_repetitions=10)


def test_rejects_duplicate_target_ids_and_nonfinite_targets():
    rows, reports = fixtures()
    rows[1]["qid"] = rows[0]["qid"]
    with pytest.raises(ValueError, match="unique IDs"):
        summarize(rows, reports)
    rows, reports = fixtures()
    rows[0]["relevant_windows"] = [[0, float("nan")]]
    with pytest.raises(ValueError, match="Target interval"):
        summarize(rows, reports)


def test_repeatable_seed_video_resampling_with_nonconstant_effect():
    rows, reports = fixtures()
    for index, seed in enumerate(SEEDS):
        report = reports[f"quality-{seed}"]
        report["predictions"][index]["pred_relevant_windows"] = []
        report["metrics"] = score_predictions(rows, report["predictions"])
    first = summarize(rows, reports, bootstrap_repetitions=40)
    assert first == summarize(rows, reports, bootstrap_repetitions=40)
    interval = first["quality_minus_baseline"]["ci95_percentage_points"]["R1@0.5"]
    assert interval[0] < 75 < interval[1]
