from concurrent.futures import ThreadPoolExecutor
import psycopg
import pytest

from video_search import store


def expire(url, job):
    with psycopg.connect(url) as conn:
        conn.execute("UPDATE jobs SET lease_until = clock_timestamp() - interval '1 second' WHERE id = %s", (job["id"],))


def test_duplicate_import_and_complete(database_url):
    first = store.enqueue(database_url, "sample.mp4", 123, 456)
    assert store.enqueue(database_url, "sample.mp4", 123, 456)["id"] == first["id"]
    claimed = store.claim_job(database_url)
    recording = store.complete_job(database_url, str(claimed["id"]), str(claimed["lease_token"]),
                                   "a" * 64, {"duration_seconds": 18.0}, [(0, 10), (8, 18)])
    assert store.get_job(database_url, str(first["id"]))["state"] == "succeeded"
    assert store.get_recording(database_url, recording)["windows_count"] == 2
    assert store.list_windows(database_url, recording, limit=1, offset=1) == [{"start_seconds": 8.0, "end_seconds": 18.0}]


def test_two_workers_cannot_claim_same_job(database_url):
    store.enqueue(database_url, "sample.mp4", 1, 1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(pool.map(lambda _: store.claim_job(database_url), range(2)))
    assert sum(item is not None for item in claimed) == 1


def test_expired_worker_cannot_write(database_url):
    store.enqueue(database_url, "sample.mp4", 1, 1)
    old = store.claim_job(database_url)
    expire(database_url, old)
    assert not store.heartbeat(database_url, str(old["id"]), str(old["lease_token"]))
    new = store.claim_job(database_url)
    assert new["attempts"] == 2
    assert new["lease_token"] != old["lease_token"]
    with pytest.raises(store.LeaseLost):
        store.complete_job(database_url, str(old["id"]), str(old["lease_token"]),
                           "b" * 64, {"duration_seconds": 1.0}, [(0, 1)])
    assert not store.fail_job(database_url, str(old["id"]), str(old["lease_token"]), {"code": "old_error"})
    assert store.list_recordings(database_url) == []
    store.complete_job(database_url, str(new["id"]), str(new["lease_token"]),
                       "b" * 64, {"duration_seconds": 1.0}, [(0, 1)])


def test_dead_worker_attempt_limit(database_url):
    job = store.enqueue(database_url, "sample.mp4", 1, 1)
    for attempt in range(3):
        claimed = store.claim_job(database_url)
        assert claimed["attempts"] == attempt + 1
        expire(database_url, claimed)
    assert store.claim_job(database_url) is None
    assert store.get_job(database_url, str(job["id"]))["state"] == "failed"


def test_duplicate_content_keeps_distinct_occurrences(database_url):
    for path in ("camera-a.mp4", "camera-b.mp4"):
        store.enqueue(database_url, path, 1, 1)
        job = store.claim_job(database_url)
        store.complete_job(database_url, str(job["id"]), str(job["lease_token"]),
                           "c" * 64, {"duration_seconds": 1.0}, [(0, 1)])
    assert len(store.list_recordings(database_url)) == 2
    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT count(*) FROM assets").fetchone()[0] == 1


def test_invalid_completion_is_atomic(database_url):
    store.enqueue(database_url, "sample.mp4", 1, 1)
    job = store.claim_job(database_url)
    with pytest.raises(ValueError):
        store.complete_job(database_url, str(job["id"]), str(job["lease_token"]),
                           "d" * 64, {"duration_seconds": 1.0}, [(0, 2)])
    assert store.list_recordings(database_url) == []
    assert store.get_job(database_url, str(job["id"]))["state"] == "running"


def test_schema_version_mismatch_fails(database_url):
    with psycopg.connect(database_url) as conn:
        conn.execute("UPDATE schema_version SET version = 999")
    with pytest.raises(RuntimeError, match="Unsupported schema"):
        store.init_db(database_url)


def test_library_identity_cannot_change(database_url):
    store.bind_library(database_url, "library-a")
    store.bind_library(database_url, "library-a")
    with pytest.raises(RuntimeError, match="different video directory"):
        store.bind_library(database_url, "library-b")
