"""Bounded streamed uploads into a separate persistent storage area."""

import hashlib
import asyncio
import os
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException

from video_search import media, store


async def save_upload(request, write_root, media_root, database_url, description_spec, filename, *, upload_id=None, max_bytes=2 * 1024**3, read_root=None):
    if write_root is None:
        raise HTTPException(503, "Upload storage is not configured")
    if (not filename or len(filename.encode("utf-8")) > 240 or filename in {".", ".."}
            or any(ord(c) < 32 or c in '/\\:' for c in filename)
            or Path(filename).suffix.lower() not in media.MEDIA_EXTENSIONS):
        raise HTTPException(422, "Choose a supported video with a plain file name of at most 240 bytes")
    try:
        upload_id = UUID(upload_id or str(uuid4()))
    except ValueError as exc:
        raise HTTPException(422, "X-Upload-ID must be a UUID") from exc
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            declared = int(declared)
        except ValueError as exc:
            raise HTTPException(422, "Content-Length must be a byte count") from exc
        if declared <= 0:
            raise HTTPException(422, "The uploaded file is empty")
        if declared > max_bytes:
            raise HTTPException(413, "Video exceeds the upload size limit")
    root = Path(write_root).resolve(strict=True)
    with store.upload_lock(database_url, upload_id) as acquired:
        if not acquired:
            raise HTTPException(409, "This upload is already in progress")
        directory = root / str(upload_id)
        directory.mkdir(exist_ok=True)
        if directory.is_symlink() or directory.resolve() != directory:
            raise HTTPException(409, "Upload directory is not a regular storage directory")
        final = directory / filename
        published = [p for p in directory.iterdir() if not p.name.endswith(".part")]
        if published and published != [final]:
            raise HTTPException(409, "This upload ID already belongs to a different file name")
        # The session lock proves no live upload owns leftovers from a stopped process.
        for stale in directory.glob("*.part"):
            stale.unlink()
        temporary = directory / (str(uuid4()) + ".part")
        total, digest = 0, hashlib.sha256()
        try:
            with temporary.open("xb") as output:
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > max_bytes:
                        raise HTTPException(413, "Video exceeds the upload size limit")
                    await asyncio.to_thread(output.write, chunk)
                    digest.update(chunk)
                output.flush()
                await asyncio.to_thread(os.fsync, output.fileno())
            if total == 0 or (declared is not None and total != declared):
                raise HTTPException(422, "Upload is empty or does not match Content-Length")
            if final.exists():
                if final.is_symlink() or final.stat().st_size != total or await asyncio.to_thread(media.hash_source, final) != digest.hexdigest():
                    raise HTTPException(409, "This upload ID already belongs to different video bytes")
            else:
                os.link(temporary, final)
            relative = f"{media.UPLOAD_PREFIX}{upload_id}/{filename}"
            readable = media.source_file(Path(media_root), relative, upload_root=read_root)
            if media.fingerprint(readable) != media.fingerprint(final):
                raise HTTPException(503, "Upload storage and media storage do not map to the same file")
            size, mtime = media.fingerprint(final)
            return store.enqueue(database_url, relative, size, mtime,
                                 auto_description_spec=description_spec, original_filename=filename)
        finally:
            temporary.unlink(missing_ok=True)
