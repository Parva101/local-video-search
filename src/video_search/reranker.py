"""Optional pinned text reranking of retrieved video descriptions."""

import argparse
from functools import lru_cache
import json
import os
from pathlib import Path
from threading import Lock

from pydantic import ValidationError

from video_search.encoder import EncoderError
from video_search.vlm import Description


MODEL_ID = "cross-encoder/ms-marco-MiniLM-L6-v2"
REVISION = "233902d25c440f23af6f7d6e94d2946bac0bee0a"
SPEC = {"model_id": MODEL_ID, "revision": REVISION, "max_tokens": 512, "max_candidates": 24,
        "text_recipe": "query-paired-with-summary-actions-objects-space-joined-v1",
        "score_definition": "raw-classifier-logit-descending-not-probability",
        "runtime": "torch-2.9.0-transformers-4.57.6-cpu-float32-threads4"}
FILES = ["config.json", "model.safetensors", "special_tokens_map.json", "tokenizer.json",
         "tokenizer_config.json", "vocab.txt"]


def checkpoint_path(cache: Path) -> Path:
    return cache / "ms-marco-MiniLM-L6-v2" / REVISION


def _candidate_texts(query, candidates):
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 1000:
        raise EncoderError("invalid_query", "Reranking query must contain 1..1000 characters")
    if not isinstance(candidates, list) or len(candidates) > SPEC["max_candidates"]:
        raise EncoderError("invalid_candidates", "Reranking requires a list of at most 24 candidates")
    texts = []
    for rank, candidate in enumerate(candidates, 1):
        description = candidate.get("description") if isinstance(candidate, dict) else None
        if not isinstance(description, dict):
            raise EncoderError("invalid_description", "Reranking requires a description for each candidate", retrieval_rank=rank)
        try:
            payload = Description.model_validate({key: value for key, value in description.items() if key != "_trace"})
        except ValidationError as exc:
            raise EncoderError("invalid_description", "Candidate description does not match the required schema", retrieval_rank=rank) from exc
        texts.append(" ".join([payload.summary, *payload.actions, *payload.objects]))
    return texts


class Reranker:
    def __init__(self, cache):
        path = checkpoint_path(cache)
        if not all((path / name).is_file() for name in FILES):
            raise EncoderError("model_not_installed", "Run python -m video_search.reranker download first")
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        torch.set_num_threads(4)
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
            self.model = AutoModelForSequenceClassification.from_pretrained(
                path, local_files_only=True, trust_remote_code=False, use_safetensors=True,
            ).to(device="cpu", dtype=torch.float32).eval()
        except (OSError, ValueError, RuntimeError) as exc:
            raise EncoderError("encoder_failed", "Reranker could not be loaded", reason=str(exc)[:1000]) from exc
        self.lock = Lock()

    def rank(self, query, candidates):
        import torch

        texts = _candidate_texts(query, candidates)
        if not texts:
            return []
        try:
            with self.lock, torch.inference_mode():
                inputs = self.tokenizer([query] * len(texts), texts, padding=True, truncation=False, return_tensors="pt")
                if inputs["input_ids"].shape[1] > SPEC["max_tokens"]:
                    raise EncoderError("text_too_long", "A query/description pair exceeds the reranker's 512-token budget")
                scores = self.model(**inputs).logits
                if scores.shape != (len(candidates), 1) or not torch.isfinite(scores).all():
                    raise EncoderError("encoder_failed", "Reranker returned invalid scores")
                values = scores[:, 0].tolist()
        except RuntimeError as exc:
            raise EncoderError("encoder_failed", "Reranking inference failed", reason=str(exc)[:1000]) from exc
        ordered = sorted(range(len(candidates)), key=lambda index: (-values[index], index))
        return [{**candidates[index], "retrieval_rank": index + 1, "rerank_score": values[index]} for index in ordered]


@lru_cache(maxsize=1)
def _load(cache):
    return Reranker(cache)


_lock = Lock()


def get_reranker(cache):
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
