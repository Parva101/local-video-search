import os
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from video_search.api import create_app
from video_search.config import Settings
from video_search.worker import process_one
from test_vlm import endpoint, envelope


def test_description_and_verification_need_explicit_endpoint(database_url, video_file):
    settings = Settings(database_url, video_file.parent)
    with TestClient(create_app(settings)) as api:
        api.post("/imports", json={"path": video_file.name})
        process_one(settings)
        recording = api.get("/recordings").json()[0]["id"]
        response = api.post(f"/recordings/{recording}/description-index")
        assert response.status_code == 503
        assert response.json()["code"] == "vlm_not_configured"
        verify = api.post("/verify", json={"recording_id": recording, "query": "a red image",
                                          "start_seconds": 0, "end_seconds": 2})
        assert verify.status_code == 503
        assert len(api.get("/jobs").json()) == 1


def test_description_search_hybrid_and_source_verification(database_url, video_file):
    if os.environ.get("RUN_MODEL_TESTS") != "1":
        pytest.skip("Requires downloaded local embedding models")
    description = {"summary": "A red image is visible.", "objects": ["red image"], "actions": [], "uncertainties": []}
    verification = {"status": "match", "intervals": [{"start_seconds": 0.2, "end_seconds": 1.8}],
                    "observation": "The sampled source frames are red."}
    with endpoint([(200, envelope(description)), (200, envelope(verification))]) as (url, calls):
        settings = Settings(database_url, video_file.parent, model_cache=Path(os.environ.get("MODEL_CACHE", "/models")),
                            qwen_base_url=url, qwen_api_key="test-key")
        with TestClient(create_app(settings)) as api:
            api.post("/imports", json={"path": video_file.name})
            process_one(settings)
            recording = api.get("/recordings").json()[0]["id"]
            api.post(f"/recordings/{recording}/visual-index")
            process_one(settings)
            job = api.post(f"/recordings/{recording}/description-index").json()
            process_one(settings)
            state = api.get(f"/jobs/{job['id']}").json()
            assert state["state"] == "succeeded", state
            build = api.get(f"/description-indexes/{job['description_build_id']}").json()
            assert build["state"] == "ready"
            assert build["completed_windows"] == build["total_windows"] == 1
            for path in ("description", "hybrid"):
                response = api.post("/search", json={"query": "red image", "path": path, "limit": 1})
                assert response.status_code == 200, response.text
                item = response.json()["results"][0]
                assert item["recording_id"] == recording
                assert item["description"]["summary"] == description["summary"]
                assert not item["verified"]
                if path == "hybrid":
                    assert set(item["paths"]) == {"visual", "description"}
                    assert set(response.json()["spec"]) == {"visual", "description"}
            checked = api.post("/verify", json={"recording_id": recording, "query": "Is the image red?",
                                               "start_seconds": 0, "end_seconds": 2, "context_seconds": 0})
            assert checked.status_code == 200, checked.text
            result = checked.json()
            assert result["result"]["status"] == "match"
            assert len(result["samples"]) == 8
            persisted = api.get(f"/verifications/{result['id']}").json()
            assert persisted["response"]["status"] == "match"
            assert persisted["response"]["_trace"]["frame_sha256"]
            assert len(calls) == 2
            assert api.post(f"/recordings/{recording}/description-index").json()["id"] == job["id"]
            assert not process_one(settings)


def test_gemma_verification_saves_its_prompt_version_without_changing_description_spec(database_url, video_file):
    from video_search import analysis, store
    from video_search.vlm import GEMMA_MODEL_ID, GEMMA_VERIFICATION_PROMPT_VERSION

    answer = {"status": "match", "intervals": [{"start_seconds": .2, "end_seconds": 1.8}],
              "observation": "The supplied frames show red."}
    response = {**envelope(answer), "model": GEMMA_MODEL_ID}
    with endpoint([(200, response)]) as (url, calls):
        settings = Settings(database_url, video_file.parent, vision_provider="gemma",
                            voyager_api_key="test-key", voyager_base_url=url)
        spec_before = analysis.description_spec(settings)
        with TestClient(create_app(settings)) as api:
            api.post("/imports", json={"path": video_file.name})
            assert process_one(settings)
            recording = api.get("/recordings").json()[0]["id"]
            checked = api.post("/verify", json={"recording_id": recording, "query": "red", "start_seconds": 0,
                                               "end_seconds": 2, "context_seconds": 0})
            assert checked.status_code == 200, checked.text
            saved = store.get_verification(database_url, checked.json()["id"])
            assert saved["spec"]["prompt_version"] == GEMMA_VERIFICATION_PROMPT_VERSION
            assert saved["response"]["_trace"]["prompt_version"] == GEMMA_VERIFICATION_PROMPT_VERSION
            assert saved["spec"]["verification_schema_version"] == "status-intervals-v3-points"
            assert analysis.description_spec(settings) == spec_before
            assert spec_before["prompt_version"] == "visible-evidence-gemma-json-v2"
            assert len(calls) == 1


@pytest.mark.parametrize("provider", ["qwen", "gemma"])
def test_point_evidence_is_saved_with_new_verification_contract(database_url, video_file, provider):
    from video_search import analysis, media, store
    from video_search.vlm import GEMMA_MODEL_ID

    raw = {"status": "match", "intervals": [{"start_seconds": 0.0, "end_seconds": 0.0}],
           "observation": "One observed instant shows red."}
    response = {**envelope(raw), "model": GEMMA_MODEL_ID if provider == "gemma" else envelope()["model"]}
    with endpoint([(200, response)]) as (url, calls):
        settings = Settings(database_url, video_file.parent, vision_provider=provider, qwen_base_url=url,
                            voyager_base_url=url, voyager_api_key="test-key")
        before = analysis.description_spec(settings)
        store.enqueue(database_url, video_file.name, *media.fingerprint(video_file))
        assert process_one(settings)
        recording = store.list_recordings(database_url)[0]
        checked = analysis.verify(settings, recording, "red", 0, 2, context=0)
        saved = store.get_verification(database_url, checked["id"])
    assert len(calls) == 1 and saved["response"]["intervals"] == raw["intervals"]
    assert checked["result"]["intervals"] == raw["intervals"]
    assert saved["spec"]["verification_schema_version"] == "status-intervals-v3-points"
    assert saved["response"]["_trace"]["verification_schema_version"] == "status-intervals-v3-points"
    assert saved["spec"]["prompt_version"] == saved["response"]["_trace"]["prompt_version"]
    assert analysis.description_spec(settings) == before


def test_verification_api_rejects_invalid_bounds(database_url, video_file):
    with TestClient(create_app(Settings(database_url, video_file.parent))) as api:
        api.post("/imports", json={"path": video_file.name})
        process_one(Settings(database_url, video_file.parent))
        recording = api.get("/recordings").json()[0]["id"]
        for start, end in [(0, 3), (1, 0.5), (0, 31)]:
            assert api.post("/verify", json={"recording_id": recording, "query": "red", "start_seconds": start,
                                            "end_seconds": end}).status_code == 422
