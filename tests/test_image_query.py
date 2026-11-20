import base64
import io
import os
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from video_search.api import create_app
from video_search.config import Settings
from video_search.frames import QUERY_IMAGE_MAX_BYTES, QUERY_IMAGE_PREPROCESS_VERSION, prepare_query_image
from video_search.media import MediaError
from video_search.worker import process_one


def png_bytes(color="red", size=(64, 64)):
    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_prepare_query_image_rules():
    frame = prepare_query_image(png_bytes("red", (1024, 640)))
    assert frame.mode == "RGB"
    assert frame.size == (512, 320)
    # Small images are never enlarged, matching the ffmpeg decrease rule.
    assert prepare_query_image(png_bytes("blue", (200, 100))).size == (200, 100)
    with pytest.raises(MediaError, match="empty"):
        prepare_query_image(b"")
    with pytest.raises(MediaError, match="decodable"):
        prepare_query_image(b"plain text is not an image")
    with pytest.raises(MediaError, match="larger than the limit"):
        prepare_query_image(b"a" * (QUERY_IMAGE_MAX_BYTES + 1))


def test_image_query_validation(database_url, tmp_path):
    with TestClient(create_app(Settings(database_url, tmp_path))) as client:
        bodies = [
            {"query": "a red frame", "path": "description", "image_base64": b64(png_bytes())},
            {"query": "a red frame", "path": "hybrid", "rerank": True, "image_base64": b64(png_bytes())},
            {"query": "a red frame", "path": "visual", "image_base64": "not valid base64 !!!"},
            {"query": "a red frame", "path": "visual", "image_base64": b64(b"plain text, not an image")},
            {"query": "a red frame", "path": "visual", "image_base64": b64(b"")},
        ]
        for body in bodies:
            response = client.post("/search", json=body)
            assert response.status_code == 422, (body, response.text)
        response = client.post("/evidence-search", json={
            "query": "a red frame", "path": "description", "image_base64": b64(png_bytes()), "limit": 12})
        assert response.status_code == 422


def test_real_image_query_retrieval(database_url, tmp_path):
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
        for color, expected_start, query in (
            ("red", 0.0, "a red image"),
            ("green", 16.0, "a green image"),
        ):
            response = client.post("/search", json={
                "query": query, "path": "visual", "image_base64": b64(png_bytes(color)), "limit": 1})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["query_image"] == {"preprocess_version": QUERY_IMAGE_PREPROCESS_VERSION,
                                            "vector_recipe": "unit-sum-text-image-l2-v1"}
            top = body["results"][0]
            assert top["recording_id"] == recording
            assert top["start_seconds"] == expected_start, (color, body)
            assert top["verified"] is False
        text_only = client.post("/search", json={"query": "a blue image", "limit": 1}).json()
        assert "query_image" not in text_only
        assert text_only["results"][0]["start_seconds"] == 8.0
        scoped = client.post("/search", json={"query": "a red image", "limit": 1,
                                              "start_date": "2026-01-01", "end_date": "2026-01-02"}).json()
        assert scoped["date_scope"] == {"start_date": "2026-01-01", "end_date": "2026-01-02"}
        assert scoped["results"] == []
        assert scoped["coverage"]["recordings_without_capture_date"] == 1
