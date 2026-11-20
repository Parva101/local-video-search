import os
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from video_search import analysis, store
from video_search.api import create_app
from video_search.config import Settings
from video_search.worker import process_one
from test_vlm import endpoint, envelope


def test_evidence_api_validates_work_budget(database_url, tmp_path):
    with TestClient(create_app(Settings(database_url, tmp_path))) as api:
        for extra in ({"max_checks": 0}, {"max_checks": 7}, {"max_checks": True},
                      {"limit": 25}, {"policy": "unknown"}, {"query": "  "},
                      {"rerank": True, "path": "visual"}, {"rerank": "true"},
                      {"start_seconds": 2, "end_seconds": 1}):
            response = api.post("/evidence-search", json={"query": "red", **extra})
            assert response.status_code == 422, response.text


def test_evidence_api_preserves_retrieval_and_saved_source_checks(database_url, video_file):
    if os.environ.get("RUN_MODEL_TESTS") != "1":
        pytest.skip("Requires the installed text embedding model")
    match = {"status": "match", "intervals": [{"start_seconds": .6, "end_seconds": 1.4}],
             "observation": "The source frames show red."}
    with endpoint([(200, envelope(match))]) as (url, calls):
        settings = Settings(database_url, video_file.parent,
                            model_cache=Path(os.environ.get("MODEL_CACHE", "/models")), qwen_base_url=url)
        with TestClient(create_app(settings)) as api:
            api.post("/imports", json={"path": video_file.name})
            assert process_one(settings)
            recording = api.get("/recordings").json()[0]["id"]
            store.enqueue_description(database_url, recording, analysis.description_spec(settings))
            job = store.claim_job(database_url)
            samples = [{"requested_seconds": .1 + i * .2, "source_seconds": .1 + i * .2,
                        "pts_seconds": .1 + i * .2} for i in range(8)]
            store.save_description_window(database_url, str(job["id"]), str(job["lease_token"]),
                                          0, 2, samples, {"summary": "Red frame", "actions": [], "objects": [], "uncertainties": []}, "Red frame",
                                          [1.0] + [0.0] * 383)
            store.finish_description_job(database_url, str(job["id"]), str(job["lease_token"]))
            response = api.post("/evidence-search", json={"query": "red frame", "recording_ids": [recording],
                                "start_seconds": .5, "end_seconds": 1.5, "max_checks": 2})
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["request_id"] == response.headers["X-Request-ID"]
            assert data["status"] == "match" and data["stop_reason"] == "match_found"
            assert data["retrieval"]["path"] == "description"
            assert data["retrieval"]["results"][0]["start_seconds"] == 0
            check = data["checks"][0]
            assert check["verification"]["inspection_start_seconds"] == .5
            assert check["verification"]["inspection_end_seconds"] == 1.5
            assert data["budget"]["calls"] == len(calls) == 1
            assert data["budget"]["frames"] == 8
            assert data["supports_absence_or_counts"] is False
            assert api.get(f"/verifications/{check['verification']['id']}").status_code == 200
            reranked = api.post("/search", json={"query": "red frame", "path": "description",
                                "recording_ids": [recording], "rerank": True, "limit": 1})
            assert reranked.status_code == 200, reranked.text
            ranked = reranked.json()
            assert ranked["reranker"]["candidate_count"] == 1
            assert ranked["reranker"]["spec"]["model_id"] == "cross-encoder/ms-marco-MiniLM-L6-v2"
            assert ranked["results"][0]["retrieval_rank"] == 1
            assert isinstance(ranked["results"][0]["rerank_score"], float)
