"""The audio stream's recorded origin and how transcript times use it."""

import math
import subprocess

from fastapi.testclient import TestClient
import pytest

from video_search import media, speech, store
from video_search.api import create_app
from video_search.config import Settings
from video_search.worker import process_one


UNIT_VECTOR_384 = [1.0] + [0.0] * 383


def _sine_color_video(path):
    """A color video with a silent sine audio track, muxed like the speech fixtures."""
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x64:r=4:d=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-map", "0:v", "-map", "1:a", "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(path),
    ], check=True, capture_output=True, timeout=60)
    return path


def test_probe_records_audio_origin(tmp_path):
    metadata = media.probe(_sine_color_video(tmp_path / "silent.mp4"))
    assert metadata["has_audio"] is True
    assert metadata["audio_start_seconds"] is not None
    assert math.isfinite(metadata["audio_start_seconds"]) and metadata["audio_start_seconds"] >= 0
    assert isinstance(metadata["audio_stream_index"], int)
    assert metadata["audio_stream_index"] != metadata["video_stream_index"]
    assert metadata["duration_seconds"] > 0
    assert speech.audio_stream_origin(metadata["audio_start_seconds"]) is not None


def test_probe_records_nonzero_audio_origin(tmp_path):
    # The audio stream starts ~5 source seconds in; the video stream starts at zero.
    path = tmp_path / "shifted.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x64:r=4:d=8",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-map", "0:v", "-map", "1:a",
        "-af", "asetpts=PTS+5/TB", "-c:v", "mpeg4", "-c:a", "aac", str(path),
    ], check=True, capture_output=True, timeout=60)
    metadata = media.probe(path)
    assert metadata["has_audio"] is True
    assert metadata["audio_start_seconds"] == pytest.approx(5, abs=0.25)
    assert metadata["source_start_seconds"] == pytest.approx(0)
    assert speech.asr_spec(metadata["audio_start_seconds"])["origin_rule"] == "audio-stream-origin-corrected-v2"


def test_probe_without_audio_records_no_origin(video_file):
    metadata = media.probe(video_file)
    assert metadata["has_audio"] is False
    assert "audio_start_seconds" not in metadata
    assert "audio_stream_index" not in metadata


@pytest.mark.parametrize("value", [None, -0.5, float("nan"), float("inf"), "not-a-number"])
def test_unusable_probe_origin_keeps_assumed_zero_rule(value):
    assert speech.audio_stream_origin(value) is None
    assert speech.asr_spec(value)["origin_rule"] == "audio-stream-start-assumed-zero-v1"


def test_recorded_origin_selects_the_corrected_rule():
    base = speech.asr_spec()
    assert base["origin_rule"] == "audio-stream-start-assumed-zero-v1"
    corrected = speech.asr_spec(0.0)
    assert corrected["origin_rule"] == "audio-stream-origin-corrected-v2"
    assert {key: value for key, value in corrected.items() if key != "origin_rule"} == \
        {key: value for key, value in base.items() if key != "origin_rule"}
    assert speech.audio_stream_origin(1.25) == pytest.approx(1.25)


def test_store_accepts_offset_corrected_times(database_url, tmp_path):
    path = _sine_color_video(tmp_path / "silent.mp4")
    settings = Settings(database_url, tmp_path)
    with TestClient(create_app(settings)) as client:
        queued = client.post("/imports", json={"path": path.name}).json()["jobs"][0]
        assert process_one(settings)
        recording = client.get(f"/jobs/{queued['id']}").json()["result"]["recording_id"]
        audio_start = client.get(f"/recordings/{recording}").json()["metadata"]["audio_start_seconds"]
    origin = speech.audio_stream_origin(audio_start)
    assert origin is not None
    job = store.enqueue_transcript(database_url, recording, speech.asr_spec(audio_start))
    claimed = store.claim_job(database_url)
    assert str(claimed["id"]) == str(job["id"])
    # A Whisper segment at 0.1-0.9 in an audio stream that starts at `origin` source seconds:
    store.save_transcript_segment(database_url, str(claimed["id"]), str(claimed["lease_token"]),
                                  0.1 + origin, 0.9 + origin, "the delivery person spoke", UNIT_VECTOR_384)
    build = store.get_transcript_build(database_url, str(claimed["transcript_build_id"]))
    assert build["completed_segments"] == 1
    assert build["spec"]["origin_rule"] == "audio-stream-origin-corrected-v2"
