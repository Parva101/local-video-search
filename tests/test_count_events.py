from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from video_search.api import create_app
from video_search.config import Settings
from video_search.worker import process_one
from test_vlm import endpoint, envelope


def _colors_video(tmp_path):
    import subprocess
    path = tmp_path / "colors.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64:r=4:d=8",
        "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=4:d=8",
        "-f", "lavfi", "-i", "color=c=green:s=64x64:r=4:d=8",
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]",
        "-c:v", "mpeg4", str(path),
    ], check=True, capture_output=True, timeout=30)
    return path


def _match(start, end, text):
    return {"status": "match", "intervals": [{"start_seconds": start, "end_seconds": end}], "observation": text}


NO_MATCH = {"status": "no_match", "intervals": [], "observation": "Nothing red."}
UNCLEAR = {"status": "insufficient_evidence", "intervals": [], "observation": "Hard to tell."}


def test_count_events_validation(database_url, tmp_path):
    with TestClient(create_app(Settings(database_url, tmp_path))) as client:
        for extra in ({"max_checks": 0}, {"max_checks": 501}, {"max_checks": True},
                      {"start_seconds": 2, "end_seconds": 1}, {"start_date": "2026-12-01", "end_date": "2026-11-01"}):
            assert client.post("/count-events", json={"query": "red", **extra}).status_code == 422, extra
        assert client.post("/count-events", json={"query": "  "}).status_code == 422
        assert client.post("/count-events", json={"query": "red", "recording_ids": [str(uuid4())]}).status_code == 404


def test_count_events_merges_overlapping_occurrences(database_url, tmp_path):
    colors = _colors_video(tmp_path)
    with endpoint([(200, envelope(_match(8.0, 9.0, "A red frame."))),
                   (200, envelope(_match(8.5, 9.5, "Still red."))),
                   (200, envelope(NO_MATCH))]) as (url, calls):
        settings = Settings(database_url, tmp_path, qwen_base_url=url)
        with TestClient(create_app(settings)) as client:
            imported = client.post("/imports", json={"path": colors.name}).json()["jobs"][0]
            assert process_one(settings)
            recording = client.get(f"/jobs/{imported['id']}").json()["result"]["recording_id"]
            response = client.post("/count-events", json={"query": "a red image",
                                                           "recording_ids": [recording], "max_checks": 10})
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["count"] == 1, data
            assert data["partitions"] == {"total": 3, "checked": 3, "uncertain": 0,
                                          "skipped_undated": 0, "complete": True}
            assert data["events"][0]["start_seconds"] == 8.0
            assert data["events"][0]["end_seconds"] == 9.5
            assert len(data["events"][0]["verification_ids"]) == 2
            assert len(calls) == 3
            assert data["stop_reason"] == "scope_exhausted"
            for verification_id in data["events"][0]["verification_ids"]:
                assert client.get(f"/verifications/{verification_id}").status_code == 200


def test_count_events_keeps_separate_occurrences(database_url, tmp_path):
    colors = _colors_video(tmp_path)
    with endpoint([(200, envelope(_match(5.0, 7.0, "A red frame."))),
                   (200, envelope(NO_MATCH)),
                   (200, envelope(_match(20.0, 21.0, "Red again.")))]) as (url, calls):
        settings = Settings(database_url, tmp_path, qwen_base_url=url)
        with TestClient(create_app(settings)) as client:
            imported = client.post("/imports", json={"path": colors.name}).json()["jobs"][0]
            assert process_one(settings)
            recording = client.get(f"/jobs/{imported['id']}").json()["result"]["recording_id"]
            data = client.post("/count-events", json={"query": "a red image",
                                                      "recording_ids": [recording], "max_checks": 10}).json()
            assert data["count"] == 2, data
            spans = sorted((event["start_seconds"], event["end_seconds"]) for event in data["events"])
            assert spans == [(5.0, 7.0), (20.0, 21.0)]
            assert len(calls) == 3


def test_count_events_reports_partial_scans(database_url, tmp_path):
    colors = _colors_video(tmp_path)
    with endpoint([(200, envelope(_match(5.0, 7.0, "A red frame.")))]) as (url, calls):
        settings = Settings(database_url, tmp_path, qwen_base_url=url)
        with TestClient(create_app(settings)) as client:
            imported = client.post("/imports", json={"path": colors.name}).json()["jobs"][0]
            assert process_one(settings)
            recording = client.get(f"/jobs/{imported['id']}").json()["result"]["recording_id"]
            data = client.post("/count-events", json={"query": "a red image",
                                                      "recording_ids": [recording], "max_checks": 1}).json()
            assert data["count"] == 1
            assert data["partitions"] == {"total": 3, "checked": 1, "uncertain": 0,
                                          "skipped_undated": 0, "complete": False}
            assert data["stop_reason"] == "budget_exhausted"
            assert "not proven absent" in data["honesty_note"]
            assert len(calls) == 1


def test_count_events_reports_uncertain_partitions(database_url, tmp_path):
    colors = _colors_video(tmp_path)
    with endpoint([(200, envelope(_match(5.0, 7.0, "A red frame."))),
                   (200, envelope(UNCLEAR)),
                   (200, envelope(UNCLEAR))]) as (url, calls):
        settings = Settings(database_url, tmp_path, qwen_base_url=url)
        with TestClient(create_app(settings)) as client:
            imported = client.post("/imports", json={"path": colors.name}).json()["jobs"][0]
            assert process_one(settings)
            recording = client.get(f"/jobs/{imported['id']}").json()["result"]["recording_id"]
            data = client.post("/count-events", json={"query": "a red image",
                                                      "recording_ids": [recording], "max_checks": 10}).json()
            assert data["count"] == 1
            assert data["partitions"]["uncertain"] == 2
            assert data["partitions"]["complete"] is True
            assert len(calls) == 3


def test_count_events_skips_undated_recordings_in_date_scope(database_url, tmp_path):
    colors = _colors_video(tmp_path)
    with endpoint([]) as (url, calls):
        settings = Settings(database_url, tmp_path, qwen_base_url=url)
        with TestClient(create_app(settings)) as client:
            imported = client.post("/imports", json={"path": colors.name}).json()["jobs"][0]
            assert process_one(settings)
            recording = client.get(f"/jobs/{imported['id']}").json()["result"]["recording_id"]
            data = client.post("/count-events", json={"query": "a red image", "recording_ids": [recording],
                                                      "start_date": "2026-11-19", "end_date": "2026-11-19",
                                                      "max_checks": 10}).json()
            assert data["count"] == 0
            assert data["partitions"]["total"] == 0
            assert data["partitions"]["skipped_undated"] == 1
            assert data["partitions"]["checked"] == 0
            assert len(calls) == 0
