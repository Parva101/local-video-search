from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from video_search import media, store
from video_search.api import create_app
from video_search.config import Settings
from video_search.worker import process_one


def test_uploaded_source_namespace_cannot_escape_storage(tmp_path):
    library = tmp_path / "library"
    uploaded = tmp_path / "uploads"
    library.mkdir()
    uploaded.mkdir()
    original = library / "sample.mp4"
    original.write_bytes(b"original")
    copy = uploaded / "sample.mp4"
    copy.write_bytes(b"upload")
    assert media.source_file(library, "sample.mp4", upload_root=uploaded) == original
    assert media.source_file(library, "/__uploads/sample.mp4", upload_root=uploaded) == copy
    original_subfolder = library / "__uploads"
    original_subfolder.mkdir()
    nested_original = original_subfolder / "sample.mp4"
    nested_original.write_bytes(b"nested original")
    assert media.source_file(library, "__uploads/sample.mp4", upload_root=uploaded) == nested_original
    assert media.scan_sources(library, "__uploads") == ["__uploads/sample.mp4"]
    for relative in ("/__uploads/../library/sample.mp4", "/__uploads//etc/passwd", "/__uploads/..\\sample.mp4"):
        with pytest.raises(media.MediaError):
            media.source_file(library, relative, upload_root=uploaded)


def test_local_page_config_and_origin_checks(database_url, tmp_path):
    settings = Settings(database_url, tmp_path, vision_provider="gemma", voyager_api_key="private-web-test-key")
    with TestClient(create_app(settings)) as api:
        page = api.get("/")
        assert page.status_code == 200
        assert "text/html" in page.headers["content-type"]
        assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
        assert api.get("/static/app.js").status_code == 200
        config = api.get("/app-config")
        assert config.json()["model"] == "gemma4-31b-it"
        assert len(config.json()["description_config_key"]) == 64
        assert config.json()["uploads_enabled"] is False
        assert config.json()["upload_max_bytes"] == 2 * 1024**3
        assert "private-web-test-key" not in page.text + config.text
        assert api.get("/", headers={"Host": "untrusted.example"}).status_code == 400
        for headers in ({"Origin": "https://untrusted.example"}, {"Sec-Fetch-Site": "cross-site"}):
            blocked = api.post("/imports", json={"path": "."}, headers=headers)
            assert blocked.status_code == 403
            assert blocked.json()["request_id"]
        assert api.post("/uploads?filename=sample.mp4", content=b"test").status_code == 503
        assert api.post("/search", json={"query": "   ", "path": "description"}).status_code == 422


def test_browser_upload_import_and_follow_on_job_survive_refresh(database_url, video_file):
    root = video_file.parent
    upload_root = root / "separate-upload-volume"
    upload_root.mkdir()
    settings = Settings(database_url, root, vision_provider="gemma", voyager_api_key="private-web-test-key",
                        upload_write_root=upload_root, upload_read_root=upload_root)
    upload_id = str(uuid4())
    body = video_file.read_bytes()
    headers = {"Content-Type": "application/octet-stream", "X-Upload-ID": upload_id, "Origin": "http://testserver"}
    with TestClient(create_app(settings)) as api:
        uploaded = api.post("/uploads?filename=sample.mp4", content=body, headers=headers)
        assert uploaded.status_code == 202, uploaded.text
        job = uploaded.json()["job"]
        repeated = api.post("/uploads?filename=sample.mp4", content=body, headers=headers)
        assert repeated.status_code == 202, repeated.text
        assert repeated.json()["job"]["id"] == job["id"]
        assert api.get("/app-config").json()["uploads_enabled"]
    assert process_one(settings)
    with TestClient(create_app(settings)) as refreshed:
        imported = refreshed.get(f"/jobs/{job['id']}").json()
        assert imported["state"] == "succeeded", imported
        recording_id = imported["result"]["recording_id"]
        builds = refreshed.get(f"/description-indexes?recording_id={recording_id}").json()
        assert len(builds) == 1
        assert builds[0]["state"] == "queued"
        assert builds[0]["spec"]["model_id"] == "gemma4-31b-it"
        playback = refreshed.get(f"/recordings/{recording_id}/media", headers={"Range": "bytes=0-31"})
        assert playback.status_code == 206
        assert playback.content == body[:32]
        assert len(store.list_jobs(database_url)) == 2
        assert Path(upload_root, job["source_path"].removeprefix(media.UPLOAD_PREFIX)).read_bytes() == body
        assert not (root / "__uploads").exists()
