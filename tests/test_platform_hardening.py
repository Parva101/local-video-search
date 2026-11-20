from datetime import date
import subprocess
import time
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg
import pytest

from video_search.api import create_app
from video_search.config import Settings
from video_search import store
from video_search.worker import process_one
from test_vlm import endpoint, envelope


NO_MATCH = {"status": "no_match", "intervals": [], "observation": "No red anywhere."}
UNIT_VECTOR_384 = [1.0] + [0.0] * 383

ASR_SPEC = {"source": "asr", "model_id": "test-asr", "revision": "test",
            "dimensions": 384, "runtime": "test"}
SUBTITLE_SPEC = {"source": "subtitle", "format": "srt", "content_sha256": "hardening",
                 "dimensions": 384, "text_encoder": "test", "text_encoder_revision": "test",
                 "runtime": "test"}


def _import_one(client, settings, video_file):
    job = client.post("/imports", json={"path": video_file.name}).json()["jobs"][0]
    assert process_one(settings)
    return client.get(f"/jobs/{job['id']}").json()["result"]["recording_id"]


def _long_video(tmp_path):
    path = tmp_path / "twenty-four.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64:r=4:d=24",
        "-c:v", "mpeg4", "-y", str(path),
    ], check=True, capture_output=True, timeout=60)
    return path


def test_count_events_time_filter_partitions_across_recordings(database_url, video_file, tmp_path):
    long_video = _long_video(tmp_path)
    with endpoint([(200, envelope(NO_MATCH))]) as (url, calls):
        settings = Settings(database_url, tmp_path, qwen_base_url=url)
        with TestClient(create_app(settings)) as client:
            first = client.post("/imports", json={"path": long_video.name}).json()["jobs"][0]
            second = client.post("/imports", json={"path": video_file.name}).json()["jobs"][0]
            assert process_one(settings)
            assert process_one(settings)
            long_id = client.get(f"/jobs/{first['id']}").json()["result"]["recording_id"]
            short_id = client.get(f"/jobs/{second['id']}").json()["result"]["recording_id"]
            # Baselines without a filter: 24 s -> three windows, 2 s -> one window.
            assert store.count_windows(database_url, long_id) == 3
            assert store.count_windows(database_url, short_id) == 1
            data = client.post("/count-events", json={
                "query": "a red image", "recording_ids": [long_id, short_id],
                "start_seconds": 9, "end_seconds": 11, "max_checks": 10}).json()
            assert data["count"] == 0, data
            # Only the two long-recording windows overlapping [9, 11) are counted partitions.
            assert data["partitions"] == {"total": 2, "checked": 2, "uncertain": 0,
                                          "skipped_undated": 0, "complete": True}
            assert data["stop_reason"] == "scope_exhausted"
            assert len(calls) == 2


def test_transcript_job_lifecycle_guards(database_url, video_file, tmp_path):
    settings = Settings(database_url, video_file.parent)
    with TestClient(create_app(settings)) as client:
        recording = _import_one(client, settings, video_file)
        # A claimed transcript job with zero segments cannot publish an empty index.
        job = store.enqueue_transcript(database_url, recording, ASR_SPEC)
        assert job["kind"] == "transcript" and job["state"] == "queued"
        claimed = store.claim_job(database_url)
        assert claimed is not None and str(claimed["id"]) == str(job["id"])
        build = store.get_transcript_build(database_url, str(claimed["transcript_build_id"]))
        assert build["state"] == "running" and build["completed_segments"] == 0
        with pytest.raises(ValueError, match="empty transcript"):
            store.finish_transcript_job(database_url, str(claimed["id"]), str(claimed["lease_token"]))
        nothing = store.get_transcript_build(database_url, str(claimed["transcript_build_id"]))
        assert nothing["state"] == "running" and nothing["completed_segments"] == 0
        # A stale lease loses write access: saving and publishing are both refused.
        stale = store.enqueue_transcript(database_url, recording, SUBTITLE_SPEC)
        worker = store.claim_job(database_url, lease_seconds=1)
        assert str(worker["id"]) == str(stale["id"])
        time.sleep(1.5)
        with pytest.raises(store.LeaseLost, match="expired"):
            store.save_transcript_segment(database_url, str(stale["id"]), str(worker["lease_token"]),
                                          0.1, 0.9, "A stale worker writes this.", UNIT_VECTOR_384)
        with pytest.raises(store.LeaseLost, match="expired"):
            store.finish_transcript_job(database_url, str(stale["id"]), str(worker["lease_token"]))
        untouched = store.get_transcript_build(database_url, str(stale["transcript_build_id"]))
        assert untouched["completed_segments"] == 0


def test_capture_date_source_and_speech_date_guards(database_url, video_file, tmp_path):
    settings = Settings(database_url, video_file.parent)
    with TestClient(create_app(settings)) as client:
        recording = _import_one(client, settings, video_file)
        with pytest.raises(ValueError, match="Capture date source"):
            store.set_capture_date(database_url, recording, date(2026, 11, 20), "gps")
        unchanged = store.get_recording(database_url, recording)
        assert unchanged["capture_date"] is None and unchanged["capture_date_source"] is None
        set_row = store.set_capture_date(database_url, recording, date(2026, 11, 20), "user")
        assert set_row["capture_date"] == date(2026, 11, 20)
        assert set_row["capture_date_source"] == "user"
        with pytest.raises(ValueError, match="before its start date"):
            store.search_speech(database_url, "a package", UNIT_VECTOR_384,
                                start_date=date(2026, 11, 20), end_date=date(2026, 11, 19))


def test_health_reflects_schema_readiness(database_url, tmp_path):
    with TestClient(create_app(Settings(database_url, tmp_path))) as client:
        healthy = client.get("/health")
        assert healthy.status_code == 200
        body = healthy.json()
        assert body["status"] == "ready"
        assert body["schema_version"] == store.SCHEMA_VERSION
        assert body["job_queue"] == {"queued": 0, "running": 0}
        with psycopg.connect(database_url) as conn:
            conn.execute("UPDATE schema_version SET version = 5")
        stale = client.get("/health")
        assert stale.status_code == 503
        assert stale.json() == {"detail": "Database schema is not ready"}


def test_transcript_index_route_scopes_known_and_unknown_builds(database_url, video_file, tmp_path):
    settings = Settings(database_url, video_file.parent)
    with TestClient(create_app(settings)) as client:
        recording = _import_one(client, settings, video_file)
        build_id, created = store.create_ready_transcript(
            database_url, recording, SUBTITLE_SPEC,
            [(0.1, 0.9, "The delivery person left a package at the front door.", UNIT_VECTOR_384)])
        assert created
        known = client.get(f"/transcript-indexes/{build_id}")
        assert known.status_code == 200, known.text
        body = known.json()
        assert body["id"] == build_id and body["state"] == "ready"
        assert body["completed_segments"] == 1
        assert client.get(f"/transcript-indexes/{uuid4()}").status_code == 404
        assert client.get("/transcript-indexes/not-a-uuid").status_code == 422
