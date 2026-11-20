"""Speech and subtitle transcripts for a third search path."""

import argparse
import hashlib
import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path
from threading import Lock

from video_search.text_encoder import SPEC as TEXT_SPEC


ASR_MODEL_ID = "openai/whisper-base"
ASR_REVISION = "e37978b90ca9030d5170a5c07aadb050351a65bb"
ASR_FILES = ["added_tokens.json", "config.json", "generation_config.json", "merges.txt", "model.safetensors",
             "normalizer.json", "preprocessor_config.json", "special_tokens_map.json", "tokenizer.json",
             "tokenizer_config.json", "vocab.json"]


SRT_TIME = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{1,3})")
VTT_TIME = re.compile(r"(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})")
SUBTITLE_MAX_BYTES = 2 * 1024 * 1024


class TranscriptError(ValueError):
    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code = code
        self.details = details


def subtitle_spec(kind: str, content: str) -> dict:
    """Identity of one supplied-subtitle import; the content hash makes re-imports idempotent."""
    if kind not in ("srt", "vtt"):
        raise TranscriptError("invalid_subtitle_format", "Subtitle format must be srt or vtt")
    if not isinstance(content, str) or not content.strip() or len(content.encode("utf-8")) > SUBTITLE_MAX_BYTES:
        raise TranscriptError("invalid_subtitle", "Subtitle content must be non-empty UTF-8 text under two megabytes")
    return {
        "source": "subtitle", "format": kind, "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "dimensions": 384, "text_encoder": TEXT_SPEC["model_id"], "text_encoder_revision": TEXT_SPEC["revision"],
        "runtime": "python-stdlib-parser-v1",
    }


def audio_stream_origin(value: object) -> float | None:
    """The recorded audio-stream origin when it is a finite nonnegative number, else None."""
    try:
        origin = float(value)
    except (TypeError, ValueError):
        return None
    return origin if math.isfinite(origin) and origin >= 0 else None


def asr_spec(audio_start: object = None) -> dict:
    return {
        "source": "asr", "model_id": ASR_MODEL_ID, "revision": ASR_REVISION,
        "dimensions": 384, "text_encoder": TEXT_SPEC["model_id"], "text_encoder_revision": TEXT_SPEC["revision"],
        "audio": "ffmpeg-mono-16khz-pcm-v1",
        # Whisper times are audio-stream-relative; the rule records whether the stream's source origin was added.
        "origin_rule": ("audio-stream-origin-corrected-v2" if audio_stream_origin(audio_start) is not None
                        else "audio-stream-start-assumed-zero-v1"),
        "runtime": f"torch-cpu-float32-chunked-30s-v1",
    }


def asr_checkpoint_path(cache: Path) -> Path:
    return Path(cache) / "whisper-base" / ASR_REVISION


def download_asr(cache: Path) -> Path:
    from huggingface_hub import snapshot_download

    path = asr_checkpoint_path(cache)
    snapshot_download(ASR_MODEL_ID, revision=ASR_REVISION, allow_patterns=ASR_FILES, local_dir=path)
    return path


class WhisperASR:
    """Pinned local Whisper transcription; chunked long-form with sentence-level timestamps."""

    def __init__(self, cache):
        import torch
        from transformers import AutoProcessor, WhisperForConditionalGeneration

        path = asr_checkpoint_path(cache)
        if not all((path / filename).is_file() for filename in ASR_FILES):
            raise TranscriptError("asr_not_installed", "Run python -m video_search.speech download before speech indexing")
        torch.set_num_threads(4)
        try:
            self.processor = AutoProcessor.from_pretrained(path, local_files_only=True, trust_remote_code=False)
            self.model = WhisperForConditionalGeneration.from_pretrained(
                path, local_files_only=True, trust_remote_code=False, use_safetensors=True
            ).to(device="cpu", dtype=torch.float32).eval()
        except (OSError, ValueError, RuntimeError) as exc:
            raise TranscriptError("asr_failed", "The local speech checkpoint could not be loaded",
                                  reason=str(exc)[:1000]) from exc
        self.lock = Lock()

    def transcribe(self, wav_path) -> list[tuple[float, float, str]]:
        import torch

        try:
            with self.lock, torch.inference_mode():
                from transformers import pipeline as hf_pipeline

                asr = hf_pipeline("automatic-speech-recognition", model=self.model,
                                  tokenizer=self.processor.tokenizer,
                                  feature_extractor=self.processor.feature_extractor,
                                  chunk_length_s=30, batch_size=1, device="cpu")
                output = asr(str(wav_path), return_timestamps=True)
        except (OSError, ValueError, RuntimeError) as exc:
            raise TranscriptError("asr_failed", "Speech transcription failed", reason=str(exc)[:1000]) from exc
        segments = []
        for chunk in output.get("chunks") or []:
            text = str(chunk.get("text") or "").strip()
            stamp = chunk.get("timestamp") or (None, None)
            start, end = stamp[0], stamp[1] if isinstance(stamp, (list, tuple)) and len(stamp) > 1 else None
            if not text or start is None or end is None or not math.isfinite(float(start)) or not math.isfinite(float(end)):
                continue
            if float(end) > float(start):
                segments.append((float(start), float(end), text))
        return segments


@lru_cache(maxsize=1)
def _load_asr(cache: Path) -> WhisperASR:
    return WhisperASR(cache)


_asr_lock = Lock()


def get_asr(cache: Path) -> WhisperASR:
    with _asr_lock:
        return _load_asr(cache)


def _seconds(hours: str, minutes: str, seconds: str, millis: str) -> float:
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis.ljust(3, "0")) / 1000


def _clean(lines: list[str]) -> str:
    text = " ".join(part.strip() for part in lines if part.strip())
    return re.sub(r"\s+", " ", text).strip()


def _validate(segments: list[tuple[float, float, str]], duration: float | None) -> list[tuple[float, float, str]]:
    if not segments:
        raise TranscriptError("empty_transcript", "No subtitle cues with text were found")
    cleaned = []
    for index, (start, end, text) in enumerate(segments):
        if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end:
            raise TranscriptError("invalid_cue", "A subtitle cue has a non-positive or reversed time range",
                                  cue=index + 1, start=start, end=end)
        if not text:
            raise TranscriptError("empty_cue_text", "A subtitle cue has no text", cue=index + 1)
        if duration is not None and end > duration + 0.05:
            raise TranscriptError("cue_outside_recording", "A subtitle cue ends after the recording duration",
                                  cue=index + 1, end=end, duration_seconds=duration)
        cleaned.append((start, end, text))
    if duration is not None and any(end > duration + 0.05 for _, end, _ in cleaned):
        raise TranscriptError("cue_outside_recording", "A subtitle cue ends after the recording duration")
    return cleaned


def _cue_blocks(lines: list[str]) -> list[list[str]]:
    blocks, block = [], []
    for line in lines:
        if not line.strip():
            if block:
                blocks.append(block)
                block = []
        else:
            block.append(line)
    if block:
        blocks.append(block)
    return blocks


def parse_srt(content: str, duration: float | None = None) -> list[tuple[float, float, str]]:
    segments = []
    for block in _cue_blocks(content.replace("\r\n", "\n").split("\n")):
        time_line = next((index for index, line in enumerate(block) if SRT_TIME.search(line)), None)
        if time_line is None:
            raise TranscriptError("invalid_cue", "A subtitle block has no SRT time line", block=" ".join(block)[:200])
        match = SRT_TIME.search(block[time_line])
        start = _seconds(match.group(1), match.group(2), match.group(3), match.group(4))
        end = _seconds(match.group(5), match.group(6), match.group(7), match.group(8))
        text = _clean(block[time_line + 1:])
        if text:
            segments.append((start, end, text))
    return _validate(segments, duration)


def parse_vtt(content: str, duration: float | None = None) -> list[tuple[float, float, str]]:
    body = content.replace("\r\n", "\n")
    header, _, rest = body.partition("\n")
    if "WEBVTT" not in header:
        raise TranscriptError("invalid_vtt_header", "A WebVTT file must begin with WEBVTT")
    segments = []
    for block in _cue_blocks(rest.split("\n")):
        if block[0].startswith("NOTE") or block[0].startswith("STYLE") or block[0].startswith("REGION"):
            continue
        time_line = next((index for index, line in enumerate(block) if VTT_TIME.search(line)), None)
        if time_line is None:
            raise TranscriptError("invalid_cue", "A cue block has no VTT time line", block=" ".join(block)[:200])
        match = VTT_TIME.search(block[time_line])
        start = _seconds(match.group(1) or "0", match.group(2), match.group(3), match.group(4))
        end = _seconds(match.group(5) or "0", match.group(6), match.group(7), match.group(8))
        text = _clean(block[time_line + 1:])
        if text:
            segments.append((start, end, text))
    return _validate(segments, duration)


def main():
    parser = argparse.ArgumentParser(description="Inspect subtitles or install the pinned speech model")
    parser.add_argument("action", choices=["parse", "download"])
    parser.add_argument("path", type=Path, nargs="?", default=None)
    args = parser.parse_args()
    if args.action == "download":
        cache = Path(os.environ.get("MODEL_CACHE", "/models"))
        print(json.dumps({"checkpoint": str(download_asr(cache)), "spec": asr_spec()}))
        return
    content = args.path.read_text(encoding="utf-8")
    kind = "vtt" if args.path.suffix.lower() == ".vtt" else "srt"
    segments = (parse_vtt if kind == "vtt" else parse_srt)(content)
    print(json.dumps({"format": kind, "spec": subtitle_spec(kind, content),
                      "segments": [{"start_seconds": s, "end_seconds": e, "text": t} for s, e, t in segments]}))


if __name__ == "__main__":
    main()
