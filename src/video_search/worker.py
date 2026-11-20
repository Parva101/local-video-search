import argparse
import logging
from pathlib import Path
import signal
import subprocess
import tempfile
import time
from threading import Event, Thread

import psycopg

from video_search import media, store
from video_search.config import Settings
from video_search.log import configure_logging
from video_search.encoder import EncoderError, SPEC, get_encoder
from video_search import analysis, speech
from video_search.speech import TranscriptError, get_asr
from video_search.text_encoder import get_text_encoder
from video_search.vlm import VLMError

logger = logging.getLogger("video_search")


def process_description(settings, job, check_lease):
    job_id, token = str(job["id"]), str(job["lease_token"])
    build_id = str(job["description_build_id"])
    build = store.get_description_build(settings.database_url, build_id)
    if build["spec"] != analysis.description_spec(settings):
        raise VLMError("incompatible_index", "Worker cannot build this description specification")
    model = analysis.client(settings)
    encoder = get_text_encoder(settings.model_cache)
    recording = store.get_recording(settings.database_url, str(build["recording_id"]))
    path = analysis.source(settings, recording, check_lease)
    while pending := store.pending_description_windows(settings.database_url, build_id, limit=32):
        for window in pending:
            check_lease()
            start, end = window["start_seconds"], window["end_seconds"]
            images, samples = analysis.inspect_frames(path, recording["metadata"], start, end, check_lease)
            try:
                payload = model.describe(images, samples, start, end)
            finally:
                for image in images:
                    image.close()
            # Dense search represents the summary; lexical search also covers listed actions/objects.
            vector = encoder.text(payload["summary"])
            searchable = " ".join([payload["summary"], *payload["actions"], *payload["objects"]])
            if media.fingerprint(path) != (recording["size"], recording["mtime_ns"]):
                raise media.MediaError("source_changed", "Source changed during description indexing")
            check_lease()
            store.save_description_window(settings.database_url, job_id, token, start, end, samples,
                                          payload, searchable, vector)
            logger.info("description_window_saved", extra={"fields": {"job_id": job_id, "build_id": build_id,
                        "start_seconds": start, "end_seconds": end, "request_id": payload["_trace"]["request_id"]}})
    analysis.source(settings, recording, check_lease)
    check_lease()
    store.finish_description_job(settings.database_url, job_id, token)


def process_visual(settings, job, check_lease):
    from video_search.frames import sample_window

    job_id, token = str(job["id"]), str(job["lease_token"])
    build_id = str(job["index_build_id"])
    build = store.get_visual_build(settings.database_url, build_id)
    if build["spec"] != SPEC:
        raise EncoderError("incompatible_index", "This worker does not support the requested index specification")
    recording = store.get_recording(settings.database_url, str(build["recording_id"]))
    path = media.source_file(settings.media_root, recording["source_path"], upload_root=settings.upload_read_root)
    expected = (job["expected_size"], job["expected_mtime_ns"])
    if media.fingerprint(path) != expected or media.hash_source(path, check_lease) != recording["sha256"]:
        raise media.MediaError("source_changed", "Source differs from the imported recording", path=job["source_path"])
    model = get_encoder(settings.model_cache)
    while pending := store.pending_visual_windows(settings.database_url, build_id, limit=32):
        for window in pending:
            check_lease()
            started = time.perf_counter()
            start, end = window["start_seconds"], window["end_seconds"]
            images, samples = sample_window(path, recording["metadata"], start, end, check_lease)
            try:
                vector = model.images(images)
            finally:
                for image in images:
                    image.close()
            check_lease()
            if media.fingerprint(path) != expected:
                raise media.MediaError("source_changed", "Source changed during indexing", path=job["source_path"])
            store.save_visual_window(settings.database_url, job_id, token, start, end, samples, vector)
            logger.info("visual_window_saved", extra={"fields": {
                "job_id": job_id, "build_id": build_id, "start_seconds": start,
                "end_seconds": end, "frames": len(samples), "seconds": time.perf_counter()-started,
            }})
    if media.fingerprint(path) != expected or media.hash_source(path, check_lease) != recording["sha256"]:
        raise media.MediaError("source_changed", "Source changed before indexing completed", path=job["source_path"])
    check_lease()
    store.finish_visual_job(settings.database_url, job_id, token)


def process_transcript(settings, job, check_lease):
    job_id, token = str(job["id"]), str(job["lease_token"])
    build_id = str(job["transcript_build_id"])
    build = store.get_transcript_build(settings.database_url, build_id)
    recording = store.get_recording(settings.database_url, str(build["recording_id"]))
    audio_start = recording["metadata"].get("audio_start_seconds")
    if build["spec"] != speech.asr_spec(audio_start):
        raise TranscriptError("incompatible_index", "Worker cannot build this transcript specification")
    if not recording["metadata"].get("has_audio"):
        raise media.MediaError("no_audio", "This recording has no audio stream to transcribe",
                               path=job["source_path"])
    path = media.source_file(settings.media_root, recording["source_path"], upload_root=settings.upload_read_root)
    expected = (job["expected_size"], job["expected_mtime_ns"])
    if media.fingerprint(path) != expected:
        raise media.MediaError("source_changed", "Source differs from the imported recording", path=job["source_path"])
    model = get_asr(settings.model_cache)
    encoder = get_text_encoder(settings.model_cache)
    started = time.perf_counter()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        wav = handle.name
    try:
        subprocess.run([
            "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", str(path),
            "-vn", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", wav,
        ], check=True, capture_output=True, timeout=600)
        check_lease()
        segments = model.transcribe(wav)
    finally:
        Path(wav).unlink(missing_ok=True)
    check_lease()
    if not segments:
        raise TranscriptError("empty_transcript", "The speech model returned no usable segments")
    # Chunk ends can round slightly past the audio; clamp to the imported duration.
    duration = float(recording["metadata"]["duration_seconds"])
    # Whisper times are audio-stream-relative; add the recorded origin to get source-relative times.
    origin = speech.audio_stream_origin(audio_start)
    if origin is None:
        logger.warning("transcript_origin_assumed_zero", extra={"fields": {
            "job_id": job_id, "build_id": build_id, "audio_start_seconds": audio_start}})
        origin = 0.0
    segments = [(start + origin, min(end + origin, duration), text)
                for start, end, text in segments if start + origin < duration]
    if not segments:
        raise TranscriptError("empty_transcript", "No transcribed segment lies inside the recording duration")
    if media.fingerprint(path) != expected:
        raise media.MediaError("source_changed", "Source changed during transcription", path=job["source_path"])
    for start, end, text in segments:
        check_lease()
        vector = encoder.text(text)
        store.save_transcript_segment(settings.database_url, job_id, token, start, end, text, vector)
    logger.info("transcript_segments_saved", extra={"fields": {
        "job_id": job_id, "build_id": build_id, "segments": len(segments),
        "audio_seconds": round(segments[-1][1], 2), "seconds": round(time.perf_counter() - started, 1)}})
    check_lease()
    store.finish_transcript_job(settings.database_url, job_id, token)


def process_one(settings: Settings, lease_seconds: int = 60) -> bool:
    job = store.claim_job(settings.database_url, lease_seconds)
    if job is None:
        return False
    job_id, token = str(job["id"]), str(job["lease_token"])
    stopped = Event()
    lease_errors: list[Exception] = []

    def keep_lease():
        while not stopped.wait(lease_seconds / 3):
            try:
                if not store.heartbeat(settings.database_url, job_id, token, lease_seconds):
                    raise store.LeaseLost("Job lease expired or was replaced")
            except (psycopg.Error, store.LeaseLost) as exc:
                lease_errors.append(exc)
                return

    def check_lease():
        if lease_errors:
            raise lease_errors[0]

    thread = Thread(target=keep_lease, daemon=True)
    thread.start()
    logger.info("job_started", extra={"fields": {"job_id": job_id, "source_path": job["source_path"], "kind": job["kind"]}})
    try:
        if job["kind"] == "visual":
            process_visual(settings, job, check_lease)
            logger.info("visual_index_succeeded", extra={"fields": {"job_id": job_id, "build_id": job["index_build_id"]}})
            return True
        if job["kind"] == "description":
            process_description(settings, job, check_lease)
            logger.info("description_index_succeeded", extra={"fields": {"job_id": job_id, "build_id": job["description_build_id"]}})
            return True
        if job["kind"] == "transcript":
            process_transcript(settings, job, check_lease)
            logger.info("transcript_index_succeeded", extra={"fields": {"job_id": job_id, "build_id": job["transcript_build_id"]}})
            return True
        path = media.source_file(settings.media_root, job["source_path"], upload_root=settings.upload_read_root)
        expected = (job["expected_size"], job["expected_mtime_ns"])
        if media.fingerprint(path) != expected:
            raise media.MediaError("source_changed", "Source changed after it was queued", path=job["source_path"])
        sha256 = media.hash_source(path, check_lease)
        metadata = media.probe(path)
        if media.fingerprint(path) != expected:
            raise media.MediaError("source_changed", "Source changed during import", path=job["source_path"])
        check_lease()
        metadata["pipeline_version"] = "import-v1"
        metadata["window_length_seconds"] = 10
        metadata["window_overlap_seconds"] = 2
        metadata["search_index_status"] = "not_built"
        if job["original_filename"] is not None:
            metadata["original_filename"] = job["original_filename"]
        recording_id = store.complete_job(
            settings.database_url, job_id, token, sha256, metadata,
            media.windows(metadata["duration_seconds"]),
        )
        logger.info("import_succeeded", extra={"fields": {"job_id": job_id, "recording_id": recording_id}})
    except media.MediaError as exc:
        error = {"code": exc.code, "message": str(exc), "details": exc.details}
        owned = store.fail_job(settings.database_url, job_id, token, error)
        logger.error("import_failed", extra={"fields": {"job_id": job_id, "error": error, "lease_owned": owned}})
    except EncoderError as exc:
        error = {"code": exc.code, "message": str(exc), "details": exc.details}
        owned = store.fail_job(settings.database_url, job_id, token, error)
        logger.error("visual_index_failed", extra={"fields": {"job_id": job_id, "error": error, "lease_owned": owned}})
    except VLMError as exc:
        error = {"code": exc.code, "message": str(exc), "details": exc.details}
        owned = store.fail_job(settings.database_url, job_id, token, error)
        logger.error("description_index_failed", extra={"fields": {"job_id": job_id, "error": error, "lease_owned": owned}})
    except TranscriptError as exc:
        error = {"code": exc.code, "message": str(exc), "details": exc.details}
        owned = store.fail_job(settings.database_url, job_id, token, error)
        logger.error("transcript_index_failed", extra={"fields": {"job_id": job_id, "error": error, "lease_owned": owned}})
    except store.LeaseLost as exc:
        logger.warning("lease_lost", extra={"fields": {"job_id": job_id, "error": str(exc)}})
    finally:
        stopped.set()
        thread.join(timeout=10)
    return True


def main():
    parser = argparse.ArgumentParser(description="Import videos through durable jobs")
    parser.add_argument("--once", action="store_true", help="Process at most one job, then exit")
    args = parser.parse_args()
    configure_logging()
    settings = Settings.from_env()
    store.init_db(settings.database_url)
    store.bind_library(settings.database_url, settings.library_identity)
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    while not stop.is_set():
        worked = process_one(settings)
        if args.once:
            return
        if not worked:
            stop.wait(1)


if __name__ == "__main__":
    main()
