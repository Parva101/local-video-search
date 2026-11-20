import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from psycopg import sql
import pytest

from video_search import store
from video_search.benchmark_run import CONDITIONS, DEVELOPMENT_CONDITIONS, DEVELOPMENT_CHECKS, EVALUATION_CHECKS, POINT_FREEZE, Pilot, RunError, _digest, _save, load_data, validate_context_cache_change
from video_search.config import Settings
from test_vlm import endpoint, envelope


@pytest.fixture
def pilot_data(tmp_path, video_file):
    root = tmp_path / "private-pilot"
    media = root / "media"
    media.mkdir(parents=True)
    shutil.copyfile(video_file, media / "red.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=10:d=2",
                    "-c:v", "mpeg4", "-y", str(media / "blue.mp4")], check=True, capture_output=True)
    for split, video in [("train", "red"), ("test", "blue")]:
        source = media / (video + ".mp4")
        document = {"name": "synthetic-pilot", "split": split, "provenance": "Synthetic generated media; no real data",
                    "videos": {video: {"duration_seconds": 2, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                                       "path": "media/" + source.name}},
                    "queries": [{"id": split + "-query", "query": "a colored image", "scope_video_ids": [video],
                                 "targets": [{"video_id": video, "start_seconds": .2, "end_seconds": 1.8}]}]}
        (root / f"{split}.manifest.json").write_text(json.dumps(document))
    (root / "provenance.json").write_text(json.dumps({"media_bytes": sum(p.stat().st_size for p in media.iterdir()),
                                                      "three_policy_three_check_max_calls": 20}))
    return root


def test_checkpoint_is_write_once_and_atomic(tmp_path):
    path = tmp_path / "checkpoint.json"
    _save(path, {"a": 1})
    _save(path, {"a": 1})
    with pytest.raises(ValueError, match="differs"):
        _save(path, {"a": 2})
    assert json.loads(path.read_text()) == {"a": 1}
    assert not list(tmp_path.glob("*.part"))


def test_prepared_sources_are_checked_before_any_inference(pilot_data):
    data, hashes, _ = load_data(pilot_data)
    assert len(data) == len(hashes) == 2
    with (pilot_data / "media/red.mp4").open("ab") as output:
        output.write(b"changed")
    with pytest.raises(ValueError, match="changed"):
        load_data(pilot_data)


def test_budget_must_fit_frozen_pilot_before_external_requests(pilot_data, tmp_path):
    with endpoint([]) as (url, calls):
        with pytest.raises(ValueError, match="cannot fit"):
            Pilot(Settings("unused", tmp_path, qwen_base_url=url), pilot_data, limit=19)
    assert not calls


def test_private_output_cannot_escape_dataset(pilot_data, tmp_path):
    with pytest.raises(ValueError, match="inside"):
        Pilot(Settings("unused", tmp_path), pilot_data, work=tmp_path / "public")


def test_changing_work_directory_cannot_reset_the_approved_budget(pilot_data, tmp_path):
    with endpoint([]) as (url, calls):
        settings = Settings("dbname=test", tmp_path, qwen_base_url=url)
        Pilot(settings, pilot_data, work=pilot_data / "first", limit=30)
        with pytest.raises(ValueError, match="differs"):
            Pilot(settings, pilot_data, work=pilot_data / "second", limit=30)
    assert not calls


OLD_CONTEXT_SOURCE = '''PROMPT = "same"
class Client:
    def inspect_extent(self, data):
        contradictory = False
        if contradictory or (data['query_support'] == 'all' and 'present' not in data['sample_support']):
            raise ValueError("duplicate")
        data['status'] = 'no_match'
        return data
'''
NEW_CONTEXT_SOURCE = OLD_CONTEXT_SOURCE.replace(
    "if contradictory or (data['query_support'] == 'all' and 'present' not in data['sample_support']):",
    "if contradictory:").replace("        return data", """        if data['query_support'] == 'all' and 'present' not in data['sample_support']:
            data['status'] = 'insufficient_evidence'
        return data""")


def test_cache_proof_accepts_only_the_unlocalized_context_change():
    assert validate_context_cache_change(OLD_CONTEXT_SOURCE, NEW_CONTEXT_SOURCE) == "only-unlocalized-context-branch-changed"
    assert validate_context_cache_change(OLD_CONTEXT_SOURCE, OLD_CONTEXT_SOURCE) == "identical-source"


@pytest.mark.parametrize("changed", [
    NEW_CONTEXT_SOURCE.replace('PROMPT = "same"', 'PROMPT = "changed"'),
    NEW_CONTEXT_SOURCE.replace("data['status'] = 'no_match'", "data['status'] = 'match'"),
    NEW_CONTEXT_SOURCE.replace("not in data['sample_support']", "in data['sample_support']"),
    NEW_CONTEXT_SOURCE + "\nOTHER_CHANGE = True\n",
])
def test_cache_proof_rejects_prompt_other_behavior_and_predicate_changes(changed):
    with pytest.raises(RunError):
        validate_context_cache_change(OLD_CONTEXT_SOURCE, changed)


def test_index_isolated_and_resumable_with_real_encoder(database_url, pilot_data):
    if os.environ.get("RUN_MODEL_TESTS") != "1":
        pytest.skip("Requires the installed text encoder")
    outside = store.enqueue(database_url, "outside.mp4", 123, 456)
    answer = {"status": "match", "intervals": [{"start_seconds": .2, "end_seconds": 1.8}],
              "observation": "The sampled frames show a colored image."}
    extent_answer = {"query_support": "all", "anchor_relation": "not_applicable",
                     "sample_support": ["absent", *["present"] * 6, "absent"],
                     "observation": "The middle source samples support the action."}
    responses = [(200, envelope()), (200, envelope())]
    for query_id in ["train-query", "test-query"]:
        conditions = sorted(DEVELOPMENT_CONDITIONS if query_id == "train-query" else CONDITIONS, key=lambda name: _digest(["charades-paired-order-v1", query_id, name]))
        responses.extend((200, envelope(answer if name == "ranked_fixed" else extent_answer)) for name in conditions)
    with endpoint(responses) as (url, calls):
        settings = Settings(database_url, pilot_data, model_cache=Path(os.environ.get("MODEL_CACHE", "/models")),
                            qwen_base_url=url, qwen_api_key="fixture-upstream-key")
        pilot = Pilot(settings, pilot_data, limit=30)
        try:
            with pilot:
                pilot.index()
                assert pilot.gateway.attempts_used == 2
                assert pilot.protocol()["prior_protocol_sha256"] is None
                previous_freeze = b'{"legacy_protocol":"preserved"}\n'
                (pilot.work / "test.freeze.json").write_bytes(previous_freeze)
                assert pilot.protocol()["evaluation_status"] == "exploratory-after-prior-protocol-exposure"
                assert store.get_job(database_url, outside["id"])["state"] == "queued"
                assert len(store.list_recordings(database_url)) == 0
                assert len(store.list_recordings(pilot.settings.database_url)) == 2
                with pytest.raises(RuntimeError, match="development"):
                    pilot.freeze()
                pilot.run_queries("train")
                assert pilot.gateway.attempts_used == 3
                assert pilot.protocol()["development_conditions"] == DEVELOPMENT_CONDITIONS
                assert pilot.protocol()["conditions"] == CONDITIONS
                pilot.freeze()
                assert (pilot.work / POINT_FREEZE).is_file()
                assert (pilot.work / "test.freeze.json").read_bytes() == previous_freeze
                assert pilot.protocol()["prior_protocol_sha256"] == hashlib.sha256(previous_freeze).hexdigest()
                assert pilot.protocol()["development_max_checks"] == DEVELOPMENT_CHECKS == 1
                assert pilot.protocol()["max_checks"] == EVALUATION_CHECKS == 2
                pilot.run_queries("test")
                aggregate = pilot.report("test")
                assert aggregate and pilot.gateway.attempts_used == len(calls) == 6
                initial = pilot.protocol()
                parent = {**initial, "run_variant": "point-aware-pilot-v1"}
                (pilot.work / POINT_FREEZE).rename(pilot.work / "earlier-context.freeze.json")
                _save(pilot.work / "point-aware.freeze.json", parent)
                for name in parent["source_sha256"]:
                    _save(pilot.work / "point-aware-frozen-source" / name,
                          (Path(__file__).parents[1] / "src/video_search" / name).read_bytes())
                old_cases = {}
                for phase in ("development", "test"):
                    source = pilot.work / phase / _digest(initial)
                    destination = pilot.work / phase / _digest(parent)
                    _save(destination / "protocol.json", parent)
                    for path in (source / "cases").glob("*.json"):
                        case = {**json.loads(path.read_bytes()), "protocol_hash": _digest(parent)}
                        target = destination / "cases" / path.name
                        _save(target, case)
                        old_cases[target] = target.read_bytes()
                    for path in (source / "retrieval").glob("*.json"):
                        _save(destination / "retrieval" / path.name, path.read_bytes())
                pilot.reuse_context_cache()
                pilot.reuse_context_cache()
                assert pilot.gateway.attempts_used == len(calls) == 6
                assert all(path.read_bytes() == raw for path, raw in old_cases.items())
                for phase in ("development", "test"):
                    for path in (pilot.work / phase / _digest(pilot.protocol()) / "cases").glob("*.json"):
                        reused = json.loads(path.read_bytes())
                        original = json.loads((pilot.work / phase / _digest(parent) / "cases" / path.name).read_bytes())
                        assert reused["result"] == original["result"]
                        assert reused["cache_reuse"]["parent_case_sha256"] == hashlib.sha256(
                            (pilot.work / phase / _digest(parent) / "cases" / path.name).read_bytes()).hexdigest()
                pilot.freeze()
                pilot.run_queries("test")
                assert pilot.gateway.attempts_used == len(calls) == 6
            with Pilot(settings, pilot_data, limit=30) as resumed:
                resumed.index()
                resumed.run_queries("test")
                assert resumed.gateway.attempts_used == len(calls) == 6
        finally:
            with store._connect(database_url) as conn:
                conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(pilot.schema)))
