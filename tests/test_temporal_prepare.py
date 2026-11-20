"""Archive trust-boundary checks for the research-only data preparer."""

import importlib.util
from io import BytesIO
from pathlib import Path
import tarfile

import pytest


spec = importlib.util.spec_from_file_location("prepare_temporal", Path(__file__).parents[1] / "scripts/sol/prepare_temporal.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def archive(tmp_path, entries):
    path = tmp_path / "features.tar"
    with tarfile.open(path, "w") as output:
        for name, payload, kind in entries:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.size = len(payload) if kind == tarfile.REGTYPE else 0
            output.addfile(info, BytesIO(payload) if kind == tarfile.REGTYPE else None)
    return path


def test_unpack_preserves_existing_features_and_rejects_changed_bytes(tmp_path):
    path = archive(tmp_path, [("features/A.npz", b"source", tarfile.REGTYPE)])
    destination = tmp_path / "data"
    assert module.unpack(path, destination) == 1
    assert module.unpack(path, destination) == 1
    (destination / "A.npz").write_bytes(b"wrong")
    with pytest.raises(ValueError, match="Existing feature differs"):
        module.unpack(path, destination)


@pytest.mark.parametrize("name,kind", [("../A.npz", tarfile.REGTYPE), ("/A.npz", tarfile.REGTYPE),
                                        ("A.npz", tarfile.SYMTYPE), ("index.html", tarfile.REGTYPE)])
def test_unpack_rejects_paths_links_and_wrong_files(tmp_path, name, kind):
    path = archive(tmp_path, [(name, b"source", kind)])
    with pytest.raises(ValueError):
        module.unpack(path, tmp_path / "data")


def test_unpack_rejects_flattened_name_collision(tmp_path):
    path = archive(tmp_path, [("a/A.npz", b"a", tarfile.REGTYPE), ("b/A.npz", b"b", tarfile.REGTYPE)])
    with pytest.raises(ValueError, match="Duplicate feature"):
        module.unpack(path, tmp_path / "data")
