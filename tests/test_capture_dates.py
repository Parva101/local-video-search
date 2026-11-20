from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg
from psycopg.types.json import Jsonb
import pytest

from video_search.api import create_app
from video_search.config import Settings
from video_search import store
from video_search.worker import process_one


FAKE_SPEC = {"model_id": "test-model", "revision": "test-revision", "dimensions": 768,
             "preprocess_version": "t", "sampling_version": "t", "frames_per_window": 3,
             "pooling": "mean", "runtime": "t"}

UNIT_VECTOR = [1.0] + [0.0] * 767


def _import_one(client, settings, video_file):
    job = client.post("/imports", json={"path": video_file.name}).json()["jobs"][0]
    assert process_one(settings)
    return client.get(f"/jobs/{job['id']}").json()["result"]["recording_id"]


def test_capture_date_validation(database_url, tmp_path):
    with TestClient(create_app(Settings(database_url, tmp_path))) as client:
        unknown = str(uuid4())
        assert client.post(f"/recordings/{unknown}/capture-date", json={"capture_date": "2026-11-19"}).status_code == 404
        assert client.post(f"/recordings/{unknown}/capture-date", json={"capture_date": "2026-13-40"}).status_code == 422
        assert client.post("/recordings/capture-dates/from-files", json={"utc_offset_minutes": 2000}).status_code == 422
        assert client.post("/recordings/capture-dates/from-files", json={"utc_offset_minutes": "0"}).status_code == 422
        assert client.post("/search", json={"query": "red", "start_date": "2026-12-01", "end_date": "2026-11-01"}).status_code == 422
        assert client.post("/search", json={"query": "red", "start_date": "not-a-date"}).status_code == 422


def test_capture_date_set_clear_and_bulk(database_url, video_file, tmp_path):
    settings = Settings(database_url, video_file.parent)
    with TestClient(create_app(settings)) as client:
        recording = _import_one(client, settings, video_file)
        listed = client.get("/recordings").json()[0]
        assert listed["capture_date"] is None
        assert listed["capture_date_source"] is None
        response = client.post(f"/recordings/{recording}/capture-date", json={"capture_date": "2026-11-19"})
        assert response.status_code == 200
        assert response.json()["capture_date"] == "2026-11-19"
        assert response.json()["capture_date_source"] == "user"
        # A user-set date is never overwritten by the bulk file-time action.
        bulk = client.post("/recordings/capture-dates/from-files", json={"utc_offset_minutes": 0})
        assert bulk.status_code == 200
        assert bulk.json()["count"] == 0
        cleared = client.post(f"/recordings/{recording}/capture-date", json={"capture_date": None})
        assert cleared.status_code == 200
        assert cleared.json()["capture_date"] is None
        assert cleared.json()["capture_date_source"] is None
        bulk = client.post("/recordings/capture-dates/from-files", json={"utc_offset_minutes": 0})
        assert bulk.json()["count"] == 1
        row = client.get(f"/recordings/{recording}").json()
        expected = datetime.fromtimestamp(row["mtime_ns"] / 1_000_000_000, tz=timezone.utc).date()
        assert row["capture_date"] == expected.isoformat()
        assert row["capture_date_source"] == "file_mtime"


def test_date_scoped_visual_search(database_url, video_file, tmp_path):
    settings = Settings(database_url, video_file.parent)
    with TestClient(create_app(settings)) as client:
        recording = _import_one(client, settings, video_file)
        key = store._visual_key(FAKE_SPEC)
        build_id = str(uuid4())
        with psycopg.connect(database_url) as conn:
            conn.execute(
                "INSERT INTO visual_builds (id, recording_id, config_key, spec, state) VALUES (%s, %s, %s, %s, 'ready')",
                (build_id, recording, key, Jsonb(FAKE_SPEC)))
            conn.execute(
                """INSERT INTO visual_windows (build_id, start_seconds, end_seconds, samples, embedding)
                   VALUES (%s, 0.0, 10.0, %s, %s::vector)""",
                (build_id, Jsonb([]), "[" + ",".join(str(value) for value in UNIT_VECTOR) + "]"))
        no_date = store.search_visual(database_url, FAKE_SPEC, UNIT_VECTOR,
                                      start_date=date(2026, 11, 1), end_date=date(2026, 11, 30))
        assert no_date["results"] == []
        assert no_date["coverage"]["recordings_without_capture_date"] == 1
        assert no_date["coverage"]["total_recordings"] == 1
        assert client.post(f"/recordings/{recording}/capture-date", json={"capture_date": "2026-11-19"}).status_code == 200
        inside = store.search_visual(database_url, FAKE_SPEC, UNIT_VECTOR,
                                     start_date=date(2026, 11, 19), end_date=date(2026, 11, 19))
        assert len(inside["results"]) == 1
        assert inside["coverage"]["recordings_without_capture_date"] == 0
        start_only = store.search_visual(database_url, FAKE_SPEC, UNIT_VECTOR, start_date=date(2026, 11, 19))
        assert len(start_only["results"]) == 1
        start_after = store.search_visual(database_url, FAKE_SPEC, UNIT_VECTOR, start_date=date(2026, 11, 20))
        assert start_after["results"] == []
        outside = store.search_visual(database_url, FAKE_SPEC, UNIT_VECTOR,
                                      start_date=date(2026, 10, 1), end_date=date(2026, 10, 31))
        assert outside["results"] == []
        assert outside["coverage"]["recordings_without_capture_date"] == 0
        unfiltered = store.search_visual(database_url, FAKE_SPEC, UNIT_VECTOR)
        assert len(unfiltered["results"]) == 1
