from contextlib import asynccontextmanager
import base64
import binascii
from datetime import date as calendar_date
import logging
import math
from pathlib import Path
import time
from typing import Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import psycopg

from video_search.config import Settings
from video_search.log import configure_logging
from video_search import frames, media, speech, store, uploads
from video_search.encoder import EncoderError, SPEC, get_encoder
from video_search import analysis, evidence, extent
from video_search.text_encoder import get_text_encoder
from video_search.vlm import VLMError


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(default=".", min_length=1, max_length=4096)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=100)
    recording_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=100)
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, gt=0)
    path: Literal["visual", "description", "hybrid", "speech"] = "visual"
    rerank: bool = Field(default=False, strict=True)
    image_base64: str | None = Field(default=None, max_length=14_000_000)
    start_date: calendar_date | None = Field(default=None)
    end_date: calendar_date | None = Field(default=None)

    @field_validator("query")
    @classmethod
    def nonempty_query(cls, value):
        if not value.strip():
            raise ValueError("Query must contain text")
        return value.strip()

    @model_validator(mode="after")
    def ordered_times(self):
        if self.rerank and (self.path != "description" or self.limit > 24):
            raise ValueError("Reranking requires the description path and a limit of at most 24")
        if self.image_base64 is not None and self.path == "description":
            raise ValueError("A reference image requires the visual or hybrid path")
        if self.image_base64 is not None and self.rerank:
            raise ValueError("A reference image cannot be combined with description reranking")
        if self.start_seconds is not None and self.end_seconds is not None and self.start_seconds >= self.end_seconds:
            raise ValueError("start_seconds must be less than end_seconds")
        if self.start_date is not None and self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


def _combine_query_vectors(text_vector: list[float], image_vector: list[float]) -> list[float]:
    if len(text_vector) != len(image_vector):
        raise EncoderError("invalid_embedding", "Text and image query vectors have different dimensions")
    combined = [a + b for a, b in zip(text_vector, image_vector)]
    norm = math.sqrt(sum(value * value for value in combined))
    if not math.isfinite(norm) or norm == 0:
        raise EncoderError("invalid_embedding", "The text and image query vectors cannot be combined")
    return [value / norm for value in combined]


class EvidenceSearchRequest(SearchRequest):
    limit: int = Field(default=12, ge=1, le=24)
    path: Literal["visual", "description", "hybrid"] = "description"
    max_checks: int = Field(default=3, ge=1, le=6, strict=True)
    policy: Literal["ranked", "adaptive", "extent", "uniform_extent"] = "adaptive"
    spend_budget: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def extent_budget_only(self):
        if self.spend_budget and self.policy not in {"extent", "uniform_extent"}:
            raise ValueError("spend_budget is only available for extent policies")
        return self


class VerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    recording_id: UUID
    query: str = Field(min_length=1, max_length=1000)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    context_seconds: float = Field(default=2, ge=0, le=5)

    @model_validator(mode="after")
    def valid_interval(self):
        if not self.query.strip():
            raise ValueError("Query must contain text")
        if not 0 < self.end_seconds-self.start_seconds <= 30:
            raise ValueError("Verification requires an interval longer than zero and at most 30 seconds")
        return self


class CaptureDateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capture_date: calendar_date | None = None


class SubtitleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["srt", "vtt"]
    content: str = Field(min_length=1, max_length=2_800_000)


class CountEventsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    query: str = Field(min_length=1, max_length=1000)
    recording_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=100)
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, gt=0)
    start_date: calendar_date | None = Field(default=None)
    end_date: calendar_date | None = Field(default=None)
    max_checks: int = Field(default=60, ge=1, le=500, strict=True)

    @field_validator("query")
    @classmethod
    def nonempty_count_query(cls, value):
        if not value.strip():
            raise ValueError("Query must contain text")
        return value.strip()

    @model_validator(mode="after")
    def count_scope(self):
        if self.start_seconds is not None and self.end_seconds is not None and self.start_seconds >= self.end_seconds:
            raise ValueError("start_seconds must be less than end_seconds")
        if self.start_date is not None and self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


def _merge_event(events, recording_id, partition_start, partition_end, intervals, verification_id):
    """Merge a verified occurrence with the previous one when their spans overlap within half a second."""
    if intervals:
        start = min(float(item["start_seconds"]) for item in intervals)
        end = max(float(item["end_seconds"]) for item in intervals)
    else:
        start, end = float(partition_start), float(partition_end)
    for event in events:
        if event["recording_id"] == recording_id \
                and event["start_seconds"] <= end + 0.5 and event["end_seconds"] >= start - 0.5:
            event["start_seconds"] = min(event["start_seconds"], start)
            event["end_seconds"] = max(event["end_seconds"], end)
            event["verification_ids"].append(verification_id)
            return
    events.append({"recording_id": recording_id, "start_seconds": start, "end_seconds": end,
                   "verification_ids": [verification_id], "media_url": f"/recordings/{recording_id}/media"})


class FileCaptureDatesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    utc_offset_minutes: int = Field(ge=-1440, le=1440, strict=True)
    recording_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=1000)


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        app.state.settings = settings or Settings.from_env()
        store.init_db(app.state.settings.database_url)
        store.bind_library(app.state.settings.database_url, app.state.settings.library_identity)
        yield

    app = FastAPI(title="Local Video Search", version="0.1.0", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
    static_root = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=static_root), name="static")

    @app.middleware("http")
    async def correlate(request: Request, call_next):
        request.state.request_id = str(uuid4())
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if (request.headers.get("sec-fetch-site") == "cross-site"
                    or (origin is not None and origin != str(request.base_url).rstrip("/"))):
                return JSONResponse(status_code=403, content={"code": "cross_origin_request", "request_id": request.state.request_id})
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.exception_handler(media.MediaError)
    async def media_error(request: Request, exc: media.MediaError):
        payload = {"code": exc.code, "message": str(exc), "details": exc.details,
                   "request_id": request.state.request_id}
        logging.getLogger("video_search").warning("media_error", extra={"fields": payload})
        return JSONResponse(status_code=422, content=payload)

    @app.exception_handler(psycopg.OperationalError)
    async def database_error(request: Request, exc: psycopg.OperationalError):
        # Do not expose a connection string or credentials through an HTTP error.
        logging.getLogger("video_search").error("database_unavailable", extra={"fields": {
            "request_id": request.state.request_id, "error_type": type(exc).__name__,
            "sqlstate": exc.sqlstate,
        }})
        return JSONResponse(status_code=503, content={
            "code": "database_unavailable", "request_id": request.state.request_id,
        })

    @app.exception_handler(EncoderError)
    async def encoder_error(request: Request, exc: EncoderError):
        status = 503 if exc.code in {"model_not_installed", "encoder_failed", "invalid_embedding"} else 422
        payload = {"code": exc.code, "message": str(exc), "details": exc.details, "request_id": request.state.request_id}
        logging.getLogger("video_search").warning("encoder_error", extra={"fields": payload})
        return JSONResponse(status_code=status, content=payload)

    @app.exception_handler(VLMError)
    async def vlm_error(request: Request, exc: VLMError):
        payload = {"code": exc.code, "message": str(exc), "details": exc.details,
                   "request_id": request.state.request_id}
        logging.getLogger("video_search").warning("vision_model_error", extra={"fields": payload})
        return JSONResponse(status_code=503 if exc.code == "vlm_not_configured" else 502, content=payload)

    @app.exception_handler(speech.TranscriptError)
    async def transcript_error(request: Request, exc: speech.TranscriptError):
        payload = {"code": exc.code, "message": str(exc), "details": exc.details,
                   "request_id": request.state.request_id}
        logging.getLogger("video_search").warning("transcript_error", extra={"fields": payload})
        return JSONResponse(status_code=422, content=payload)

    @app.get("/health")
    def health(request: Request):
        if not store.ready(request.app.state.settings.database_url):
            raise HTTPException(503, "Database schema is not ready")
        depth = store.job_queue_depth(request.app.state.settings.database_url)
        return {"status": "ready", "schema_version": store.SCHEMA_VERSION,
                "job_queue": {"queued": depth.get("queued", 0), "running": depth.get("running", 0)}}

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(static_root / "index.html")

    @app.get("/app-config")
    def app_config(request: Request):
        config = request.app.state.settings
        spec = analysis.description_spec(config)
        return {"model": spec["model_id"], "description_config_key": store._description_key(spec),
                "uploads_enabled": config.upload_write_root is not None,
                "upload_max_bytes": config.upload_max_bytes}

    @app.post("/uploads", status_code=202)
    async def upload(request: Request, filename: str = Query(min_length=1, max_length=255)):
        config = request.app.state.settings
        if config.upload_write_root is None:
            raise HTTPException(503, "Upload storage is not configured")
        analysis.client(config)
        job = await uploads.save_upload(request, config.upload_write_root, config.media_root,
                                        config.database_url, analysis.description_spec(config), filename,
                                        upload_id=request.headers.get("X-Upload-ID"), max_bytes=config.upload_max_bytes,
                                        read_root=config.upload_read_root)
        return {"job": job}

    @app.post("/imports", status_code=202)
    def import_sources(body: ImportRequest, request: Request):
        config = request.app.state.settings
        paths = media.scan_sources(config.media_root, body.path)
        # Validate the full request before creating any jobs.
        sources = [(path, *media.fingerprint(media.source_file(config.media_root, path, upload_root=config.upload_read_root))) for path in paths]
        jobs = [store.enqueue(config.database_url, path, size, mtime)
                for path, size, mtime in sources]
        return {"jobs": jobs, "count": len(jobs), "stage": "import"}

    @app.get("/jobs")
    def jobs(request: Request, limit: int = Query(default=100, ge=1, le=1000)):
        """List jobs, newest first. Page cap: limit 1..1000 (default 100)."""
        return store.list_jobs(request.app.state.settings.database_url, limit)

    @app.get("/jobs/{job_id}")
    def job(job_id: UUID, request: Request):
        result = store.get_job(request.app.state.settings.database_url, str(job_id))
        if result is None:
            raise HTTPException(404, "Job not found")
        return result

    @app.post("/jobs/{job_id}/retry", status_code=202)
    def retry_job(job_id: UUID, request: Request):
        config = request.app.state.settings
        item = store.get_job(config.database_url, str(job_id))
        if item is None:
            raise HTTPException(404, "Job not found")
        path = media.source_file(config.media_root, item["source_path"], upload_root=config.upload_read_root)
        if media.fingerprint(path) != (item["expected_size"], item["expected_mtime_ns"]):
            raise HTTPException(409, "Source changed; submit a new import")
        retried = store.retry_job(config.database_url, str(job_id))
        if retried is None:
            raise HTTPException(409, "Only failed jobs can be retried")
        return retried

    @app.get("/recordings")
    def recordings(request: Request, limit: int = Query(default=100, ge=1, le=1000)):
        """List recordings, newest first. Page cap: limit 1..1000 (default 100)."""
        return store.list_recordings(request.app.state.settings.database_url, limit)

    @app.post("/recordings/capture-dates/from-files")
    def capture_dates_from_files(body: FileCaptureDatesRequest, request: Request):
        scope = [str(item) for item in body.recording_ids] if body.recording_ids is not None else None
        updated = store.capture_dates_from_files(request.app.state.settings.database_url,
                                                 body.utc_offset_minutes, scope)
        return {"updated": updated, "count": len(updated)}

    @app.post("/recordings/{recording_id}/capture-date")
    def set_capture_date(recording_id: UUID, body: CaptureDateRequest, request: Request):
        recording_or_404(request, recording_id)
        row = store.set_capture_date(request.app.state.settings.database_url, str(recording_id),
                                     body.capture_date, "user")
        return row

    def recording_or_404(request: Request, recording_id: UUID):
        result = store.get_recording(request.app.state.settings.database_url, str(recording_id))
        if result is None:
            raise HTTPException(404, "Recording not found")
        return result

    @app.get("/recordings/{recording_id}")
    def recording(recording_id: UUID, request: Request):
        return recording_or_404(request, recording_id)

    @app.post("/recordings/{recording_id}/visual-index", status_code=202)
    def index_recording(recording_id: UUID, request: Request):
        item = recording_or_404(request, recording_id)
        config = request.app.state.settings
        path = media.source_file(config.media_root, item["source_path"], upload_root=config.upload_read_root)
        if media.fingerprint(path) != (item["size"], item["mtime_ns"]):
            raise HTTPException(409, "Source changed; import the new file before indexing")
        return store.enqueue_visual(config.database_url, str(recording_id), SPEC)

    @app.get("/visual-indexes")
    def indexes(request: Request, recording_id: UUID | None = None,
                limit: int = Query(default=100, ge=1, le=1000)):
        """List visual index builds, newest first. Page cap: limit 1..1000 (default 100)."""
        return store.list_visual_builds(request.app.state.settings.database_url,
                                        str(recording_id) if recording_id else None, limit)

    @app.get("/visual-indexes/{build_id}")
    def index_status(build_id: UUID, request: Request):
        result = store.get_visual_build(request.app.state.settings.database_url, str(build_id))
        if result is None:
            raise HTTPException(404, "Visual index not found")
        return result

    @app.post("/recordings/{recording_id}/description-index", status_code=202)
    def description_index(recording_id: UUID, request: Request):
        item = recording_or_404(request, recording_id)
        config = request.app.state.settings
        analysis.client(config)
        path = media.source_file(config.media_root, item["source_path"], upload_root=config.upload_read_root)
        if media.fingerprint(path) != (item["size"], item["mtime_ns"]):
            raise HTTPException(409, "Source changed; import the new file first")
        return store.enqueue_description(config.database_url, str(recording_id), analysis.description_spec(config))

    @app.get("/description-indexes")
    def description_indexes(request: Request, recording_id: UUID | None = None,
                            limit: int = Query(default=100, ge=1, le=1000)):
        """List description index builds, newest first. Page cap: limit 1..1000 (default 100)."""
        return store.list_description_builds(request.app.state.settings.database_url,
                                            str(recording_id) if recording_id else None, limit)

    @app.get("/description-indexes/{build_id}")
    def description_status(build_id: UUID, request: Request):
        result = store.get_description_build(request.app.state.settings.database_url, str(build_id))
        if result is None:
            raise HTTPException(404, "Description index not found")
        return result

    @app.post("/recordings/{recording_id}/subtitles")
    def add_subtitles(recording_id: UUID, body: SubtitleRequest, request: Request):
        recording = recording_or_404(request, recording_id)
        config = request.app.state.settings
        spec = speech.subtitle_spec(body.format, body.content)
        parser = speech.parse_vtt if body.format == "vtt" else speech.parse_srt
        segments = parser(body.content, recording["metadata"]["duration_seconds"])
        encoder = get_text_encoder(config.model_cache)
        vectors = [encoder.text(text) for _, _, text in segments]
        build_id, created = store.create_ready_transcript(
            config.database_url, str(recording_id), spec,
            [(start, end, text, vector) for (start, end, text), vector in zip(segments, vectors)])
        logging.getLogger("video_search").info("subtitles_imported", extra={"fields": {
            "request_id": request.state.request_id, "recording_id": str(recording_id),
            "format": body.format, "segments": len(segments), "created": created}})
        return {"build_id": build_id, "created": created, "segments": len(segments), "format": body.format}

    @app.post("/recordings/{recording_id}/transcript-index", status_code=202)
    def transcript_index(recording_id: UUID, request: Request):
        item = recording_or_404(request, recording_id)
        config = request.app.state.settings
        if not item["metadata"].get("has_audio"):
            raise HTTPException(422, "This recording has no audio stream to transcribe")
        path = media.source_file(config.media_root, item["source_path"], upload_root=config.upload_read_root)
        if media.fingerprint(path) != (item["size"], item["mtime_ns"]):
            raise HTTPException(409, "Source changed; import the new file before speech indexing")
        return store.enqueue_transcript(config.database_url, str(recording_id),
                                        speech.asr_spec(item["metadata"].get("audio_start_seconds")))

    @app.get("/transcript-indexes")
    def transcript_indexes(request: Request, recording_id: UUID | None = None,
                           limit: int = Query(default=100, ge=1, le=1000)):
        """List transcript index builds, newest first. Page cap: limit 1..1000 (default 100)."""
        return store.list_transcript_builds(request.app.state.settings.database_url,
                                            str(recording_id) if recording_id else None, limit)

    @app.get("/transcript-indexes/{build_id}")
    def transcript_status(build_id: UUID, request: Request):
        result = store.get_transcript_build(request.app.state.settings.database_url, str(build_id))
        if result is None:
            raise HTTPException(404, "Transcript index not found")
        return result

    @app.post("/count-events")
    def count_events(body: CountEventsRequest, request: Request):
        config = request.app.state.settings
        started = time.perf_counter()
        scope = [str(item) for item in body.recording_ids] if body.recording_ids is not None else None
        if scope:
            for recording_id in scope:
                recording_or_404(request, UUID(recording_id))
        recordings = store.list_recordings(config.database_url, limit=1000)
        if scope is not None:
            wanted = set(scope)
            recordings = [item for item in recordings if str(item["id"]) in wanted]
        events, checked, uncertain, skipped_undated, partition_total = [], 0, 0, 0, 0
        stop_reason = "scope_exhausted"
        partition_progress = []
        for recording in recordings:
            capture = recording["capture_date"]
            if (body.start_date is not None or body.end_date is not None) and capture is None:
                skipped_undated += 1
                continue
            if body.start_date is not None and capture < body.start_date:
                continue
            if body.end_date is not None and capture > body.end_date:
                continue
            recording_id = str(recording["id"])
            total = store.count_windows(config.database_url, recording_id,
                                        body.start_seconds, body.end_seconds)
            partition_total += total
            partition_checked = 0
            if checked >= body.max_checks or total == 0:
                if checked >= body.max_checks:
                    stop_reason = "budget_exhausted"
                partition_progress.append({"recording_id": recording_id, "total": total, "checked": partition_checked})
                continue
            offset = 0
            while checked < body.max_checks:
                windows = store.list_windows(config.database_url, recording_id,
                                              min(1000, body.max_checks - checked), offset)
                if not windows:
                    break
                for window in windows:
                    if checked >= body.max_checks:
                        break
                    start, end = float(window["start_seconds"]), float(window["end_seconds"])
                    if body.start_seconds is not None and end <= body.start_seconds:
                        continue
                    if body.end_seconds is not None and start >= body.end_seconds:
                        continue
                    verification = analysis.verify(config, recording, body.query, start, end, 0)
                    checked += 1
                    partition_checked += 1
                    status = verification["result"]["status"]
                    if status == "match":
                        _merge_event(events, recording_id, start, end,
                                     verification["result"]["intervals"], verification["id"])
                    elif status == "insufficient_evidence":
                        uncertain += 1
                offset += len(windows)
            partition_progress.append({"recording_id": recording_id, "total": total, "checked": partition_checked})
            if checked >= body.max_checks and partition_total > checked:
                stop_reason = "budget_exhausted"
        complete = stop_reason != "budget_exhausted"
        result = {
            "query": body.query, "count": len(events), "events": events,
            "result_type": "observed_event_count",
            "partitions": {"total": partition_total, "checked": checked, "uncertain": uncertain,
                           "skipped_undated": skipped_undated, "complete": complete},
            "partition_progress": partition_progress,
            "stop_reason": stop_reason,
            "elapsed_seconds": time.perf_counter() - started,
            "honesty_note": ("The count covers only checked partitions; unchecked or uncertain intervals are not "
                             "proven absent, and nearby separate events can merge into one occurrence."),
            "request_id": request.state.request_id,
        }
        logging.getLogger("video_search").info("count_events", extra={"fields": {
            "request_id": request.state.request_id, "count": len(events), "checked": checked,
            "total_partitions": partition_total, "uncertain": uncertain, "stop_reason": stop_reason,
            "elapsed_seconds": result["elapsed_seconds"],
        }})
        return result

    @app.post("/verify")
    def verify(body: VerificationRequest, request: Request):
        recording = recording_or_404(request, body.recording_id)
        if body.end_seconds > recording["metadata"]["duration_seconds"]:
            raise HTTPException(422, "Verification interval leaves the source recording")
        return analysis.verify(request.app.state.settings, recording, body.query, body.start_seconds,
                               body.end_seconds, body.context_seconds)

    @app.get("/verifications/{verification_id}")
    def verification(verification_id: UUID, request: Request):
        item = store.get_verification(request.app.state.settings.database_url, str(verification_id))
        if item is None:
            raise HTTPException(404, "Verification not found")
        return item

    @app.post("/search")
    def search(body: SearchRequest, request: Request):
        config = request.app.state.settings
        started = time.perf_counter()
        scope = [str(item) for item in body.recording_ids] if body.recording_ids is not None else None
        if scope:
            for recording_id in scope:
                recording_or_404(request, UUID(recording_id))
        results, coverage, encode_seconds = {}, {}, 0.0
        query_image = None
        budget = min(100, body.limit*4) if body.path == "hybrid" else body.limit
        if body.rerank:
            budget = 24
        if body.path in {"visual", "hybrid"}:
            encode_started = time.perf_counter()
            if body.image_base64 is not None:
                try:
                    query_image = frames.prepare_query_image(base64.b64decode(body.image_base64, validate=True))
                except (binascii.Error, ValueError) as exc:
                    raise HTTPException(422, "The attached reference image is not valid base64") from exc
            vector = get_encoder(config.model_cache).text(body.query)
            if query_image is not None:
                vector = _combine_query_vectors(vector, get_encoder(config.model_cache).images([query_image]))
            encode_seconds += time.perf_counter()-encode_started
            results["visual"] = store.search_visual(config.database_url, SPEC, vector, budget, scope,
                                                     body.start_seconds, body.end_seconds,
                                                     body.start_date, body.end_date)
            coverage["visual"] = results["visual"]["coverage"]
        if body.path in {"description", "hybrid"}:
            encode_started = time.perf_counter()
            vector = get_text_encoder(config.model_cache).text(body.query)
            encode_seconds += time.perf_counter()-encode_started
            results["description"] = store.search_descriptions(
                config.database_url, analysis.description_spec(config), body.query, vector, budget, scope,
                body.start_seconds, body.end_seconds, body.start_date, body.end_date)
            coverage["description"] = results["description"]["coverage"]
        if body.path == "speech":
            encode_started = time.perf_counter()
            vector = get_text_encoder(config.model_cache).text(body.query)
            encode_seconds += time.perf_counter()-encode_started
            results["speech"] = store.search_speech(config.database_url, body.query, vector, budget, scope,
                                                    body.start_seconds, body.end_seconds, body.start_date, body.end_date)
            coverage["speech"] = results["speech"]["coverage"]
        if body.path == "hybrid":
            merged = {}
            for branch, output in results.items():
                for rank, candidate in enumerate(output["results"], 1):
                    key = (str(candidate["recording_id"]), candidate["start_seconds"], candidate["end_seconds"])
                    item = merged.setdefault(key, {**candidate, "paths": [], "fusion_score": 0.0, "branch_scores": {}})
                    item["paths"].append(branch)
                    item["fusion_score"] += 1/(60+rank)
                    item["branch_scores"][branch] = candidate.get("similarity", candidate.get("rrf_score"))
                    if branch == "description":
                        item["description"] = candidate["description"]
            candidates = sorted(merged.values(), key=lambda item: (-item["fusion_score"], str(item["recording_id"]), item["start_seconds"]))[:body.limit]
            result = {"results": candidates, "coverage": coverage}
        else:
            result = results[body.path]
        if body.rerank:
            from video_search.reranker import SPEC as RERANK_SPEC, get_reranker
            rerank_started = time.perf_counter()
            candidate_count = len(result["results"])
            result["results"] = get_reranker(config.model_cache).rank(body.query, result["results"])[:body.limit]
            result["reranker"] = {"spec": RERANK_SPEC, "candidate_count": candidate_count,
                                  "seconds": time.perf_counter() - rerank_started}
        # Inspect source availability before returning a playable evidence reference.
        for candidate in result["results"]:
            try:
                path = media.source_file(config.media_root, candidate["source_path"], upload_root=config.upload_read_root)
                unchanged = media.fingerprint(path) == (candidate["size"], candidate["mtime_ns"])
                candidate["source_status"] = "available" if unchanged else "changed"
            except media.MediaError as exc:
                candidate["source_status"] = exc.code
            candidate["verified"] = False
            candidate["media_url"] = f"/recordings/{candidate['recording_id']}/media"
        result["spec"] = ({"visual": SPEC, "description": analysis.description_spec(config)} if body.path == "hybrid"
                          else SPEC if body.path == "visual" else analysis.description_spec(config))
        result["query"] = body.query
        result["path"] = body.path
        if body.start_date is not None or body.end_date is not None:
            result["date_scope"] = {"start_date": body.start_date.isoformat() if body.start_date else None,
                                    "end_date": body.end_date.isoformat() if body.end_date else None}
        if query_image is not None:
            result["query_image"] = {"preprocess_version": frames.QUERY_IMAGE_PREPROCESS_VERSION,
                                     "vector_recipe": "unit-sum-text-image-l2-v1"}
        result["result_type"] = ("unverified_visual_candidates" if body.path == "visual"
                                else "unverified_transcript_matches" if body.path == "speech"
                                else "unverified_multimodal_candidates")
        elapsed = time.perf_counter()-started
        result["timing"] = {"encode_seconds": encode_seconds,
                             "search_seconds": elapsed-encode_seconds, "total_seconds": elapsed}
        logging.getLogger("video_search").info("visual_search", extra={"fields": {
            "request_id": request.state.request_id, "results": len(result["results"]),
            "query_characters": len(body.query), "image_query": query_image is not None,
            "timing": result["timing"],
        }})
        return result

    @app.post("/evidence-search")
    def evidence_search(body: EvidenceSearchRequest, request: Request):
        started = time.perf_counter()
        retrieved = search(SearchRequest(**body.model_dump(exclude={"max_checks", "policy", "spend_budget"})), request)
        checker = extent.check_candidates if body.policy in {"extent", "uniform_extent"} else evidence.check_candidates
        options = {"spend_budget": body.spend_budget} if body.policy in {"extent", "uniform_extent"} else {}
        checked = checker(
            request.app.state.settings, body.query, retrieved["results"], body.max_checks, body.policy,
            body.start_seconds, body.end_seconds, **options,
        )
        checked["retrieval"] = retrieved
        checked["request_id"] = request.state.request_id
        checked["elapsed_seconds"] = time.perf_counter() - started
        logging.getLogger("video_search").info("evidence_search", extra={"fields": {
            "request_id": request.state.request_id, "policy_version": checked["policy_version"],
            "stop_reason": checked["stop_reason"], "budget": checked["budget"],
            "verification_ids": [item["verification"]["id"] for item in checked["checks"]],
            "elapsed_seconds": checked["elapsed_seconds"],
        }})
        return checked

    @app.get("/recordings/{recording_id}/windows")
    def windows(recording_id: UUID, request: Request,
                limit: int = Query(default=100, ge=1, le=1000),
                offset: int = Query(default=0, ge=0)):
        """List one recording's windows in time order. Page cap: limit 1..1000, offset 0+."""
        recording_or_404(request, recording_id)
        return store.list_windows(request.app.state.settings.database_url, str(recording_id), limit, offset)

    @app.get("/recordings/{recording_id}/media")
    def recording_media(recording_id: UUID, request: Request):
        item = recording_or_404(request, recording_id)
        try:
            path = media.source_file(request.app.state.settings.media_root, item["source_path"],
                                     upload_root=request.app.state.settings.upload_read_root)
            current = media.fingerprint(path)
        except media.MediaError as exc:
            raise HTTPException(409, {"code": "source_unavailable", "reason": exc.code}) from exc
        if current != (item["size"], item["mtime_ns"]):
            raise HTTPException(409, {"code": "source_changed", "message": "Import the changed file before playback."})
        return FileResponse(path, content_disposition_type="inline")

    return app


app = create_app()
