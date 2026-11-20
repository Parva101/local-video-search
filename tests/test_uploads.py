import asyncio
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
import psycopg
import pytest

from video_search import analysis, media, store, uploads
from video_search.config import Settings
from video_search.worker import process_one


class UploadRequest:
    def __init__(self, chunks, length=None, fail=False):
        self.chunks = chunks
        self.headers = {} if length is None else {"content-length": str(length)}
        self.fail = fail

    async def stream(self):
        for chunk in self.chunks:
            yield chunk
        if self.fail:
            raise ConnectionError("Client disconnected during upload")


def save(database_url, tmp_path, content, *, name="sample.mp4", upload_id=None, max_bytes=1024*1024):
    root = tmp_path / "__uploads"
    root.mkdir(exist_ok=True)
    request = content if isinstance(content, UploadRequest) else UploadRequest([content], len(content))
    return asyncio.run(uploads.save_upload(request, root, tmp_path, database_url, analysis.description_spec(), name,
                                          upload_id=upload_id, max_bytes=max_bytes, read_root=root))


def test_upload_queues_description_after_import_without_browser(database_url, video_file):
    uploaded = save(database_url, video_file.parent, video_file.read_bytes())
    assert uploaded["auto_description_spec"] == analysis.description_spec()
    assert uploaded["original_filename"] == "sample.mp4"
    settings = Settings(database_url=database_url, media_root=video_file.parent, upload_read_root=video_file.parent / "__uploads")
    assert process_one(settings)
    completed = store.get_job(database_url, str(uploaded["id"]))
    assert completed["state"] == "succeeded"
    child = store.get_job(database_url, completed["result"]["description_job_id"])
    assert child["state"] == "queued" and child["kind"] == "description"
    assert store.get_description_build(database_url, str(child["description_build_id"]))["spec"] == analysis.description_spec()
    # A second worker can claim the persisted next stage without any browser action.
    assert store.claim_job(database_url)["id"] == child["id"]


def test_upload_retry_is_idempotent_and_rejects_changed_bytes(database_url, video_file):
    identifier = str(uuid4())
    first = save(database_url, video_file.parent, video_file.read_bytes(), upload_id=identifier)
    repeated = save(database_url, video_file.parent, video_file.read_bytes(), upload_id=identifier)
    assert first["id"] == repeated["id"]
    with pytest.raises(HTTPException) as error:
        save(database_url, video_file.parent, b"different", upload_id=identifier)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        save(database_url, video_file.parent, b"different", name="other.mp4", upload_id=identifier)
    assert error.value.status_code == 409
    assert len(store.list_jobs(database_url)) == 1
    assert (media.source_file(video_file.parent, first["source_path"], upload_root=video_file.parent / "__uploads")).read_bytes() == video_file.read_bytes()


@pytest.mark.parametrize("name", ["../test.mp4", "a\\b.mp4", "test.txt", "C:test.mp4", "a\n.mp4", "x"*241+".mp4"])
def test_upload_rejects_unsafe_names(database_url, tmp_path, name):
    with pytest.raises(HTTPException) as error:
        save(database_url, tmp_path, b"bytes", name=name)
    assert error.value.status_code == 422
    assert store.list_jobs(database_url) == []


@pytest.mark.parametrize("upload_request,limit,status", [
    (UploadRequest([b"12345"], 5), 4, 413),
    (UploadRequest([b"12", b"345"]), 4, 413),
    (UploadRequest([b"12"], 4), 8, 422),
    (UploadRequest([b""]), 8, 422),
])
def test_upload_rejects_size_and_cleans_partial_files(database_url, tmp_path, upload_request, limit, status):
    with pytest.raises(HTTPException) as error:
        save(database_url, tmp_path, upload_request, max_bytes=limit)
    assert error.value.status_code == status
    assert not list((tmp_path / "__uploads").rglob("*.part"))
    assert not list((tmp_path / "__uploads").rglob("*.mp4"))
    assert store.list_jobs(database_url) == []


def test_interrupted_upload_releases_lock_and_cleans_partial_file(database_url, tmp_path):
    identifier = str(uuid4())
    with pytest.raises(ConnectionError, match="disconnected"):
        save(database_url, tmp_path, UploadRequest([b"first"], fail=True), upload_id=identifier)
    assert not list((tmp_path / "__uploads").rglob("*.part"))
    assert save(database_url, tmp_path, b"complete", upload_id=identifier)["state"] == "queued"


def test_same_upload_id_cannot_stream_concurrently(database_url, tmp_path):
    identifier = str(uuid4())
    with store.upload_lock(database_url, identifier) as acquired:
        assert acquired
        with pytest.raises(HTTPException) as error:
            save(database_url, tmp_path, b"video", upload_id=identifier)
    assert error.value.status_code == 409


def test_retry_cleans_partial_file_left_by_stopped_process(database_url, tmp_path):
    identifier = str(uuid4())
    directory = tmp_path / "__uploads" / identifier
    directory.mkdir(parents=True)
    (directory / (str(uuid4()) + ".part")).write_bytes(b"interrupted")
    assert save(database_url, tmp_path, b"complete", upload_id=identifier)["state"] == "queued"
    assert not list(directory.glob("*.part"))


def test_corrupt_media_is_visible_as_failed_import(database_url, tmp_path):
    job = save(database_url, tmp_path, b"not a video")
    assert process_one(Settings(database_url=database_url, media_root=tmp_path, upload_read_root=tmp_path / "__uploads"))
    failed = store.get_job(database_url, str(job["id"]))
    assert failed["state"] == "failed" and failed["error"]
    assert store.list_description_builds(database_url) == []


def test_import_and_automatic_index_commit_atomically(database_url):
    job = store.enqueue(database_url, "sample.mp4", 1, 1, auto_description_spec=analysis.description_spec())
    claimed = store.claim_job(database_url)
    with psycopg.connect(database_url) as conn:
        conn.execute("UPDATE jobs SET auto_description_spec = %s WHERE id = %s", (psycopg.types.json.Jsonb({"bad": True}), job["id"]))
    with pytest.raises(ValueError, match="specification"):
        store.complete_job(database_url, str(job["id"]), str(claimed["lease_token"]), "a"*64,
                           {"duration_seconds": 2.0}, [(0, 2)])
    assert store.list_recordings(database_url) == []
    assert store.list_description_builds(database_url) == []
    assert store.get_job(database_url, str(job["id"]))["state"] == "running"


def test_database_failure_keeps_published_upload_for_retry(database_url, tmp_path):
    with psycopg.connect(database_url) as conn:
        conn.execute("""CREATE FUNCTION reject_test_upload() RETURNS trigger LANGUAGE plpgsql AS $$
                       BEGIN RAISE EXCEPTION 'Test database failure'; END $$""")
        conn.execute("CREATE TRIGGER reject_test_upload BEFORE INSERT ON jobs FOR EACH ROW EXECUTE FUNCTION reject_test_upload()")
    identifier = str(uuid4())
    with pytest.raises(psycopg.errors.RaiseException, match="Test database failure"):
        save(database_url, tmp_path, b"complete", upload_id=identifier)
    assert (tmp_path / "__uploads" / identifier / "sample.mp4").read_bytes() == b"complete"
    assert not list((tmp_path / "__uploads").rglob("*.part"))
    with psycopg.connect(database_url) as conn:
        conn.execute("DROP TRIGGER reject_test_upload ON jobs")
    assert save(database_url, tmp_path, b"complete", upload_id=identifier)["state"] == "queued"


def test_v3_migration_preserves_import_and_description_job(database_url):
    imported = store.enqueue(database_url, "old.mp4", 1, 1)
    running = store.claim_job(database_url)
    recording_id = store.complete_job(database_url, str(imported["id"]), str(running["lease_token"]), "b"*64,
                                      {"duration_seconds": 2.0}, [(0, 2)])
    description = store.enqueue_description(database_url, recording_id, analysis.description_spec())
    with psycopg.connect(database_url) as conn:
        conn.execute("ALTER TABLE jobs DROP COLUMN auto_description_spec, DROP COLUMN original_filename")
        conn.execute("UPDATE schema_version SET version = 3")
    store.init_db(database_url)
    assert store.ready(database_url)
    assert store.get_recording(database_url, recording_id)["source_path"] == "old.mp4"
    assert store.get_job(database_url, str(description["id"]))["state"] == "queued"
    assert store.get_job(database_url, str(imported["id"]))["auto_description_spec"] is None
