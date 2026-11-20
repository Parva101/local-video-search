import os
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from video_search import analysis, store
from video_search.api import create_app
from video_search.config import Settings
from video_search.worker import process_one
from test_vlm import endpoint, envelope


def test_extent_budget_parameters_are_explicit(database_url, tmp_path):
    with TestClient(create_app(Settings(database_url, tmp_path))) as api:
        for options in ({"policy": "ranked", "spend_budget": True}, {"policy": "extent", "spend_budget": "true"},
                        {"policy": "uniform_extent", "max_checks": 7}, {"policy": "unknown"}):
            response = api.post("/evidence-search", json={"query": "red frame", **options})
            assert response.status_code == 422, response.text


def test_extent_api_keeps_estimates_separate_from_source_samples(database_url, video_file):
    if os.environ.get("RUN_MODEL_TESTS") != "1":
        pytest.skip("Requires the installed text embedding model")
    answer = {"query_support": "all", "anchor_relation": "not_applicable",
              "sample_support": ["absent", *["present"] * 6, "absent"], "observation": "The middle samples support the query."}
    with endpoint([(200, envelope(answer))]) as (url, calls):
        settings = Settings(database_url, video_file.parent, qwen_base_url=url,
                            model_cache=Path(os.environ.get("MODEL_CACHE", "/models")))
        with TestClient(create_app(settings)) as api:
            api.post("/imports", json={"path": video_file.name})
            assert process_one(settings)
            recording = api.get("/recordings").json()[0]["id"]
            store.enqueue_description(database_url, recording, analysis.description_spec(settings))
            job = store.claim_job(database_url)
            samples = [{"source_seconds": .1 + i * .2, "requested_seconds": .1 + i * .2,
                        "pts_seconds": .1 + i * .2} for i in range(8)]
            description = {"summary": "Red frame", "actions": [], "objects": [], "uncertainties": []}
            store.save_description_window(database_url, str(job["id"]), str(job["lease_token"]), 0, 2, samples,
                                          description, "Red frame", [1.0] + [0.0] * 383)
            store.finish_description_job(database_url, str(job["id"]), str(job["lease_token"]))
            response = api.post("/evidence-search", json={"query": "red frame", "recording_ids": [recording],
                                "policy": "extent", "max_checks": 1})
            assert response.status_code == 200, response.text
            data = response.json()
            proposal = data["proposals"][0]
            checked = data["checks"][0]["verification"]
            assert proposal["complete"] is True and proposal["verified"] is False
            assert 0 < proposal["start_seconds"] < proposal["end_seconds"] < 2
            assert checked["result"]["intervals"][0]["start_seconds"] > proposal["start_seconds"]
            assert checked["reference"] is None and len(checked["samples"]) == 8
            saved = api.get(f"/verifications/{checked['id']}").json()
            assert saved["spec"]["task"] == "extent"
            assert saved["spec"]["extent_schema_version"] == "sample-support-v5-context-support"
            assert checked["result"]["_trace"]["status_derivation"] == "new-sample-support-v1"
            assert checked["result"]["_trace"]["query_support_scope"] == "all-input-samples-v1"
            assert data["retrieval"]["results"][0]["start_seconds"] == 0
            assert data["budget"]["calls"] == len(calls) == 1
            assert data["supports_absence_or_counts"] is False
