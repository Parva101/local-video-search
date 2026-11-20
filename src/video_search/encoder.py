"""Pinned, local SigLIP2 image/text retrieval baseline."""

import argparse
from functools import lru_cache
import json
import os
from pathlib import Path
import time
from threading import Lock


MODEL_ID = "google/siglip2-base-patch16-224"
REVISION = "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2"
SPEC = {
    "model_id": MODEL_ID,
    "revision": REVISION,
    "dimensions": 768,
    "preprocess_version": "ffmpeg-max512-siglip-native-pil-rgb-v1",
    "sampling_version": "window-sixth-mid-five-sixths-after-or-window-first-pts-v1",
    "frames_per_window": 3,
    "pooling": "mean-l2-frame-then-l2-window",
    "runtime": "torch-2.9.0-transformers-4.57.6-pillow-12.1.0-cpu-float32-v1",
}
FILES = ["config.json", "model.safetensors", "preprocessor_config.json", "special_tokens_map.json",
         "tokenizer.json", "tokenizer.model", "tokenizer_config.json"]


class EncoderError(ValueError):
    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code = code
        self.details = details


def checkpoint_path(cache: Path) -> Path:
    return cache / "siglip2-base-patch16-224" / REVISION


def download(cache: Path) -> Path:
    from huggingface_hub import snapshot_download

    path = checkpoint_path(cache)
    snapshot_download(MODEL_ID, revision=REVISION, allow_patterns=FILES, local_dir=path)
    return path


class SiglipEncoder:
    def __init__(self, cache: Path):
        import torch
        from transformers import AutoModel, AutoProcessor

        path = checkpoint_path(cache)
        if not all((path / filename).is_file() for filename in FILES):
            raise EncoderError("model_not_installed", "Run python -m video_search.encoder download before indexing or searching")
        torch.set_num_threads(4)
        try:
            self.model = AutoModel.from_pretrained(path, local_files_only=True, trust_remote_code=False,
                                                   use_safetensors=True).to(device="cpu", dtype=torch.float32).eval()
            self.processor = AutoProcessor.from_pretrained(path, local_files_only=True, trust_remote_code=False,
                                                           use_fast=False)
        except (OSError, ValueError, RuntimeError) as exc:
            raise EncoderError("encoder_failed", "The local checkpoint could not be loaded",
                               error_type=type(exc).__name__, reason=str(exc)[:1000]) from exc
        self.lock = Lock()

    def images(self, images) -> list[float]:
        import torch

        if not 1 <= len(images) <= 3:
            raise EncoderError("invalid_batch", "The baseline accepts one to three sampled frames")
        try:
            with self.lock, torch.inference_mode():
                inputs = self.processor(images=images, return_tensors="pt")
                vectors = self.model.get_image_features(**inputs).float()
                if not torch.isfinite(vectors).all() or (vectors.norm(dim=-1) == 0).any():
                    raise EncoderError("invalid_embedding", "Encoder returned an invalid image embedding")
                vectors = torch.nn.functional.normalize(vectors, dim=-1)
                pooled = torch.nn.functional.normalize(vectors.mean(dim=0), dim=-1)
                if pooled.numel() != SPEC["dimensions"] or not torch.isfinite(pooled).all() or pooled.norm() == 0:
                    raise EncoderError("invalid_embedding", "Encoder returned an invalid pooled embedding")
                return pooled.tolist()
        except RuntimeError as exc:
            raise EncoderError("encoder_failed", "Image inference failed",
                               error_type=type(exc).__name__, reason=str(exc)[:1000]) from exc

    def text(self, query: str) -> list[float]:
        import torch

        if not query.strip():
            raise EncoderError("empty_query", "Query must contain text")
        tokens = self.processor.tokenizer(query, add_special_tokens=True, truncation=False)["input_ids"]
        if len(tokens) > 64:
            raise EncoderError("query_too_long", "This baseline accepts at most 64 model tokens; shorten the query")
        try:
            with self.lock, torch.inference_mode():
                inputs = self.processor(text=[query], padding="max_length", max_length=64,
                                        truncation=False, return_tensors="pt")
                vector = self.model.get_text_features(**inputs)[0]
                vector = torch.nn.functional.normalize(vector.float(), dim=-1)
                if vector.numel() != SPEC["dimensions"] or not torch.isfinite(vector).all() or vector.norm() == 0:
                    raise EncoderError("invalid_embedding", "Encoder returned an invalid text embedding")
                return vector.tolist()
        except RuntimeError as exc:
            raise EncoderError("encoder_failed", "Text inference failed",
                               error_type=type(exc).__name__, reason=str(exc)[:1000]) from exc


@lru_cache(maxsize=1)
def _load_encoder(cache: Path) -> SiglipEncoder:
    return SiglipEncoder(cache)


_load_lock = Lock()


def get_encoder(cache: Path) -> SiglipEncoder:
    # Concurrent first requests must not each allocate another model.
    with _load_lock:
        return _load_encoder(cache)


def main():
    parser = argparse.ArgumentParser(description="Install or test the pinned retrieval encoder")
    parser.add_argument("action", choices=["download", "smoke"])
    args = parser.parse_args()
    cache = Path(os.environ.get("MODEL_CACHE", "/models"))
    if args.action == "download":
        print(json.dumps({"checkpoint": str(download(cache)), "spec": SPEC}))
    else:
        from PIL import Image

        start = time.perf_counter()
        model = get_encoder(cache)
        loaded = time.perf_counter()
        red = model.images([Image.new("RGB", (224, 224), "red")])
        text = model.text("a red image")
        print(json.dumps({"dimensions": len(red), "cosine": sum(a*b for a,b in zip(red, text)),
                          "load_seconds": loaded-start, "inference_seconds": time.perf_counter()-loaded,
                          "spec": SPEC}))


if __name__ == "__main__":
    main()
