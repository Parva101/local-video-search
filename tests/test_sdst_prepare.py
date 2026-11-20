"""Synthetic input tests. No downloads, GPU work, pickle loads or private data."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import zipfile

import numpy as np
import pytest
import requests

_spec = importlib.util.spec_from_file_location("sdst_prepare", Path(__file__).resolve().parents[1] / "scripts/sol/prepare_sdst.py")
sdst = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sdst)


def npz_bytes(array, key="visual_feats_interm_pooled"):
    output = io.BytesIO()
    np.savez_compressed(output, **{key: array})
    return output.getvalue()


def make_zip(path, members):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in members:
            archive.writestr(name, value)
    return path


def small_release(tmp_path):
    labels, members = {}, []
    for split, qid in (("train", "q1"), ("test", "q2")):
        name = f"charades_{split}.jsonl"
        row = {"qid": qid, "vid": "source1", "query": "a query", "duration": 2.5,
               "relevant_windows": [[0.1, 0.2]]}
        payload = (json.dumps(row) + "\n").encode()
        labels[name] = (1, hashlib.sha256(payload).hexdigest())
        members.append(("data/charades/" + name, payload))
        members.append((f"data/charades/txt_feats/{qid}.npz", npz_bytes(np.ones((5, 3, 1024), dtype="float32"), "text_feats")))
    members.append(("data/charades/vid_feats/source1.npz", npz_bytes(np.ones((2, 5, 768), dtype="float32"))))
    members.extend([("data/charades/._ignored.npz", b"apple"), ("data/tacos/unused.bin", b"unused")])
    return make_zip(tmp_path / "release.zip", members), labels


def test_selected_extraction_checks_all_tensors_and_preserves_raw_labels(tmp_path):
    archive, labels = small_release(tmp_path)
    data = tmp_path / "stage/data"
    records = sdst.extract_charades(archive, data)
    assert len(records) == 5
    assert not (data / "tacos").exists()
    assert not list(data.rglob("._*"))
    result = sdst.validate_tree(data, records, labels, (1, 2))
    assert result["covered_queries"] == 2
    assert result["covered_sources"] == 1
    assert result["annotation_changes"] == 0
    assert result["splits"]["charades_train.jsonl"]["subsecond_targets"] == 1
    assert records["charades/vid_feats/source1.npz"]["shape"] == [2, 5, 768]
    for name, (_, expected_hash) in labels.items():
        assert sdst.sha256(data / "charades" / name) == expected_hash
    with pytest.raises(FileExistsError):
        sdst.extract_charades(archive, data)


@pytest.mark.parametrize("name", ["../outside", "/absolute", "data/../outside", "data\\outside", "C:/outside"])
def test_rejects_unsafe_paths_even_outside_the_selected_dataset(tmp_path, name):
    archive = make_zip(tmp_path / "bad.zip", [(name, b"x")])
    if "\\" in name:
        archive.write_bytes(archive.read_bytes().replace(name.replace("\\", "/").encode(), name.encode()))
    with pytest.raises(ValueError, match="Unsafe ZIP member"):
        sdst.extract_charades(archive, tmp_path / "data")


def test_rejects_links_duplicates_and_encryption(tmp_path):
    link = zipfile.ZipInfo("data/other/link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    archive = make_zip(tmp_path / "link.zip", [(link, b"/outside")])
    with pytest.raises(ValueError, match="type or encryption"):
        sdst.extract_charades(archive, tmp_path / "links")
    with pytest.warns(UserWarning, match="Duplicate name"):
        archive = make_zip(tmp_path / "duplicate.zip", [("data/other/file", b"x")] * 2)
    with pytest.raises(ValueError, match="Duplicate ZIP"):
        sdst.extract_charades(archive, tmp_path / "duplicates")
    archive = make_zip(tmp_path / "encrypted.zip", [("data/other/file", b"x")])
    payload = bytearray(archive.read_bytes())
    index = payload.index(b"PK\x01\x02")
    payload[index + 8] |= 1
    archive.write_bytes(payload)
    with pytest.raises(ValueError, match="type or encryption"):
        sdst.extract_charades(archive, tmp_path / "encrypted")


def test_rejects_member_and_total_expansion_limits(tmp_path):
    archive = make_zip(tmp_path / "large.zip", [("data/charades/charades_train.jsonl", b"1234")])
    with pytest.raises(ValueError, match="size"):
        sdst.extract_charades(archive, tmp_path / "member", member_limit=3)
    with pytest.raises(ValueError, match="extraction limit"):
        sdst.extract_charades(archive, tmp_path / "total", total_limit=3)


def test_crc_failure_preserves_the_unpublished_stage(tmp_path):
    archive = tmp_path / "crc.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output:
        output.writestr("data/charades/charades_train.jsonl", b"recognizable-payload")
    payload = archive.read_bytes().replace(b"recognizable-payload", b"Xecognizable-payload")
    archive.write_bytes(payload)
    with pytest.raises(zipfile.BadZipFile, match="CRC"):
        sdst.extract_charades(archive, tmp_path / "stage/data")
    assert not (tmp_path / "data").exists()
    assert (tmp_path / "stage/data/charades/charades_train.jsonl").exists()


@pytest.mark.parametrize("array", [np.ones(()), np.ones((2, 768)), np.ones((2, 4, 768), dtype="float32"),
                                   np.ones((0, 5, 768), dtype="float32"), np.ones((513, 5, 768), dtype="float32"),
                                   np.ones((2, 5, 768), dtype="float64"), np.full((2, 5, 768), np.nan, dtype="float32"),
                                   np.full((2, 5, 768), np.inf, dtype="float32"), np.ones((2, 5, 768), dtype=object)])
def test_rejects_invalid_video_tensors_without_conversion_or_pickle(tmp_path, array):
    path = tmp_path / "bad.npz"
    path.write_bytes(npz_bytes(array))
    with pytest.raises(ValueError):
        sdst.validate_features(path, "vid_feats")


def test_rejects_wrong_text_shape_keys_and_npz_duplicates(tmp_path):
    path = tmp_path / "bad.npz"
    path.write_bytes(npz_bytes(np.ones((5, 3, 1023), dtype="float32"), "text_feats"))
    with pytest.raises(ValueError, match="shape"):
        sdst.validate_features(path, "txt_feats")
    path.write_bytes(npz_bytes(np.ones((5, 3, 1024), dtype="float32"), "wrong"))
    with pytest.raises(ValueError, match="keys"):
        sdst.validate_features(path, "txt_feats")
    with pytest.warns(UserWarning, match="Duplicate name"):
        make_zip(path, [("text_feats.npy", b"x")] * 2)
    with pytest.raises(ValueError, match="NPZ payload"):
        sdst.validate_features(path, "txt_feats")


def test_rejects_missing_coverage_changed_label_and_changed_feature(tmp_path):
    archive, labels = small_release(tmp_path)
    data = tmp_path / "data"
    records = sdst.extract_charades(archive, data)
    feature = data / "charades/vid_feats/source1.npz"
    original = feature.read_bytes()
    feature.unlink()
    with pytest.raises(ValueError, match="coverage"):
        sdst.validate_tree(data, records, labels, (1, 2))
    feature.write_bytes(original + b"changed")
    with pytest.raises(ValueError, match="extracted member"):
        sdst.validate_tree(data, records, labels, (1, 2))
    feature.write_bytes(original)
    label = data / "charades/charades_train.jsonl"
    label.write_bytes(label.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="Label SHA"):
        sdst.validate_tree(data, records, labels, (1, 2))


class RawBody(io.BytesIO):
    def read(self, size, decode_content=False):
        return super().read(size)


class Response:
    def __init__(self, body=b"PK\x03\x04partial", content_type="application/zip", url=None, fail=False):
        self.url = url or "https://drive.usercontent.google.com/download"
        self.status_code, self.history = 200, []
        self.headers = {"Content-Type": content_type, "Content-Length": str(sdst.ARCHIVE_BYTES), "X-Request-ID": "test-request"}
        self.raw, self.body, self.fail = RawBody(body), body, fail

    def iter_content(self, size):
        yield self.body
        if self.fail:
            raise requests.exceptions.ChunkedEncodingError("stream stopped")

    def close(self):
        pass


class Session:
    def __init__(self, response):
        self.response, self.calls = response, []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_three_failed_streams_preserve_distinct_partials_and_backoff(tmp_path, caplog):
    session = Session(Response(fail=True))
    waits = []
    with pytest.raises(requests.exceptions.ChunkedEncodingError):
        sdst.download_archive(tmp_path / "archive.zip", session, waits.append)
    assert len(session.calls) == 3
    assert waits == [1, 2]
    assert len(list(tmp_path.glob("*.partial"))) == 3
    assert len(list(tmp_path.glob("*.failure.json"))) == 3
    assert not (tmp_path / "archive.zip").exists()
    assert all(path.read_bytes() == b"PK\x03\x04partial" for path in tmp_path.glob("*.partial"))
    assert [record.fields["attempt"] for record in caplog.records] == [1, 2]


@pytest.mark.parametrize("response", [Response(url="https://evil.example/download"),
    Response(content_type="text/plain"), Response(body=b"<html>not a ZIP</html>"),
    Response(body=b"<form id='download-form' action='https://evil.example/download'></form>", content_type="text/html")])
def test_download_rejects_hosts_types_html_and_confirmation_actions(tmp_path, response):
    session = Session(response)
    with pytest.raises(ValueError):
        sdst.download_archive(tmp_path / "archive.zip", session, lambda seconds: None)
    assert not (tmp_path / "archive.zip").exists()
    for path in tmp_path.glob("*.failure.json"):
        assert "evil.example" not in path.read_text()


def test_archive_identity_needs_full_release_size_and_json_never_overwrites(tmp_path):
    path = tmp_path / "small.zip"
    path.write_bytes(b"PK\x03\x04")
    with pytest.raises(ValueError, match="byte count"):
        sdst.archive_identity(path)
    report = tmp_path / "preparation.json"
    sdst.write_json(report, {"sha256": "first"})
    with pytest.raises(FileExistsError):
        sdst.write_json(report, {"sha256": "changed"})
    assert json.loads(report.read_bytes()) == {"sha256": "first"}


def test_unapproved_redirect_is_rejected_before_the_next_request():
    response = Response()
    response.status_code = 302
    response.headers["Location"] = "https://example.invalid/download"
    session = Session(response)
    with pytest.raises(ValueError, match="HTTPS Google hosts"):
        sdst.google_response(session, "https://drive.usercontent.google.com/download", {"id": sdst.FILE_ID})
    assert len(session.calls) == 1
    assert session.calls[0][1]["allow_redirects"] is False


def source_fixture(tmp_path):
    upstream = tmp_path / "upstream"
    (upstream / ".git").mkdir(parents=True)
    (upstream / ".git/HEAD").write_text(sdst.COMMIT + "\n", encoding="ascii")
    source = upstream / "model.py"
    source.write_text("pinned model source\n", encoding="utf-8")
    record = {"source_commit": sdst.COMMIT, "files": {"model.py": sdst.sha256(source)}}
    sdst.write_json(tmp_path / "source-identity.json", record)
    return upstream, record


def test_source_manifest_works_without_a_git_repository_and_rejects_tampering(tmp_path):
    upstream, record = source_fixture(tmp_path)
    assert sdst.source_identity(tmp_path) == record["files"]
    (upstream / "model.py").write_text("changed source\n", encoding="utf-8")
    with pytest.raises(ValueError, match="differs from its host Git identity"):
        sdst.source_identity(tmp_path)


@pytest.mark.parametrize("name", ["", ".", "../outside", "/absolute", "C:/outside", "sub\\file", ".git/HEAD"])
def test_source_manifest_rejects_paths_outside_its_source_files(tmp_path, name):
    upstream, record = source_fixture(tmp_path)
    record["files"] = {name: "0" * 64}
    (tmp_path / "source-identity.json").write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsafe source manifest path"):
        sdst.source_identity(tmp_path)


def test_source_manifest_requires_the_pinned_detached_head(tmp_path):
    upstream, record = source_fixture(tmp_path)
    (upstream / ".git/HEAD").write_text("ref: refs/heads/main\n", encoding="ascii")
    with pytest.raises(ValueError, match="pinned detached checkout"):
        sdst.source_identity(tmp_path)
