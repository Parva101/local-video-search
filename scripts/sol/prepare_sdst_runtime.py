"""Prepare and verify an isolated SDST Python target inside its pinned SIF."""

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time


IMAGE = "docker://mirror.gcr.io/pytorch/pytorch@sha256:42204bca460bb77cbd524577618e1723ad474e5d77cc51f94037fffbc2c88c6f"
CLIP_COMMIT = "a1d071733d7111c9c014f024669f959182114e33"
REQUIREMENTS = (
    "numpy==1.26.4", "nncore==0.4.2", "scipy==1.12.0",
    "scikit-learn==1.4.1.post1", "opencv-python-headless==4.9.0.80",
    "einops==0.7.0", "ftfy==6.1.3", "regex==2023.12.25", "tqdm==4.66.2",
)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 ** 2), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def event(name, **fields):
    print(json.dumps({"event": name, **fields}), flush=True)


def run(args):
    event("command_start", args=list(map(str, args)))
    started = time.monotonic()
    subprocess.run(list(map(str, args)), check=True)
    event("command_complete", elapsed_seconds=time.monotonic() - started)


def file_hashes(root):
    root = Path(root).resolve()
    hashes = {}
    for path in sorted(root.rglob("*")):
        if not path.resolve().is_relative_to(root):
            raise ValueError(f"Runtime path leaves its stage: {path}")
        if path.is_file() and path.relative_to(root).as_posix() != "files.json":
            hashes[path.relative_to(root).as_posix()] = sha256(path)
    return hashes


def assert_versions(torch_version, vision_version, cuda_version):
    if (torch_version.split("+")[0], vision_version.split("+")[0], cuda_version) != ("2.2.1", "0.17.1", "12.1"):
        raise ValueError(f"Unexpected base stack: torch={torch_version}, torchvision={vision_version}, CUDA={cuda_version}")


def probe(target=None):
    import torch
    import torchvision

    assert_versions(torch.__version__, torchvision.__version__, torch.version.cuda)
    nvcc = subprocess.check_output(["/usr/local/cuda/bin/nvcc", "--version"], text=True)
    if "release 12.1," not in nvcc:
        raise ValueError(f"Unexpected CUDA compiler: {nvcc}")
    result = {"python": platform.python_version(), "torch": torch.__version__,
              "torchvision": torchvision.__version__, "torch_cuda": torch.version.cuda,
              "nvcc": nvcc, "cxx11_abi": torch._C._GLIBCXX_USE_CXX11_ABI,
              "compiler": subprocess.check_output(["c++", "--version"], text=True)}
    if target is not None:
        target = Path(target).resolve()
        modules = {}
        for name in ("numpy", "nncore", "nncore.engine", "scipy", "sklearn", "cv2", "einops", "ftfy", "regex", "tqdm", "clip"):
            module = importlib.import_module(name)
            path = Path(module.__file__).resolve()
            if not path.is_relative_to(target):
                raise ValueError(f"Dependency imported outside isolated target: {name}: {path}")
            modules[name] = path.relative_to(target).as_posix()
        for module in (torch, torchvision):
            if Path(module.__file__).resolve().is_relative_to(target):
                raise ValueError(f"Base package replaced in isolated target: {module.__name__}")
        result["imports"] = modules
        result["distributions"] = sorted(
            [{"name": item.metadata["Name"], "version": item.version}
             for item in importlib.metadata.distributions(path=[str(target)])],
            key=lambda item: item["name"].lower())
    return result


def install(stage, sif):
    stage, sif = Path(stage).resolve(), Path(sif).resolve()
    if (stage / "runtime.json").exists() or (stage / "python").exists():
        raise FileExistsError("Use a fresh stage for each runtime attempt")
    base = probe()
    write_json(stage / "base.json", base)
    constraints = stage / "constraints.txt"
    constraints.write_text("torch==2.2.1\ntorchvision==0.17.1\nnumpy==1.26.4\n", encoding="utf-8")
    target = stage / "python"
    run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir",
         "--retries", "3", "--target", target, "--constraint", constraints,
         "--report", stage / "packages-report.json", *REQUIREMENTS])
    source = stage / "clip-source"
    if (stage / "clip-commit.txt").read_text(encoding="ascii").strip() != CLIP_COMMIT:
        raise ValueError("CLIP source does not have the declared host-verified commit")
    run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir",
         "--retries", "3", "--no-deps", "--no-build-isolation", "--target", target,
         "--report", stage / "clip-report.json", source])
    run([sys.executable, __file__, "probe", stage, sif])


def finish(stage, sif):
    stage, sif = Path(stage).resolve(), Path(sif).resolve()
    runtime = probe(stage / "python")
    write_json(stage / "runtime.json", {
        "image": IMAGE, "sif_sha256": sha256(sif), "clip_commit": CLIP_COMMIT,
        "requirements": REQUIREMENTS, "probe": runtime,
        "scope": "CPU import gate only; no ROI build, GPU, checkpoint or model execution",
    })
    write_json(stage / "files.json", file_hashes(stage))
    event("runtime_ready", sif_sha256=sha256(sif), files_sha256=sha256(stage / "files.json"))


def verify(stage, sif):
    stage = Path(stage).resolve()
    report = json.loads((stage / "runtime.json").read_bytes())
    if report["image"] != IMAGE or report["sif_sha256"] != sha256(sif):
        raise ValueError("Published runtime image identity differs")
    if json.loads((stage / "files.json").read_bytes()) != file_hashes(stage):
        raise ValueError("Published runtime files differ")
    current = probe(stage / "python")
    if current != report["probe"]:
        raise ValueError("Published runtime probe differs")
    event("runtime_verified", files_sha256=sha256(stage / "files.json"))


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "probe", "verify"))
    parser.add_argument("stage", type=Path)
    parser.add_argument("sif", type=Path)
    args = parser.parse_args()
    started = time.monotonic()
    event("stage_start", action=args.action, stage=str(args.stage))
    {"install": install, "probe": finish, "verify": verify}[args.action](args.stage, args.sif)
    event("stage_complete", action=args.action, elapsed_seconds=time.monotonic() - started)
