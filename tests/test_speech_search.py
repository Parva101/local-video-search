from datetime import date
import os
from pathlib import Path
import subprocess
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from video_search.api import create_app
from video_search.config import Settings
from video_search import speech, store
from video_search.worker import process_one


SRT = """1
00:00:00,100 --> 00:00:00,900
The delivery person left a package at the front door.

2
00:00:01,000 --> 00:00:01,900
We discussed the project budget.
"""

VTT = "WEBVTT\n\n00:00.100 --> 00:00.900\nThe delivery person left a package at the front door.\n\n00:01.000 --> 00:01.900\nWe discussed the project budget.\n"

UNIT_VECTOR_384 = [1.0] + [0.0] * 383

FAKE_SPEC = {"source": "subtitle", "format": "srt", "content_sha256": "fixture", "dimensions": 384,
             "text_encoder": "test", "text_encoder_revision": "test", "runtime": "test"}


def _import_one(client, settings, video_file):
    job = client.post("/imports", json={"path": video_file.name}).json()["jobs"][0]
    assert process_one(settings)
    return client.get(f"/jobs/{job['id']}").json()["result"]["recording_id"]


def test_subtitle_parsers():
    srt = speech.parse_srt(SRT, 2.0)
    assert len(srt) == 2
    assert srt[0][0] == pytest.approx(0.1)
    assert srt[0][2] == "The delivery person left a package at the front door."
    vtt = speech.parse_vtt(VTT, 2.0)
    assert len(vtt) == 2 and vtt[1][2] == "We discussed the project budget."
    with pytest.raises(speech.TranscriptError, match="WEBVTT"):
        speech.parse_vtt(SRT, 2.0)
    with pytest.raises(speech.TranscriptError, match="reversed"):
        speech.parse_srt("1\n00:00:02,000 --> 00:00:01,000\nreversed times\n", None)
    with pytest.raises(speech.TranscriptError, match="after the recording"):
        speech.parse_srt("1\n00:00:00,100 --> 00:00:09,900\noutside\n", 2.0)
    with pytest.raises(speech.TranscriptError, match="time line"):
        speech.parse_srt("just text without any cue\n", 2.0)
    assert speech.subtitle_spec("srt", SRT)["content_sha256"] == speech.subtitle_spec("srt", SRT)["content_sha256"]
    assert speech.subtitle_spec("srt", SRT)["content_sha256"] != speech.subtitle_spec("vtt", VTT)["content_sha256"]


def test_subtitle_api_validation(database_url, video_file, tmp_path):
    settings = Settings(database_url, video_file.parent)
    with TestClient(create_app(settings)) as client:
        recording = _import_one(client, settings, video_file)
        assert client.post(f"/recordings/{uuid4()}/subtitles", json={"format": "srt", "content": SRT}).status_code == 404
        assert client.post(f"/recordings/{uuid4()}/transcript-index").status_code == 404
        assert client.post("/recordings/x/subtitles", json={"format": "srt", "content": SRT}).status_code == 422
        assert client.post(f"/recordings/{recording}/subtitles", json={"format": "txt", "content": SRT}).status_code == 422
        assert client.post(f"/recordings/{recording}/subtitles", json={"format": "srt", "content": "no cues here"}).status_code == 422
        assert client.post("/search", json={"query": "red", "path": "speech", "start_date": "2026-12-01",
                                            "end_date": "2026-11-01"}).status_code == 422


def test_store_level_speech_search(database_url, video_file, tmp_path):
    settings = Settings(database_url, video_file.parent)
    with TestClient(create_app(settings)) as client:
        recording = _import_one(client, settings, video_file)
        build_id, created = store.create_ready_transcript(database_url, recording, FAKE_SPEC, [
            (0.1, 0.9, "The delivery person left a package at the front door.", UNIT_VECTOR_384),
            (1.0, 1.9, "We discussed the project budget.", UNIT_VECTOR_384)])
        assert created
        again_id, again_created = store.create_ready_transcript(database_url, recording, FAKE_SPEC, [
            (0.1, 0.9, "The delivery person left a package at the front door.", UNIT_VECTOR_384)])
        assert not again_created and again_id == build_id
        result = store.search_speech(database_url, "package at the front door", UNIT_VECTOR_384)
        assert result["results"], result
        assert "package" in result["results"][0]["text"].lower()
        assert result["coverage"]["total_segments"] == 2
        assert result["coverage"]["ready_recordings"] == 1
        dated = store.search_speech(database_url, "package", UNIT_VECTOR_384,
                                    start_date=date(2026, 1, 1), end_date=date(2026, 1, 2))
        assert dated["results"] == []
        assert dated["coverage"]["recordings_without_capture_date"] == 1
        with pytest.raises(ValueError, match="calendar dates"):
            store.search_speech(database_url, "package", UNIT_VECTOR_384, start_date="2026-01-01")


def test_real_subtitle_search(database_url, video_file, tmp_path):
    if os.environ.get("RUN_MODEL_TESTS") != "1":
        pytest.skip("Set RUN_MODEL_TESTS=1 after downloading the pinned text encoder")
    cache = Path(os.environ.get("MODEL_CACHE", "/models"))
    settings = Settings(database_url, video_file.parent, model_cache=cache)
    with TestClient(create_app(settings)) as client:
        recording = _import_one(client, settings, video_file)
        imported = client.post(f"/recordings/{recording}/subtitles", json={"format": "srt", "content": SRT})
        assert imported.status_code == 200, imported.text
        body = imported.json()
        assert body["created"] and body["segments"] == 2
        repeated = client.post(f"/recordings/{recording}/subtitles", json={"format": "srt", "content": SRT}).json()
        assert not repeated["created"] and repeated["build_id"] == body["build_id"]
        result = client.post("/search", json={"query": "a package at the front door", "path": "speech", "limit": 3})
        assert result.status_code == 200, result.text
        payload = result.json()
        assert payload["result_type"] == "unverified_transcript_matches"
        assert payload["results"], payload
        top = payload["results"][0]
        assert "package" in top["text"].lower()
        assert top["start_seconds"] == pytest.approx(0.1)
        assert top["end_seconds"] == pytest.approx(0.9)
        assert top["source_status"] == "available"
        assert top["media_url"].endswith("/media")


def test_real_asr_transcript(database_url, tmp_path):
    if os.environ.get("RUN_MODEL_TESTS") != "1":
        pytest.skip("Set RUN_MODEL_TESTS=1 after downloading the pinned speech checkpoint")
    cache = Path(os.environ.get("MODEL_CACHE", "/models"))
    spoken = Path(__file__).parent / "fixtures" / "spoken-sample.wav"
    path = tmp_path / "spoken.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x64:r=4:d=5",
        "-i", str(spoken), "-map", "0:v", "-map", "1:a", "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(path),
    ], check=True, capture_output=True, timeout=60)
    settings = Settings(database_url, tmp_path, model_cache=cache)
    with TestClient(create_app(settings)) as client:
        imported = client.post("/imports", json={"path": path.name}).json()["jobs"][0]
        assert process_one(settings)
        recording = client.get(f"/jobs/{imported['id']}").json()["result"]["recording_id"]
        assert client.get(f"/recordings/{recording}").json()["metadata"]["has_audio"] is True
        requested = client.post(f"/recordings/{recording}/transcript-index")
        assert requested.status_code == 202, requested.text
        job = requested.json()
        assert process_one(settings)
        completed = client.get(f"/jobs/{job['id']}").json()
        assert completed["state"] == "succeeded", completed
        build = client.get(f"/transcript-indexes/{job['transcript_build_id']}").json()
        assert build["state"] == "ready"
        assert build["completed_segments"] >= 1
        result = client.post("/search", json={"query": "a package at the front door", "path": "speech", "limit": 3})
        assert result.status_code == 200, result.text
        texts = [item["text"].lower() for item in result.json()["results"]]
        assert any("package" in text for text in texts), texts
