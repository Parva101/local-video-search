"""Small, versioned text embeddings for generated descriptions."""

import argparse
from functools import lru_cache
import json
import os
from pathlib import Path
from threading import Lock

from video_search.encoder import EncoderError

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
SPEC = {"model_id": MODEL_ID, "revision": REVISION, "dimensions": 384,
        "pooling": "attention-mask-mean-l2", "max_tokens": 256,
        "runtime": "torch-2.9.0-transformers-4.57.6-cpu-float32"}
FILES = ["config.json", "model.safetensors", "special_tokens_map.json", "tokenizer.json",
         "tokenizer_config.json", "vocab.txt"]


def checkpoint_path(cache: Path) -> Path:
    return cache / "all-MiniLM-L6-v2" / REVISION


class TextEncoder:
    def __init__(self, cache):
        import torch
        from transformers import AutoModel, AutoTokenizer

        path = checkpoint_path(cache)
        if not all((path / name).is_file() for name in FILES):
            raise EncoderError("model_not_installed", "Run python -m video_search.text_encoder download first")
        torch.set_num_threads(4)
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
            self.model = AutoModel.from_pretrained(path, local_files_only=True, trust_remote_code=False,
                                                   use_safetensors=True).to(device="cpu", dtype=torch.float32).eval()
        except (OSError, ValueError, RuntimeError) as exc:
            raise EncoderError("encoder_failed", "Text encoder could not be loaded", reason=str(exc)[:1000]) from exc
        self.lock = Lock()

    def text(self, text: str) -> list[float]:
        import torch

        if not text.strip():
            raise EncoderError("empty_query", "Text must not be empty")
        if len(self.tokenizer(text, truncation=False)["input_ids"]) > 256:
            raise EncoderError("text_too_long", "Text exceeds the encoder's 256-token budget")
        try:
            with self.lock, torch.inference_mode():
                inputs = self.tokenizer([text], padding=True, truncation=False, return_tensors="pt")
                tokens = self.model(**inputs).last_hidden_state
                mask = inputs["attention_mask"].unsqueeze(-1).expand(tokens.size()).float()
                mean = (tokens * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
                vector = torch.nn.functional.normalize(mean.float(), dim=-1)[0]
                if vector.numel() != 384 or not torch.isfinite(vector).all() or vector.norm() == 0:
                    raise EncoderError("invalid_embedding", "Text encoder returned an invalid vector")
                return vector.tolist()
        except RuntimeError as exc:
            raise EncoderError("encoder_failed", "Text inference failed", reason=str(exc)[:1000]) from exc


@lru_cache(maxsize=1)
def _load(cache):
    return TextEncoder(cache)


_lock = Lock()


def get_text_encoder(cache):
    with _lock:
        return _load(cache)


def main():
    from huggingface_hub import snapshot_download

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["download"])
    parser.parse_args()
    path = checkpoint_path(Path(os.environ.get("MODEL_CACHE", "/models")))
    snapshot_download(MODEL_ID, revision=REVISION, allow_patterns=FILES, local_dir=path)
    print(json.dumps({"checkpoint": str(path), "spec": SPEC}))


if __name__ == "__main__":
    main()
