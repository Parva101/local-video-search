import os
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient
import psycopg
import pytest

from video_search.api import create_app
from video_search.config import Settings
from video_search.encoder import SPEC, EncoderError, get_encoder
from video_search import store
from video_search.worker import process_one


def test_search_validation_without_loading_model(database_url, tmp_path):
    with TestClient(create_app(Settings(database_url, tmp_path))) as client:
        for body in ({"query": " "}, {"query": "red", "recording_ids": []},
                     {"query": "red", "start_seconds": 10, "end_seconds": 2},
                     {"query": "red", "limit": 101}, {"query": "red", "unexpected": True}):
            assert client.post("/search", json=body).status_code == 422


def test_uninstalled_model_is_explicit(database_url, video_file, tmp_path):
    settings = Settings(database_url, video_file.parent, model_cache=tmp_path / "missing-models")
    with TestClient(create_app(settings)) as client:
        client.post("/imports", json={"path": video_file.name})
        process_one(settings)
        recording = client.get("/recordings").json()[0]
        job = client.post(f"/recordings/{recording['id']}/visual-index").json()
        process_one(settings)
        failed = client.get(f"/jobs/{job['id']}").json()
        assert failed["state"] == "failed"
        assert failed["error"]["code"] == "model_not_installed"
        index = client.get(f"/visual-indexes/{job['index_build_id']}").json()
        assert index["state"] == "failed"
        assert index["completed_windows"] == 0
        response = client.post("/search", json={"query": "a red image"})
        assert response.status_code == 503
        assert response.json()["code"] == "model_not_installed"


def test_real_encoder_index_and_temporal_search(database_url, tmp_path):
    if os.environ.get("RUN_MODEL_TESTS") != "1":
        pytest.skip("Set RUN_MODEL_TESTS=1 after downloading the pinned checkpoint")
    cache = Path(os.environ.get("MODEL_CACHE", "/models"))
    path = tmp_path / "colors.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64:r=4:d=8",
        "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=4:d=8",
        "-f", "lavfi", "-i", "color=c=green:s=64x64:r=4:d=8",
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]",
        "-c:v", "mpeg4", str(path),
    ], check=True, capture_output=True, timeout=30)
    settings = Settings(database_url, tmp_path, model_cache=cache)
    with TestClient(create_app(settings)) as client:
        imported = client.post("/imports", json={"path": path.name}).json()["jobs"][0]
        assert process_one(settings)
        recording = client.get(f"/jobs/{imported['id']}").json()["result"]["recording_id"]
        requested = client.post(f"/recordings/{recording}/visual-index")
        assert requested.status_code == 202
        job = requested.json()
        assert process_one(settings)
        completed = client.get(f"/jobs/{job['id']}").json()
        assert completed["state"] == "succeeded", completed
        index = client.get(f"/visual-indexes/{job['index_build_id']}").json()
        assert index["state"] == "ready"
        assert index["completed_windows"] == index["total_windows"] == 3
        assert client.get(f"/recordings/{recording}").json()["metadata"]["search_index_status"] == "ready"
        for color, expected_start in [("red", 0.0), ("blue", 8.0), ("green", 16.0)]:
            result = client.post("/search", json={"query": f"a {color} image", "limit": 1})
            assert result.status_code == 200, result.text
            top = result.json()["results"][0]
            assert top["recording_id"] == recording
            assert top["start_seconds"] == expected_start, (color, result.json())
            assert top["verified"] is False
            assert top["source_status"] == "available"
            assert len(top["samples"]) == 3
        filtered = client.post("/search", json={"query": "a red image", "recording_ids": [recording],
                                                "start_seconds": 18, "end_seconds": 24}).json()
        assert all(item["start_seconds"] == 16 for item in filtered["results"])
        assert filtered["coverage"]["ready_windows"] == 1
        repeated = client.post(f"/recordings/{recording}/visual-index").json()
        assert repeated["id"] == job["id"]
        assert not process_one(settings)
        with pytest.raises(EncoderError, match="64 model tokens"):
            get_encoder(cache).text("red " * 100)
        # A checkpointed index stays usable after a separate API instance starts.
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(f"/visual-indexes/{job['index_build_id']}").json()["state"] == "ready"
        assert restarted.post("/search", json={"query": "a blue image", "limit": 1}).json()["results"][0]["start_seconds"] == 8
