from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import re
import struct
from threading import Thread
import zipfile
import zlib

import pytest

from video_search.benchmark_data import (DataError, RangeReader, download_member,
                                       parse_annotations, select_videos, make_manifest)


@contextmanager
def archive_server(data, *, mode="normal", transient=0):
    history = []

    class Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("ETag", '"fixed"')
            self.end_headers()

        def do_GET(self):
            history.append(dict(self.headers))
            if len(history) <= transient:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b"busy")
                return
            if mode == "redirect":
                self.send_response(302)
                self.send_header("Location", self.path)
                self.end_headers()
                return
            match = re.fullmatch(r"bytes=(\d+)-(\d+)", self.headers.get("Range", ""))
            assert match
            start, end = map(int, match.groups())
            body = data[start:end + 1]
            self.send_response(200 if mode == "ignored" else 206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
            self.send_header("ETag", '"changed"' if mode == "changed" else '"fixed"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body[:-1] if mode == "truncated" else body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/archive.zip", history
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def archive(name="Charades_v1_480/AB123.mp4", payload=b"video-data"):
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
        with z.open(name, "w", force_zip64=True) as f:
            f.write(payload)
    return output.getvalue()


def test_range_zip64_member_is_verified_and_resumable(tmp_path):
    with archive_server(archive()) as (url, calls):
        with RangeReader(url) as remote, zipfile.ZipFile(remote) as z:
            info = z.infolist()[0]
            proof = download_member(z, info, tmp_path / "AB123.mp4")
            assert (tmp_path / "AB123.mp4").read_bytes() == b"video-data"
            before = len(calls)
            assert download_member(z, info, tmp_path / "AB123.mp4") == proof
            assert len(calls) == before
            assert all(call["If-Match"] == '"fixed"' for call in calls)
            assert len(proof["sha256"]) == 64


@pytest.mark.parametrize("mode", ["ignored", "changed", "truncated", "redirect"])
def test_bad_range_transport_stops_without_publishing(tmp_path, mode):
    with archive_server(archive(), mode=mode) as (url, _):
        with pytest.raises(DataError):
            with RangeReader(url) as remote:
                remote.read(8)
    assert list(tmp_path.iterdir()) == []


def test_transient_range_retries_are_logged(caplog):
    with archive_server(archive(), transient=1) as (url, calls):
        with RangeReader(url) as remote:
            assert remote.read(4) == b"PK\x03\x04"
    assert len(calls) == 2
    records = [r for r in caplog.records if r.message == "benchmark_download_retry"]
    assert len(records) == 1 and records[0].fields["status"] == 503


def test_corrupt_existing_file_is_never_overwritten(tmp_path):
    path = tmp_path / "AB123.mp4"
    path.write_bytes(b"user-data")
    with archive_server(archive()) as (url, _):
        with RangeReader(url) as remote, zipfile.ZipFile(remote) as z:
            with pytest.raises(DataError, match="Existing"):
                download_member(z, z.infolist()[0], path)
    assert path.read_bytes() == b"user-data"


@pytest.mark.parametrize("name", ["../AB123.mp4", "/AB123.mp4", "bad\\AB123.mp4", "C:/AB123.mp4"])
def test_unsafe_archive_path_is_rejected(tmp_path, name):
    with archive_server(archive(name)) as (url, _):
        with RangeReader(url) as remote, zipfile.ZipFile(remote) as z:
            with pytest.raises(DataError, match="Unsafe"):
                download_member(z, z.infolist()[0], tmp_path / "AB123.mp4")


def test_annotation_selection_is_stable_and_keeps_every_selected_query():
    text = "AB123 0 2##a person opens a door\nAB123 2 4##the door closes\nCD456 0 1##a person sits\n"
    rows = parse_annotations(text.encode(), "train")
    assert len(rows) == 3 and len({r["id"] for r in rows}) == 3
    assert select_videos(rows, "train", 2) == select_videos(list(reversed(rows)), "train", 2)
    manifests = make_manifest("train", rows, {"AB123": {"duration_seconds": 4, "annotation_duration_seconds": 4},
                                             "CD456": {"duration_seconds": 2, "annotation_duration_seconds": 2}})
    assert len(manifests["queries"]) == 3
    assert manifests["queries"][0]["targets"][0]["end_seconds"] == 2
    bounded = make_manifest("train", rows, {"AB123": {"duration_seconds": 4, "annotation_duration_seconds": 3},
                                           "CD456": {"duration_seconds": 2, "annotation_duration_seconds": 2}})
    assert bounded["queries"][1]["targets"][0]["end_seconds"] == 3
    assert bounded["queries"][1]["raw_targets"][0]["end_seconds"] == 4
    with pytest.raises(DataError, match="bounds"):
        make_manifest("train", rows, {"AB123": {"duration_seconds": 3, "annotation_duration_seconds": 1},
                                       "CD456": {"duration_seconds": 2, "annotation_duration_seconds": 2}})


def test_reference_targets_keep_media_duration_and_raw_labels_separate():
    rows = parse_annotations(b"AB123 -1 4##a person opens a door\n", "test")
    result = make_manifest("test", rows, {"AB123": {"duration_seconds": 2.9, "annotation_duration_seconds": 3}})
    assert result["videos"]["AB123"]["duration_seconds"] == 2.9
    assert result["queries"][0]["targets"][0] == {"video_id": "AB123", "start_seconds": 0, "end_seconds": 3}
    assert result["queries"][0]["raw_targets"][0] == {"video_id": "AB123", "start_seconds": -1, "end_seconds": 4}


def test_real_zip64_directory_end_records_are_supported(tmp_path):
    data = archive()
    end = data.rfind(b"PK\x05\x06")
    fields = struct.unpack("<4s4H2IH", data[end:end + 22])
    count, size, offset = fields[4:7]
    zip64 = struct.pack("<4sQ2H2I4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, count, count, size, offset)
    locator = struct.pack("<4sIQI", b"PK\x06\x07", 0, end, 1)
    ordinary = struct.pack("<4s4H2IH", b"PK\x05\x06", 0, 0, 65535, 65535, 0xffffffff, 0xffffffff, 0)
    with archive_server(data[:end] + zip64 + locator + ordinary) as (url, _):
        with RangeReader(url) as remote, zipfile.ZipFile(remote) as z:
            download_member(z, z.infolist()[0], tmp_path / "AB123.mp4")
    assert (tmp_path / "AB123.mp4").read_bytes() == b"video-data"


def test_corrupt_zip_payload_is_not_published(tmp_path):
    data = bytearray(archive(payload=b"some-video-payload"))
    fields = struct.unpack("<4s5H3I2H", data[:30])
    start = 30 + fields[-2] + fields[-1]
    data[start + 3] ^= 1
    with archive_server(bytes(data)) as (url, _):
        with RangeReader(url) as remote, zipfile.ZipFile(remote) as z:
            with pytest.raises((zipfile.BadZipFile, zlib.error)):
                download_member(z, z.infolist()[0], tmp_path / "AB123.mp4")
    assert not (tmp_path / "AB123.mp4").exists()


@pytest.mark.parametrize("line", ["bad", "../x 0 1##query", "AB123 2 1##query", "AB123 nan 1##query", "AB123 0 1## "])
def test_invalid_annotations_fail_explicitly(line):
    with pytest.raises(DataError):
        parse_annotations(line.encode(), "test")
