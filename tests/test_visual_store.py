import hashlib
from pathlib import Path

import psycopg
import pytest

from video_search import store


SPEC = {
    "model_id": "test/image-text", "revision": "pinned-test-revision", "dimensions": 768,
    "preprocess_version": "test-v1", "sampling_version": "test-v1",
    "frames_per_window": 3, "runtime": "cpu-float32",
}


def vector(axis=0):
    result = [0.0] * 768
    result[axis] = 1.0
    return result


def recording(url, path="sample.mp4", windows=((0, 10), (8, 18))):
    store.enqueue(url, path, 123, 456)
    job = store.claim_job(url)
    assert job["kind"] == "import"
    return store.complete_job(url, str(job["id"]), str(job["lease_token"]),
                              hashlib.sha256(path.encode()).hexdigest(),
                              {"duration_seconds": 18.0, "source_start_seconds": 5.0}, list(windows))


def samples(start, end):
    return [{"requested_seconds": point, "source_seconds": point, "pts_seconds": point + 5.0}
            for point in (start + (end - start) * fraction for fraction in (0.2, 0.5, 0.8))]


def save(url, job, start, end, axis=0):
    store.save_visual_window(url, str(job["id"]), str(job["lease_token"]), start, end, samples(start, end), vector(axis))


def expire(url, job):
    with psycopg.connect(url) as conn:
        conn.execute("UPDATE jobs SET lease_until = clock_timestamp() - interval '1 second' WHERE id = %s", (job["id"],))


def test_visual_dedupe_checkpoint_resume_and_publication(database_url):
    item = recording(database_url)
    first = store.enqueue_visual(database_url, item, SPEC)
    assert store.enqueue_visual(database_url, item, dict(reversed(list(SPEC.items()))))["id"] == first["id"]
    build_id = str(first["index_build_id"])
    assert store.get_recording(database_url, item)["metadata"]["search_index_status"] == "partial"
    job = store.claim_job(database_url)
    save(database_url, job, 0, 10)
    save(database_url, job, 0, 10)
    assert store.get_visual_build(database_url, build_id)["completed_windows"] == 1
    assert store.pending_visual_windows(database_url, build_id) == [{"start_seconds": 8.0, "end_seconds": 18.0}]
    with pytest.raises(ValueError, match="incomplete"):
        store.finish_visual_job(database_url, str(job["id"]), str(job["lease_token"]))
    assert store.search_visual(database_url, SPEC, vector())["results"] == []
    expire(database_url, job)
    replacement = store.claim_job(database_url)
    with pytest.raises(store.LeaseLost):
        save(database_url, job, 8, 18)
    save(database_url, replacement, 8, 18)
    assert store.finish_visual_job(database_url, str(replacement["id"]), str(replacement["lease_token"])) == build_id
    assert store.get_recording(database_url, item)["metadata"]["search_index_status"] == "ready"
    assert store.get_job(database_url, str(first["id"]))["result"] == {"build_id": build_id}
    assert store.get_visual_build(database_url, build_id)["state"] == "ready"


def test_exact_search_filters_and_space_isolation(database_url):
    one = recording(database_url, "one.mp4")
    two = recording(database_url, "two.mp4")
    for item, axis in ((one, 0), (two, 1)):
        store.enqueue_visual(database_url, item, SPEC)
        job = store.claim_job(database_url)
        save(database_url, job, 0, 10, axis)
        save(database_url, job, 8, 18, axis)
        store.finish_visual_job(database_url, str(job["id"]), str(job["lease_token"]))
    found = store.search_visual(database_url, SPEC, vector(), limit=4)
    assert len(found["results"]) == 4
    assert str(found["results"][0]["recording_id"]) == one
    assert found["results"][0]["similarity"] == pytest.approx(1.0)
    assert found["coverage"]["ready_recordings"] == 2
    filtered = store.search_visual(database_url, SPEC, vector(), recording_ids=[two], start_seconds=10, end_seconds=18)
    assert len(filtered["results"]) == 1
    assert str(filtered["results"][0]["recording_id"]) == two
    assert filtered["results"][0]["start_seconds"] == 8
    assert filtered["coverage"]["total_recordings"] == 1
    assert store.search_visual(database_url, {**SPEC, "revision": "other"}, vector())["results"] == []
    assert store.search_visual(database_url, SPEC, vector(), recording_ids=[])["coverage"]["total_recordings"] == 0


def test_visual_failure_retry_keeps_checkpoint(database_url):
    item = recording(database_url)
    queued = store.enqueue_visual(database_url, item, SPEC)
    job = store.claim_job(database_url)
    save(database_url, job, 0, 10)
    assert store.fail_job(database_url, str(job["id"]), str(job["lease_token"]), {"code": "test_failure"})
    assert store.get_visual_build(database_url, str(queued["index_build_id"]))["state"] == "failed"
    assert store.get_recording(database_url, item)["metadata"]["search_index_status"] == "failed"
    assert store.retry_job(database_url, str(job["id"]))["state"] == "queued"
    new = store.claim_job(database_url)
    assert store.get_visual_build(database_url, str(queued["index_build_id"]))["completed_windows"] == 1
    save(database_url, new, 8, 18)
    store.finish_visual_job(database_url, str(new["id"]), str(new["lease_token"]))


def test_visual_validation_and_expired_finish(database_url):
    item = recording(database_url)
    store.enqueue_visual(database_url, item, SPEC)
    job = store.claim_job(database_url)
    bad_samples = samples(0, 10)
    bad_samples[0]["pts_seconds"] = 200
    with pytest.raises(ValueError, match="PTS"):
        store.save_visual_window(database_url, str(job["id"]), str(job["lease_token"]), 0, 10, bad_samples, vector())
    with pytest.raises(ValueError, match="768"):
        store.search_visual(database_url, SPEC, [1.0])
    with pytest.raises(ValueError, match="unit length"):
        store.search_visual(database_url, SPEC, [0.0] * 768)
    with pytest.raises(ValueError, match="finite"):
        store.search_visual(database_url, SPEC, [float("nan")] + [0.0] * 767)
    with pytest.raises(ValueError, match="after its start"):
        store.search_visual(database_url, SPEC, vector(), start_seconds=5, end_seconds=2)
    with pytest.raises(ValueError, match="registered"):
        save(database_url, job, 1, 2)
    save(database_url, job, 0, 10)
    save(database_url, job, 8, 18)
    expire(database_url, job)
    with pytest.raises(store.LeaseLost):
        store.finish_visual_job(database_url, str(job["id"]), str(job["lease_token"]))
    assert store.search_visual(database_url, SPEC, vector())["results"] == []


def test_v1_migration_preserves_import_data(database_url):
    item = recording(database_url)
    with psycopg.connect(database_url) as conn:
        conn.execute("ALTER TABLE jobs DROP COLUMN auto_description_spec, DROP COLUMN original_filename")
        conn.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS description_build_id")
        conn.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS transcript_build_id")
        conn.execute("DROP TABLE IF EXISTS verification_runs, description_windows, transcript_segments")
        conn.execute("DROP TABLE IF EXISTS description_builds, transcript_builds")
        conn.execute("DROP TABLE visual_windows")
        conn.execute("ALTER TABLE jobs DROP COLUMN index_build_id, DROP COLUMN kind")
        conn.execute("DROP TABLE visual_builds")
        conn.execute("UPDATE schema_version SET version = 1")
    store.init_db(database_url)
    assert store.ready(database_url)
    assert store.get_recording(database_url, item)["windows_count"] == 2
    assert store.list_jobs(database_url)[0]["kind"] == "import"
    assert store.enqueue_visual(database_url, item, SPEC)["kind"] == "visual"


def test_incomplete_coverage_obeys_time_filter(database_url):
    item = recording(database_url)
    store.enqueue_visual(database_url, item, SPEC)
    inside = store.search_visual(database_url, SPEC, vector(), start_seconds=2, end_seconds=3)
    assert inside["coverage"]["incomplete_builds_count"] == 1
    outside = store.search_visual(database_url, SPEC, vector(), start_seconds=100, end_seconds=110)
    assert outside["coverage"]["incomplete_builds"] == []
    assert outside["coverage"]["incomplete_builds_count"] == 0
