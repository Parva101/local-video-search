import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from video_search.evaluation import evaluate, qvhighlights_rows, search_requests, temporal_iou


def manifest():
    return {"name": "test", "split": "development", "provenance": "synthetic test labels",
            "videos": {"one": {"duration_seconds": 30}, "two": {"duration_seconds": 30}},
            "queries": [{"id": "q1", "query": "open drawer", "scope_video_ids": ["one"],
                         "targets": [{"video_id": "one", "start_seconds": 0, "end_seconds": 10},
                                     {"video_id": "one", "start_seconds": 20, "end_seconds": 30}]}]}


def prediction(video="one", start=0, end=10):
    return {"video_id": video, "start_seconds": start, "end_seconds": end, "score": 1.0}


def test_metrics_distinguish_one_hit_all_targets_and_wrong_video():
    report = evaluate(manifest(), [{"query_id": "q1", "candidates": [prediction("two"), prediction()]}], ks=(1, 2))
    assert report["metrics"]["R@1/IoU=0.5"] == 0
    assert report["metrics"]["R@2/IoU=0.5"] == 1
    assert report["metrics"]["target_coverage@2/IoU=0.5"] == .5
    assert report["metrics"]["all_targets@2/IoU=0.5"] == 0
    assert report["counts"]["positive_queries"] == 1


def test_exact_threshold_and_top_k_are_inclusive():
    assert temporal_iou((0, 10), (0, 20)) == .5
    report = evaluate(manifest(), [{"query_id": "q1", "candidates": [prediction(end=20), prediction(start=20, end=30)]}], ks=(1, 2))
    assert report["metrics"]["R@1/IoU=0.5"] == 1
    assert report["metrics"]["R@1/IoU=0.7"] == 0
    assert report["metrics"]["all_targets@2/IoU=0.5"] == 1


def test_mean_top1_iou_includes_misses_and_keeps_reference_scale_clear():
    data = manifest()
    data["queries"].append({**copy.deepcopy(data["queries"][0]), "id": "q2"})
    report = evaluate(data, [{"query_id": "q1", "candidates": [prediction(end=20)]},
                             {"query_id": "q2", "candidates": []}])
    assert report["mean_top1_iou"] == .25
    assert report["per_query"][0]["top1_iou"] == .5
    assert report["per_query"][1]["top1_iou"] == 0


def test_reference_annotation_bounds_do_not_relax_prediction_bounds():
    data = manifest()
    data["videos"]["one"].update(duration_seconds=29.9, annotation_duration_seconds=30)
    report = evaluate(data, [{"query_id": "q1", "candidates": [prediction()]}])
    assert report["counts"]["queries"] == 1
    with pytest.raises(ValueError):
        evaluate(data, [{"query_id": "q1", "candidates": [prediction(start=20, end=30)]}])


def test_negative_abstention_is_separate_from_positive_recall():
    data = manifest()
    data["queries"].append({"id": "negative", "query": "an absent event", "scope_video_ids": ["one"], "targets": []})
    report = evaluate(data, [{"query_id": "q1", "candidates": []}, {"query_id": "negative", "candidates": []}])
    assert report["metrics"]["R@1/IoU=0.5"] == 0
    assert report["negative_abstention_rate"] == 1
    assert report["counts"]["negative_queries"] == 1
    assert report["cost"]["calls_total"] is None


@pytest.mark.parametrize("predictions", [[], [{"query_id": "other", "candidates": []}],
                                         [{"query_id": "q1", "candidates": []}] * 2])
def test_prediction_ids_must_match_exactly(predictions):
    with pytest.raises(ValueError):
        evaluate(manifest(), predictions)


@pytest.mark.parametrize("field,value", [("start_seconds", float("nan")), ("end_seconds", float("inf")),
                                         ("end_seconds", 31), ("end_seconds", 0), ("score", float("nan")),
                                         ("video_id", "unknown")])
def test_invalid_predictions_are_not_silently_dropped(field, value):
    candidate = prediction()
    candidate[field] = value
    with pytest.raises(ValueError):
        evaluate(manifest(), [{"query_id": "q1", "candidates": [candidate]}])


def test_frozen_labels_are_not_sent_to_search_and_corpus_is_explicit():
    data = manifest()
    before = copy.deepcopy(data)
    requests = search_requests(data, {"one": "id1", "two": "id2"}, "description", 5, "supplied_video")
    assert requests == [("q1", {"query": "open drawer", "path": "description", "limit": 5, "recording_ids": ["id1"]})]
    corpus = search_requests(data, {"one": "id1", "two": "id2"}, "visual", 5, "corpus")
    assert corpus[0][1]["recording_ids"] == ["id1", "id2"]
    assert data == before
    with pytest.raises(ValueError, match="mapping"):
        search_requests(data, {"one": "id1"}, "description", 5, "corpus")


def test_qv_export_rejects_wrong_video_instead_of_dropping_it():
    data = manifest()
    rows = qvhighlights_rows(data, [{"query_id": "q1", "candidates": [prediction()]}])
    assert rows == [{"qid": "q1", "vid": "one", "pred_relevant_windows": [[0, 10, 1.0]]}]
    with pytest.raises(ValueError, match="supplied video"):
        qvhighlights_rows(data, [{"query_id": "q1", "candidates": [prediction("two")]}])


def test_public_example_retains_official_label_and_development_warning():
    data = json.loads((Path(__file__).parents[1] / "evaluation/qvhighlights-public-example.json").read_text())
    query = data["queries"][0]
    assert query["id"] == 8056
    assert query["query"] == "Chef makes pizza and cuts it up."
    assert query["targets"] == [{"video_id": "RoripwjYFp8_60.0_210.0", "start_seconds": 106, "end_seconds": 122}]
    assert data["split"] == "public-example-development"
    assert "not a benchmark" in data["purpose"].lower()


def test_public_example_uses_exact_media_duration_without_relaxing_bounds():
    data = json.loads((Path(__file__).parents[1] / "evaluation/qvhighlights-public-example.json").read_text())
    video_id = "RoripwjYFp8_60.0_210.0"
    candidate = prediction(video_id, 144, 150.016533)
    report = evaluate(data, [{"query_id": 8056, "candidates": [candidate]}])
    assert report["counts"]["queries"] == 1
    assert data["videos"][video_id]["duration_seconds"] == 150.016533
    assert data["videos"][video_id]["annotation_duration_seconds"] == 150
    assert data["videos"][video_id]["sha256"] == "e847dbe79219afc6d70225117684a7e03563e1580b6f455ece13f89747cb5a50"
    candidate["end_seconds"] = 150.1
    with pytest.raises(ValueError, match="inside the video"):
        evaluate(data, [{"query_id": 8056, "candidates": [candidate]}])


@pytest.mark.parametrize("rerank", [False, True])
def test_cli_collects_real_http_response_retries_and_exports_without_labels(tmp_path, rerank):
    from test_vlm import endpoint

    data = manifest()
    data["videos"].pop("two")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(data))
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({"one": "local-id"}))
    output, exported = tmp_path / "run.json", tmp_path / "submission.jsonl"
    response = {"results": [{"recording_id": "local-id", "start_seconds": 0, "end_seconds": 10, "source_status": "available"}],
                "coverage": {"ready_windows": 3, "total_windows": 3, "ready_recordings": 1, "total_recordings": 1}}
    script = Path(__file__).parents[1] / "scripts/evaluate_retrieval.py"
    with endpoint([(503, {"error": "temporary"}), (200, response)]) as (url, history):
        run = subprocess.run([sys.executable, str(script), "--manifest", str(manifest_path), "--recording-map", str(mapping),
                              "--output", str(output), "--qv-export", str(exported), "--api", url.removesuffix("/v1"),
                              *(["--rerank"] if rerank else [])],
                             capture_output=True, text=True, timeout=20)
    assert run.returncode == 0, run.stderr
    assert len(history) == 2
    assert history[0]["path"] == "/search"
    expected_request = {"query": "open drawer", "path": "description", "limit": 10, "recording_ids": ["local-id"]}
    if rerank:
        expected_request["rerank"] = True
    assert history[0]["body"] == expected_request
    saved = json.loads(output.read_text())
    assert saved["rerank"] is rerank
    assert json.loads(run.stdout)["rerank"] is rerank
    assert saved["report"]["metrics"]["R@1/IoU=0.5"] == 1
    assert saved["responses"][0]["request_id"] == "upstream-test-id"
    assert json.loads(exported.read_text())["pred_relevant_windows"] == [[0, 10, 1.0]]


@pytest.mark.parametrize("path,source,error", [
    ("visual", "--recording-map", "--rerank requires --path description"),
    ("hybrid", "--recording-map", "--rerank requires --path description"),
    ("description", "--predictions", "--rerank requires live search with --recording-map"),
])
def test_cli_rejects_invalid_rerank_options_before_reading_files(tmp_path, path, source, error):
    script = Path(__file__).parents[1] / "scripts/evaluate_retrieval.py"
    output = tmp_path / "run.json"
    run = subprocess.run([sys.executable, str(script), "--manifest", str(tmp_path / "not-read.json"),
                          source, str(tmp_path / "not-read-map.json"), "--path", path, "--rerank",
                          "--output", str(output)], capture_output=True, text=True, timeout=20)
    assert run.returncode != 0
    assert error in run.stderr
    assert not output.exists()


def test_cli_rejects_incomplete_index_without_writing_score(tmp_path):
    from test_vlm import endpoint

    data = manifest()
    data["videos"].pop("two")
    manifest_path, mapping, output = tmp_path / "manifest.json", tmp_path / "mapping.json", tmp_path / "run.json"
    manifest_path.write_text(json.dumps(data))
    mapping.write_text(json.dumps({"one": "local-id"}))
    response = {"results": [], "coverage": {"ready_windows": 0, "total_windows": 3, "ready_recordings": 0, "total_recordings": 1}}
    script = Path(__file__).parents[1] / "scripts/evaluate_retrieval.py"
    with endpoint([(200, response)]) as (url, history):
        run = subprocess.run([sys.executable, str(script), "--manifest", str(manifest_path), "--recording-map", str(mapping),
                              "--output", str(output), "--api", url.removesuffix("/v1")], capture_output=True, text=True, timeout=20)
    assert run.returncode != 0
    assert "Incomplete index coverage" in run.stderr
    assert not output.exists()


@pytest.mark.parametrize("source_status", ["changed", "missing", None])
def test_cli_rejects_unavailable_or_unchecked_sources_without_writing_score(tmp_path, source_status):
    from test_vlm import endpoint

    data = manifest()
    data["videos"].pop("two")
    manifest_path, mapping, output = tmp_path / "manifest.json", tmp_path / "mapping.json", tmp_path / "run.json"
    manifest_path.write_text(json.dumps(data))
    mapping.write_text(json.dumps({"one": "local-id"}))
    candidate = {"recording_id": "local-id", "start_seconds": 0, "end_seconds": 10}
    if source_status is not None:
        candidate["source_status"] = source_status
    response = {"results": [candidate],
                "coverage": {"ready_windows": 3, "total_windows": 3, "ready_recordings": 1, "total_recordings": 1}}
    script = Path(__file__).parents[1] / "scripts/evaluate_retrieval.py"
    with endpoint([(200, response)]) as (url, history):
        run = subprocess.run([sys.executable, str(script), "--manifest", str(manifest_path), "--recording-map", str(mapping),
                              "--output", str(output), "--api", url.removesuffix("/v1")], capture_output=True, text=True, timeout=20)
    assert run.returncode != 0
    assert "Source is not available" in run.stderr
    assert len(history) == 1
    assert not output.exists()


def test_cli_validates_manifest_for_saved_predictions(tmp_path):
    data = manifest()
    del data["provenance"]
    manifest_path, predictions, output = tmp_path / "manifest.json", tmp_path / "predictions.json", tmp_path / "run.json"
    manifest_path.write_text(json.dumps(data))
    predictions.write_text(json.dumps([{"query_id": "q1", "candidates": []}]))
    script = Path(__file__).parents[1] / "scripts/evaluate_retrieval.py"
    run = subprocess.run([sys.executable, str(script), "--manifest", str(manifest_path), "--predictions", str(predictions),
                          "--output", str(output)], capture_output=True, text=True, timeout=20)
    assert run.returncode != 0
    assert "Manifest requires provenance" in run.stderr
    assert not output.exists()
