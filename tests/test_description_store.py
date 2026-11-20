import hashlib

import psycopg
import pytest

from video_search import store


SPEC = {
    "model_id": "test/qwen", "revision": "test-revision", "dimensions": 384,
    "preprocess_version": "test-v1", "sampling_version": "test-v1",
    "frames_per_window": 8, "runtime": "test-endpoint", "text_model": "test-text-v1",
}


def vector(axis=0):
    return [1.0 if i == axis else 0.0 for i in range(384)]


def recording(url, path="sample.mp4"):
    store.enqueue(url, path, 123, 456)
    job = store.claim_job(url)
    return store.complete_job(url, str(job["id"]), str(job["lease_token"]), hashlib.sha256(path.encode()).hexdigest(),
                              {"duration_seconds": 18, "source_start_seconds": 5}, [(0, 10), (8, 18)])


def samples(start, end):
    return [{"requested_seconds": t, "source_seconds": t, "pts_seconds": t + 5}
            for t in (start + (i + .5) * (end - start) / 8 for i in range(8))]


def save(url, job, start=0, end=10, text="A person opens the drawer", axis=0):
    store.save_description_window(url, str(job["id"]), str(job["lease_token"]), start, end,
                                  samples(start, end), {"summary": text}, text, vector(axis))


def publish(url, recording_id, text, axis=0, spec=SPEC):
    queued = store.enqueue_description(url, recording_id, spec)
    job = store.claim_job(url)
    save(url, job, text=text, axis=axis)
    save(url, job, 8, 18, text, axis)
    store.finish_description_job(url, str(job["id"]), str(job["lease_token"]))
    return queued


def expire(url, job):
    with psycopg.connect(url) as conn:
        conn.execute("UPDATE jobs SET lease_until = now() - interval '1 second' WHERE id = %s", (job["id"],))


def test_description_resume_rejects_stale_checkpoint_and_partial_search(database_url):
    item = recording(database_url)
    queued = store.enqueue_description(database_url, item, SPEC)
    assert store.enqueue_description(database_url, item, dict(reversed(list(SPEC.items()))))["id"] == queued["id"]
    build = str(queued["description_build_id"])
    old = store.claim_job(database_url)
    save(database_url, old)
    save(database_url, old)
    assert store.get_description_build(database_url, build)["completed_windows"] == 1
    assert store.pending_description_windows(database_url, build) == [{"start_seconds": 8.0, "end_seconds": 18.0}]
    assert store.search_descriptions(database_url, SPEC, "drawer", vector())["results"] == []
    with pytest.raises(ValueError, match="incomplete"):
        store.finish_description_job(database_url, str(old["id"]), str(old["lease_token"]))
    expire(database_url, old)
    new = store.claim_job(database_url)
    with pytest.raises(store.LeaseLost):
        save(database_url, old, 8, 18)
    save(database_url, new, 8, 18)
    assert store.finish_description_job(database_url, str(new["id"]), str(new["lease_token"])) == build
    assert store.get_recording(database_url, item)["metadata"]["search_index_status"] == "ready"
    assert store.get_description_build(database_url, build)["state"] == "ready"
    assert len(store.search_descriptions(database_url, SPEC, "drawer", vector())["results"]) == 2


def test_description_lexical_dense_fusion_and_scope(database_url):
    one = recording(database_url, "one.mp4")
    two = recording(database_url, "two.mp4")
    publish(database_url, one, "A visitor carries a crimson parcel", axis=0)
    publish(database_url, two, "A worker opens a drawer for ProjectXYZ", axis=1)
    found = store.search_descriptions(database_url, SPEC, "ProjectXYZ", vector(), limit=4)
    assert str(found["results"][0]["recording_id"]) == two
    assert found["results"][0]["lexical_rank"] > 0
    assert found["results"][0]["vector_rank"] >= 1
    assert found["coverage"]["ready_recordings"] == 2
    filtered = store.search_descriptions(database_url, SPEC, "drawer", vector(), recording_ids=[one], start_seconds=10, end_seconds=18)
    assert len(filtered["results"]) == 1
    assert str(filtered["results"][0]["recording_id"]) == one
    assert filtered["results"][0]["start_seconds"] == 8
    assert filtered["coverage"]["ready_windows"] == 1
    assert store.search_descriptions(database_url, {**SPEC, "revision": "other"}, "drawer", vector())["results"] == []
    assert store.search_descriptions(database_url, SPEC, "drawer", vector(), recording_ids=[])["results"] == []


def test_failed_description_retry_preserves_completed_work(database_url):
    item = recording(database_url)
    queued = store.enqueue_description(database_url, item, SPEC)
    job = store.claim_job(database_url)
    save(database_url, job)
    assert store.fail_job(database_url, str(job["id"]), str(job["lease_token"]), {"code": "upstream_error"})
    assert store.get_description_build(database_url, str(queued["description_build_id"]))["state"] == "failed"
    assert store.retry_job(database_url, str(job["id"]))["state"] == "queued"
    new = store.claim_job(database_url)
    assert store.get_description_build(database_url, str(queued["description_build_id"]))["completed_windows"] == 1
    save(database_url, new, 8, 18)
    store.finish_description_job(database_url, str(new["id"]), str(new["lease_token"]))


def test_description_validation_and_coverage(database_url):
    item = recording(database_url)
    store.enqueue_description(database_url, item, SPEC)
    job = store.claim_job(database_url)
    with pytest.raises(ValueError, match="384"):
        store.save_description_window(database_url, str(job["id"]), str(job["lease_token"]), 0, 10, samples(0, 10), {}, "description", [1.0])
    bad = samples(0, 10)
    bad[0]["pts_seconds"] = 100
    with pytest.raises(ValueError, match="PTS"):
        store.save_description_window(database_url, str(job["id"]), str(job["lease_token"]), 0, 10, bad, {}, "description", vector())
    with pytest.raises(ValueError, match="JSON object"):
        store.save_description_window(database_url, str(job["id"]), str(job["lease_token"]), 0, 10, samples(0, 10), {}, "", vector())
    inside = store.search_descriptions(database_url, SPEC, "drawer", vector(), start_seconds=1, end_seconds=2)
    assert inside["coverage"]["incomplete_builds_count"] == 1
    outside = store.search_descriptions(database_url, SPEC, "drawer", vector(), start_seconds=100, end_seconds=110)
    assert outside["coverage"]["incomplete_builds_count"] == 0
    expire(database_url, job)
    with pytest.raises(store.LeaseLost):
        store.finish_description_job(database_url, str(job["id"]), str(job["lease_token"]))


def test_verification_trace_and_source_bounds(database_url):
    item = recording(database_url)
    response = {"status": "match", "intervals": [{"start_seconds": 2, "end_seconds": 4}], "observation": "Drawer opened"}
    saved = store.save_verification(database_url, item, "Who opened the drawer?", 0, 10, SPEC, samples(0, 10), response)
    trace = store.get_verification(database_url, saved)
    assert trace["response"] == response
    assert trace["samples"] == samples(0, 10)
    assert trace["spec"] == SPEC
    with pytest.raises(ValueError, match="leaves the recording"):
        store.save_verification(database_url, item, "drawer", 0, 20, SPEC, samples(0, 20), response)


def test_v2_migration_keeps_recording_and_visual_index(database_url):
    item = recording(database_url)
    with psycopg.connect(database_url) as conn:
        conn.execute("DROP TABLE verification_runs")
        conn.execute("ALTER TABLE jobs DROP COLUMN description_build_id")
        conn.execute("ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check")
        conn.execute("ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check CHECK (kind IN ('import', 'visual'))")
        conn.execute("ALTER TABLE jobs ADD CONSTRAINT jobs_kind_build CHECK ((kind = 'visual') = (index_build_id IS NOT NULL))")
        conn.execute("DROP TABLE description_windows")
        conn.execute("DROP TABLE description_builds")
        conn.execute("UPDATE schema_version SET version = 2")
        conn.execute("ALTER TABLE jobs DROP COLUMN auto_description_spec, DROP COLUMN original_filename")
    store.init_db(database_url)
    assert store.ready(database_url)
    assert store.get_recording(database_url, item)["windows_count"] == 2
    assert store.enqueue_description(database_url, item, SPEC)["kind"] == "description"
