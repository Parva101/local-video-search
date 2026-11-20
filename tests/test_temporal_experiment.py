import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location("compare_temporal", Path(__file__).parents[1] / "scripts/compare_temporal_decoders.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def inputs(tmp_path, split, video):
    manifest = {"name": "synthetic", "split": split, "provenance": "unit fixture",
                "videos": {video: {"duration_seconds": 3}},
                "queries": [{"id": split, "query": "action", "scope_video_ids": [video],
                             "targets": [{"video_id": video, "start_seconds": 1, "end_seconds": 2}]}]}
    path = tmp_path / (split + ".json")
    module.save_new(path, manifest)
    cache = tmp_path / split
    candidates = [{"start_seconds": i, "end_seconds": i + 1, "rerank_score": value,
                   "source_path": video + ".mp4", "recording_id": "recording", "source_status": "available"}
                  for i, value in enumerate([0, 2, 0])]
    item = {"request": {"query": "action", "recording_ids": ["recording"]},
            "raw": {"results": candidates}, "reranked": {"results": [candidates[1], candidates[0], candidates[2]]}}
    module.save_new(cache / (hashlib.sha256(json.dumps(split).encode()).hexdigest() + ".json"), item)
    return path, cache


def test_train_freeze_then_disjoint_complete_test_no_raw_public_labels(tmp_path):
    train, train_cache = inputs(tmp_path, "train", "a")
    freeze = tmp_path / "freeze.json"
    assert module.develop(train, train_cache, freeze)["query_count"] == 1
    test, test_cache = inputs(tmp_path, "test", "b")
    result = module.run_evaluation(test, test_cache, freeze, tmp_path / "result")
    assert result["methods"]["curve_selected"]["R1_IoU_0.5"] == 1
    assert result["new_model_calls"] == 0
    assert "per_query" not in result and "reports" not in result
    with pytest.raises(FileExistsError):
        module.run_evaluation(test, test_cache, freeze, tmp_path / "result")


def test_rejects_test_development_and_overlapping_sources(tmp_path):
    train, cache = inputs(tmp_path, "train", "a")
    freeze = tmp_path / "freeze.json"
    module.develop(train, cache, freeze)
    test, test_cache = inputs(tmp_path, "test", "a")
    with pytest.raises(ValueError, match="training development"):
        module.develop(test, test_cache, tmp_path / "invalid.json")
    with pytest.raises(ValueError, match="source-disjoint"):
        module.run_evaluation(test, test_cache, freeze, tmp_path / "invalid")


def test_rejects_changed_frozen_code(tmp_path):
    train, cache = inputs(tmp_path, "train", "a")
    freeze = tmp_path / "freeze.json"
    module.develop(train, cache, freeze)
    value = json.loads(freeze.read_bytes())
    value["sources"]["decoder"] = "0" * 64
    changed = tmp_path / "changed.json"
    module.save_new(changed, value)
    test, test_cache = inputs(tmp_path, "test", "b")
    with pytest.raises(ValueError, match="code changed"):
        module.run_evaluation(test, test_cache, changed, tmp_path / "invalid")


def test_accepts_actual_pilot_split_names(tmp_path):
    train, cache = inputs(tmp_path, "development", "a")
    freeze = tmp_path / "freeze.json"
    module.develop(train, cache, freeze)
    test, test_cache = inputs(tmp_path, "held-out-pilot", "b")
    assert module.run_evaluation(test, test_cache, freeze, tmp_path / "result")["query_count"] == 1
