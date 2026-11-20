"""Offline checks for isolated runtime identity; no downloads or GPU imports."""

import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("sdst_runtime", Path(__file__).resolve().parents[1] / "scripts/sol/prepare_sdst_runtime.py")
runtime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runtime)


def test_exact_stack_required():
    runtime.assert_versions("2.2.1+cu121", "0.17.1+cu121", "12.1")
    for stack in (("2.11.0", "0.17.1", "12.1"), ("2.2.1", "0.18.0", "12.1"), ("2.2.1", "0.17.1", "12.9")):
        with pytest.raises(ValueError, match="Unexpected base stack"):
            runtime.assert_versions(*stack)


def test_manifest_detects_change_and_new_file(tmp_path):
    (tmp_path / "python").mkdir()
    target = tmp_path / "python/package.py"
    target.write_text("value = 1", encoding="utf-8")
    original = runtime.file_hashes(tmp_path)
    runtime.write_json(tmp_path / "files.json", original)
    assert runtime.file_hashes(tmp_path) == original
    target.write_text("value = 2", encoding="utf-8")
    assert runtime.file_hashes(tmp_path) != original
    (tmp_path / "extra").write_text("new", encoding="utf-8")
    assert "extra" in runtime.file_hashes(tmp_path)
    (tmp_path / "python/files.json").write_text("package data", encoding="utf-8")
    assert "python/files.json" in runtime.file_hashes(tmp_path)


def test_json_never_overwrites(tmp_path):
    target = tmp_path / "record.json"
    runtime.write_json(target, {"source": "first"})
    with pytest.raises(FileExistsError):
        runtime.write_json(target, {"source": "second"})
    assert json.loads(target.read_bytes()) == {"source": "first"}


def test_install_requires_fresh_stage(tmp_path):
    (tmp_path / "python").mkdir()
    with pytest.raises(FileExistsError, match="fresh stage"):
        runtime.install(tmp_path, tmp_path / "runtime.sif")
