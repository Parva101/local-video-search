from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from video_search import media, store
from video_search.api import create_app
from video_search.config import Settings
from video_search.worker import process_one


def test_library_identity_requires_absolute_host_path(tmp_path):
    with pytest.raises(ValueError, match="absolute host video directory"):
        Settings("unused", tmp_path, library_id="./media")


def test_import_worker_playback_and_repeat(database_url, video_file):
    settings = Settings(database_url, video_file.parent)
    with TestClient(create_app(settings)) as client:
        health = client.get("/health").json()
        assert health["status"] == "ready"
        assert health["schema_version"] == store.SCHEMA_VERSION
        assert set(health["job_queue"]) == {"queued", "running"}
        submitted = client.post("/imports", json={"path": "."})
        assert submitted.status_code == 202, submitted.text
        assert submitted.headers["X-Request-ID"]
        job_id = submitted.json()["jobs"][0]["id"]
        assert process_one(settings)
        job = client.get(f"/jobs/{job_id}").json()
        assert job["state"] == "succeeded", job
        item = job["result"]["recording_id"]
        recording = client.get(f"/recordings/{item}").json()
        assert recording["metadata"]["has_audio"] is False
        assert recording["metadata"]["search_index_status"] == "not_built"
        assert client.get(f"/recordings/{item}/windows").json() == [{"start_seconds": 0.0, "end_seconds": 2.0}]
        response = client.get(f"/recordings/{item}/media", headers={"Range": "bytes=0-31"})
        assert response.status_code == 206
        assert response.content == video_file.read_bytes()[:32]
        assert client.post("/imports", json={"path": "."}).json()["jobs"][0]["id"] == job_id
        assert not process_one(settings)
        assert len(client.get("/recordings").json()) == 1


def test_corrupt_video_is_explicit_failed_job(database_url, tmp_path):
    (tmp_path / "broken.mp4").write_bytes(b"this is not a video")
    settings = Settings(database_url, tmp_path)
    with TestClient(create_app(settings)) as client:
        job = client.post("/imports", json={"path": "."}).json()["jobs"][0]
        process_one(settings)
        failed = client.get(f"/jobs/{job['id']}").json()
        assert failed["state"] == "failed"
        assert failed["error"]["code"]
        assert client.get("/recordings").json() == []


def test_change_before_processing_is_rejected(database_url, video_file):
    settings = Settings(database_url, video_file.parent)
    size, mtime = media.fingerprint(video_file)
    job = store.enqueue(database_url, video_file.name, size, mtime)
    video_file.write_bytes(b"replacement")
    process_one(settings)
    assert store.get_job(database_url, str(job["id"]))["error"]["code"] == "source_changed"


def test_changed_source_not_served_as_old_evidence(database_url, video_file):
    settings = Settings(database_url, video_file.parent)
    with TestClient(create_app(settings)) as client:
        client.post("/imports", json={"path": video_file.name})
        process_one(settings)
        item = client.get("/recordings").json()[0]["id"]
        video_file.write_bytes(b"changed")
        response = client.get(f"/recordings/{item}/media")
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "source_changed"


def test_api_validation(database_url, video_file):
    with TestClient(create_app(Settings(database_url, video_file.parent))) as client:
        assert client.post("/imports", json={"path": "../outside"}).status_code == 422
        assert client.post("/imports", json={"path": str(video_file)}).status_code == 422
        assert client.post("/imports", json={"path": ".", "unexpected": True}).status_code == 422
        assert client.get("/jobs/not-a-uuid").status_code == 422
        assert client.get(f"/jobs/{uuid4()}").status_code == 404
        assert client.get("/recordings?limit=0").status_code == 422


def test_worker_resumes_expired_claim(database_url, video_file):
    import psycopg

    settings = Settings(database_url, video_file.parent)
    size, mtime = media.fingerprint(video_file)
    job = store.enqueue(database_url, video_file.name, size, mtime)
    old = store.claim_job(database_url)
    with psycopg.connect(database_url) as conn:
        conn.execute("UPDATE jobs SET lease_until = now() - interval '1 second' WHERE id = %s", (job["id"],))
    assert process_one(settings)
    finished = store.get_job(database_url, str(job["id"]))
    assert finished["state"] == "succeeded"
    assert finished["attempts"] == 2


def test_failed_job_can_be_retried_explicitly(database_url, video_file):
    settings = Settings(database_url, video_file.parent)
    with TestClient(create_app(settings)) as client:
        job = client.post("/imports", json={"path": video_file.name}).json()["jobs"][0]
        claimed = store.claim_job(database_url)
        store.fail_job(database_url, str(claimed["id"]), str(claimed["lease_token"]), {"code": "operator_test"})
        assert client.post(f"/jobs/{job['id']}/retry").status_code == 202
        assert client.post(f"/jobs/{job['id']}/retry").status_code == 409
        process_one(settings)
        assert client.get(f"/jobs/{job['id']}").json()["state"] == "succeeded"


def test_health_is_not_ready_for_wrong_schema(database_url, video_file):
    import psycopg

    with TestClient(create_app(Settings(database_url, video_file.parent))) as client:
        with psycopg.connect(database_url) as conn:
            conn.execute("UPDATE schema_version SET version = 999")
        assert client.get("/health").status_code == 503


def test_process_death_releases_work_after_lease_expiry(database_url, video_file):
    import os
    import subprocess
    import sys
    import time

    settings = Settings(database_url, video_file.parent)
    size, mtime = media.fingerprint(video_file)
    job = store.enqueue(database_url, video_file.name, size, mtime)
    killed = subprocess.run([
        sys.executable, "-c",
        "import os; from video_search import store; "
        "store.claim_job(os.environ['CRASH_TEST_DATABASE_URL'], lease_seconds=1); os._exit(137)",
    ], env={**os.environ, "CRASH_TEST_DATABASE_URL": database_url}, timeout=10)
    assert killed.returncode == 137
    deadline = time.monotonic() + 5
    while not process_one(settings):
        assert time.monotonic() < deadline, "Expired job was not recovered"
        time.sleep(0.1)
    finished = store.get_job(database_url, str(job["id"]))
    assert finished["state"] == "succeeded"
    assert finished["attempts"] == 2
