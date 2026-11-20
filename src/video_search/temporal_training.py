"""Strict, isolated UniVTG feature experiments; no application or hosted-model calls."""

import argparse
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import random
import re
import sys
import time
from types import SimpleNamespace

import numpy as np
import torch
from torch.nn import functional as F
from torch.utils.data import DataLoader, Dataset

from video_search import evaluation
from video_search.evaluation import temporal_iou


UPSTREAM_REVISION = "32659ac7aeba21742a63274f30eba785fc57e247"
TRAIN_METADATA_SHA256 = "cc061d290f5be0735ecfaf80d9f9d09a5032f8b95faef114fe6ce21add2df9aa"
SPLIT_SEED = "temporal-head-video-holdout-v1"
VERSION = "univtg-strict-head-v3"
UPSTREAM_SHA256 = {
    "model/univtg.py": "4451c4f0e9f8ca4c088fcd5251c20e8245aa162cca367e6bf6d684c1fe918297",
    "model/transformer_encoder_droppath.py": "399501234b0f457b1af3a19249bbc5983a0b5dab1d8d8886f124ed6d26acda36",
    "model/matcher.py": "40b8c314b52612aa13e6a7156d1e644762a2dfa2631dd214b497d7d3314e197c",
    "model/position_encoding.py": "64995b7501c6b226afe836d556ae90192402196b692284ae9554e0e9387fcfe8",
    "model/__init__.py": None,
    "utils/span_utils.py": "e1eed63f9062730ac00d030484cdeb7fcc31c1ba17c0c670bb761fe3981b33e2",
    "utils/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def read_metadata(path):
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    seen, durations = set(), {}
    for row in rows:
        qid, vid, duration = str(row["qid"]), row["vid"], row["duration"]
        if (isinstance(row["qid"], bool) or not isinstance(row["qid"], (int, str))
                or qid in seen or not re.fullmatch(r"[A-Za-z0-9_-]+", qid)
                or not isinstance(vid, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", vid)):
            raise ValueError("Metadata requires unique safe query IDs and safe video IDs")
        if (isinstance(duration, bool) or not isinstance(duration, (int, float))
                or not math.isfinite(duration) or duration <= 0 or durations.get(vid, duration) != duration):
            raise ValueError("Metadata requires a consistent positive duration per source")
        if not isinstance(row.get("query"), str) or not row["query"].strip():
            raise ValueError("Metadata requires query text")
        windows = row["relevant_windows"]
        if not isinstance(windows, list) or len(windows) != 1:
            raise ValueError("This Charades experiment requires exactly one target interval per query")
        start, end = windows[0]
        if (any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in (start, end))
                or not 0 <= start < end <= duration):
            raise ValueError("Target interval must be finite, ordered and inside reference duration")
        seen.add(qid)
        durations[vid] = duration
    if len(durations) < 2:
        raise ValueError("At least two source videos are required")
    return rows


def split_rows(rows):
    videos = sorted({r["vid"] for r in rows}, key=lambda vid: hashlib.sha256(f"{SPLIT_SEED}:{vid}".encode()).hexdigest())
    if len(videos) < 2:
        raise ValueError("Video-disjoint development requires at least two videos")
    development = set(videos[:max(1, math.ceil(len(videos) / 10))])
    return ([r for r in rows if r["vid"] not in development],
            [r for r in rows if r["vid"] in development])


def load_array(path, key, width):
    with np.load(path, allow_pickle=False) as archive:
        array = archive[key]
    if (array.ndim != 2 or not 1 <= len(array) <= 512 or array.shape[1] != width
            or array.dtype.kind not in "fiu" or not np.isfinite(array).all()):
        raise ValueError(f"Invalid feature shape, dtype or values: {path} key={key} expected_width={width}")
    array = array.astype(np.float32)
    norms = np.linalg.norm(array, axis=1, keepdims=True)
    if not np.isfinite(norms).all() or (norms == 0).any():
        raise ValueError(f"Invalid zero or overflowing feature row: {path}")
    return array / (norms + 1e-5)


class Features:
    """Preflight and retain every feature once; missing examples are never replaced."""

    def __init__(self, rows, slowfast, clip, text, use_tef=True):
        self.videos, self.text, inventory = {}, {}, []
        for row in rows:
            vid, qid = row["vid"], str(row["qid"])
            if vid not in self.videos:
                streams = []
                for directory, width, label in ((slowfast, 2304, "slowfast"), (clip, 512, "clip")):
                    path = Path(directory) / f"{vid}.npz"
                    streams.append(load_array(path, "features", width))
                    inventory.append((label, vid, file_hash(path)))
                length = min(map(len, streams))
                video = np.concatenate([stream[:length] for stream in streams], axis=1)
                if use_tef:
                    positions = np.arange(length, dtype=np.float32) / length
                    video = np.concatenate([video, np.stack((positions, positions + 1 / length), axis=1)], axis=1)
                self.videos[vid] = torch.from_numpy(video)
            path = Path(text) / f"{qid}.npz"
            self.text[qid] = torch.from_numpy(load_array(path, "last_hidden_state", 512))
            inventory.append(("text", qid, file_hash(path)))
        self.sha256 = digest(sorted(inventory))


class GroundingDataset(Dataset):
    def __init__(self, rows, features):
        self.rows, self.features = rows, features

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        video, text = self.features.videos[row["vid"]], self.features.text[str(row["qid"])]
        length = len(video)
        timestamp = ((torch.arange(length, dtype=torch.float32) + .5) / length).repeat(2, 1).T
        target = torch.tensor(row["relevant_windows"][0], dtype=torch.float32) / length
        inside = (timestamp[:, 0] >= target[0]) & (timestamp[:, 1] <= target[1])
        labels = torch.zeros_like(timestamp)
        labels[inside] = target
        # Match the author's explicit nearest-step rule for a target without an interior sample.
        if not inside.any():
            nearest = min(length - 1, max(0, int(row["relevant_windows"][0][0])))
            inside[nearest] = True
            labels[nearest] = target
        positive = random.choice(inside.nonzero().flatten().tolist())
        return row, video, text, timestamp, labels, inside.float(), positive


def collate(batch):
    videos, texts = [item[1] for item in batch], [item[2] for item in batch]
    lengths = torch.tensor([len(x) for x in videos])
    text_lengths = torch.tensor([len(x) for x in texts])
    pad = torch.nn.utils.rnn.pad_sequence
    mask = (torch.arange(int(lengths.max()))[None] < lengths[:, None]).float()
    inputs = {"src_vid": pad(videos, batch_first=True), "src_txt": pad(texts, batch_first=True),
              "src_vid_mask": mask,
              "src_txt_mask": (torch.arange(int(text_lengths.max()))[None] < text_lengths[:, None]).float()}
    targets = {"timestamp": pad([x[3] for x in batch], batch_first=True),
               "timestamp_mask": mask, "span_labels_nn": pad([x[4] for x in batch], batch_first=True),
               "timestamp_window": pad([x[5] for x in batch], batch_first=True),
               "saliency_scores": pad([x[5] for x in batch], batch_first=True),
               "saliency_pos_labels": torch.tensor([[x[6]] for x in batch])}
    return [x[0] for x in batch], inputs, targets


def quality_foreground_loss(outputs, targets, eos_coef=.1):
    spans = (targets["timestamp"] + outputs["pred_spans"]).detach()
    truth = targets["span_labels_nn"]
    intersection = (torch.minimum(spans[..., 1], truth[..., 1]) - torch.maximum(spans[..., 0], truth[..., 0])).clamp_min(0)
    union = (spans[..., 1] - spans[..., 0]) + (truth[..., 1] - truth[..., 0]) - intersection
    positive = targets["timestamp_window"].bool()
    quality = torch.where(positive, intersection / union.clamp_min(1e-8), 0)
    weights = torch.where(positive, 1., eos_coef) * targets["timestamp_mask"]
    return (F.binary_cross_entropy(outputs["pred_logits"].squeeze(-1), quality, reduction="none") * weights).sum() / targets["timestamp_mask"].sum()


def predictions(outputs, targets, rows):
    spans = targets["timestamp"] + outputs["pred_spans"]
    result = []
    for index, row in enumerate(rows):
        length = int(targets["timestamp_mask"][index].sum())
        values = (spans[index, :length] * row["duration"]).clamp(0, row["duration"]).detach().cpu().tolist()
        scores = outputs["pred_logits"][index, :length, 0].detach().cpu().tolist()
        ranked = sorted(zip(values, scores), key=lambda item: item[1], reverse=True)
        result.append({"qid": row["qid"], "vid": row["vid"], "pred_relevant_windows":
                       [[round(v[0], 4), round(v[1], 4), round(score, 4)] for v, score in ranked]})
    return result


def score_predictions(rows, predicted):
    if not rows:
        raise ValueError("Evaluation requires a nonempty complete query grid")
    if [str(r["qid"]) for r in rows] != [str(p["qid"]) for p in predicted]:
        raise ValueError("Prediction query grid differs from evaluation rows")
    values = []
    for row, prediction in zip(rows, predicted):
        if prediction["vid"] != row["vid"]:
            raise ValueError("Prediction belongs to another video")
        windows = prediction["pred_relevant_windows"]
        max_bound = round(float(np.float32(row["duration"])), 4)
        for window in windows:
            if (len(window) != 3 or any(not math.isfinite(x) for x in window)
                    or not 0 <= window[0] <= window[1] <= max_bound):
                raise ValueError(f"Invalid prediction qid={row['qid']} vid={row['vid']} duration={row['duration']} "
                                 f"float32_4dp_bound={max_bound} window={window}")
        first = windows[:1]
        values.append(temporal_iou(tuple(first[0][:2]), tuple(row["relevant_windows"][0]))
                      if first and first[0][0] < first[0][1] else 0.)
    return {"queries": len(rows), "R1@0.3": sum(x >= .3 for x in values) / len(values),
            "R1@0.5": sum(x >= .5 for x in values) / len(values),
            "R1@0.7": sum(x >= .7 for x in values) / len(values), "mIoU": sum(values) / len(values)}


def validate_model(model, loader, rows):
    if not rows:
        raise ValueError("Validation requires a nonempty complete query grid")
    model.eval()
    predicted = []
    device = next(model.parameters()).device
    with torch.inference_mode():
        for meta, inputs, targets in loader:
            inputs = {k: v.to(device) for k, v in inputs.items()}
            targets = {k: v.to(device) for k, v in targets.items()}
            predicted.extend(predictions(model(**inputs), targets, meta))
    return score_predictions(rows, predicted), predicted


def rng_state():
    name, keys, position, gaussian, cached = np.random.get_state()
    return {"python": random.getstate(), "numpy": (name, keys.tolist(), position, gaussian, cached),
            "torch": torch.get_rng_state(), "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else []}


def restore_rng(state):
    random.setstate(state["python"])
    name, keys, position, gaussian, cached = state["numpy"]
    np.random.set_state((name, np.array(keys, dtype=np.uint32), position, gaussian, cached))
    torch.set_rng_state(state["torch"])
    if state["cuda"]:
        torch.cuda.set_rng_state_all(state["cuda"])


def save_checkpoint(path, value):
    path = Path(path)
    temporary = path.with_suffix(".part")
    with temporary.open("wb") as output:
        torch.save(value, output)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def write_bytes(path, raw):
    path = Path(path)
    temporary = path.with_suffix(".part")
    with temporary.open("wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def stage_epoch(output, state, report, predicted, improved):
    pending = Path(output) / "pending.pt"
    if pending.exists():
        raise ValueError("Finish the pending epoch before staging another one")
    save_checkpoint(pending, {**state, "report": report, "improved": improved,
                              "development_predictions": predicted if improved else None})


def publish_epoch_artifacts(output, state):
    output = Path(output)
    report = state["report"]
    history_path = output / "history.jsonl"
    history = [json.loads(line) for line in history_path.read_bytes().splitlines()] if history_path.exists() else []
    expected = list(range(1, len(history) + 1))
    if [item["epoch"] for item in history] != expected:
        raise ValueError("Training history is not a complete ordered epoch grid")
    epoch = state["next_epoch"]
    if len(history) == epoch:
        if digest(history[-1]) != digest(report):
            raise ValueError("Existing epoch history differs from the pending commit")
    elif len(history) == epoch - 1:
        history.append(report)
    else:
        raise ValueError("Pending epoch does not continue training history")
    if state["improved"]:
        raw = json.dumps({"metrics": report["development"], "predictions": state["development_predictions"]},
                         allow_nan=False).encode() + b"\n"
        path = output / f"development-epoch-{epoch:03d}.json"
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("Existing epoch predictions differ from the pending commit")
        if not path.exists():
            write_bytes(path, raw)
        save_checkpoint(output / "best.pt", state)
    write_bytes(history_path, b"".join(json.dumps(row, allow_nan=False).encode() + b"\n" for row in history))


def recover_pending_epoch(output, identity):
    output = Path(output)
    pending = output / "pending.pt"
    if not pending.exists():
        return False
    state = torch.load(pending, map_location="cpu", weights_only=True)
    if state["protocol_sha256"] != identity:
        raise ValueError("Pending epoch belongs to a different training protocol")
    publish_epoch_artifacts(output, state)
    # The resumable pointer advances only after its winning model and history are durable.
    os.replace(pending, output / "latest.pt")
    return True


def bind_protocol(output, protocol):
    output.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(protocol, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    path = output / "protocol.json"
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("Output directory belongs to a different frozen training protocol")
    else:
        with path.open("xb") as target:
            target.write(raw)
    return digest(protocol)


def upstream_model(upstream, config):
    upstream = Path(upstream).resolve(strict=True)
    for relative, expected in UPSTREAM_SHA256.items():
        path = upstream / relative
        actual = file_hash(path) if path.is_file() else None
        if actual != expected:
            raise ValueError(f"UniVTG runtime source differs from pinned author bytes: {relative}")
    sys.path.insert(0, str(upstream))
    module = importlib.import_module("model.univtg")
    for relative, expected in UPSTREAM_SHA256.items():
        if expected is not None:
            name = relative[:-3].replace("/", ".").removesuffix(".__init__")
            if Path(sys.modules[name].__file__).resolve() != upstream / relative:
                raise ValueError(f"Another imported module shadows pinned UniVTG code: {name}")
    return module.build_model(SimpleNamespace(**config))


def model_config(path):
    config = json.loads(Path(path).read_bytes())
    if (config.get("span_loss_type") != "l1" or config.get("clip_length") != 1
            or config.get("t_feat_dim") != 512 or config.get("v_feat_dim") != 2816
            or config.get("ctx_mode") not in {"video", "video_tef"} or config.get("eval_mode") != "add"):
        raise ValueError("Unsupported author config: require CLIP+SlowFast, 1s, l1 and foreground moment ranking")
    config["use_tef"] = "tef" in config["ctx_mode"]
    config["use_video"] = True
    config["v_feat_dim"] += 2 if config["use_tef"] else 0
    config.update(device="cuda", dset_type="mr", model_id="univtg", train_path="strict_train.jsonl")
    return config


def train(args):
    if not os.environ.get("SLURM_JOB_ID") or not torch.cuda.is_available():
        raise RuntimeError("Training and smoke timing require an allocated Sol CUDA job")
    if (args.variant not in {"baseline", "quality"} or args.epochs < 1 or args.batch_size < 1
            or args.steps < 1 or not math.isfinite(args.learning_rate) or args.learning_rate <= 0):
        raise ValueError("Invalid experiment settings")
    torch.set_num_threads(min(4, int(os.environ.get("SLURM_CPUS_PER_TASK", 4))))
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    config = model_config(args.config)
    config.update(lr=args.learning_rate, n_epoch=args.epochs, bsz=args.batch_size, seed=args.seed,
                  lr_warmup=-1, resume=None, eval_path=None, eval_init=False, num_workers=0,
                  eval_bsz=args.batch_size, main_metric="train-development R1@0.5 then mIoU")
    if file_hash(args.metadata) != TRAIN_METADATA_SHA256:
        raise ValueError("Training requires the pinned author train labels; test or changed labels are forbidden")
    rows = read_metadata(args.metadata)
    training, development = split_rows(rows)
    features = Features(rows, args.slowfast, args.clip, args.text, use_tef=config["v_feat_dim"] == 2818)
    protocol = {"version": VERSION, "action": args.action, "variant": args.variant, "seed": args.seed,
                "epochs": args.epochs, "batch_size": args.batch_size, "learning_rate": args.learning_rate,
                "upstream_revision": UPSTREAM_REVISION, "source_sha256": file_hash(__file__),
                "upstream_runtime_sha256": UPSTREAM_SHA256,
                "evaluator_sha256": file_hash(evaluation.__file__),
                "metadata_sha256": file_hash(args.metadata), "features_sha256": features.sha256,
                "raw_author_config_sha256": file_hash(args.config),
                "config": config, "split_seed": SPLIT_SEED,
                "train_rows_sha256": digest(training), "development_rows_sha256": digest(development),
                "train_queries": len(training), "development_queries": len(development),
                "training_video_ids": sorted({r["vid"] for r in training}),
                "development_video_ids": sorted({r["vid"] for r in development}),
                "model_selection": "Train-video-disjoint development R1@0.5, then mIoU; never official test.",
                "target_protocol": "Author interval labels / aligned feature length; nearest step if no interior sample.",
                "prediction_protocol": "Foreground score, stable descending sort, author float32 duration scaling/clamp and 4dp; exact float32/4dp validation envelope. Point top1 scores zero.",
                "training_protocol": "From scratch, unchanged author model/criterion, CLI learning rate, no warmup; quality variant replaces only loss_f with detached proposal IoU targets at positive steps.",
                "length_protocol": "Preserve all author feature steps; fail above512; never truncate to max_v_l.",
                "runtime": {"torch": torch.__version__, "numpy": np.__version__, "gpu": torch.cuda.get_device_name(0)}}
    output = Path(args.output)
    identity = bind_protocol(output, protocol)
    import fcntl
    run_lock = (output / "run.lock").open("a")
    fcntl.flock(run_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    recover_pending_epoch(output, identity)
    model, criterion = upstream_model(args.upstream, config)
    model = model.cuda()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=config["wd"])
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=config["lr_drop"], gamma=config.get("lr_gamma", .1))
    start_epoch, best = 0, (-1., -1.)
    checkpoint = output / "latest.pt"
    if checkpoint.exists():
        state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        if state["protocol_sha256"] != identity:
            raise ValueError("Checkpoint protocol differs from the frozen run")
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        scheduler.load_state_dict(state["scheduler"])
        start_epoch, best = state["next_epoch"], tuple(state["best"])
        restore_rng(state["rng"])
    train_loader = DataLoader(GroundingDataset(training, features), batch_size=args.batch_size, shuffle=True, collate_fn=collate)
    dev_loader = DataLoader(GroundingDataset(development, features), batch_size=args.batch_size, collate_fn=collate)
    torch.cuda.reset_peak_memory_stats()
    measured, steps = [], 0
    for epoch in range(start_epoch, args.epochs):
        model.train()
        total_loss, count = 0., 0
        epoch_start = time.perf_counter()
        for _, inputs, targets in train_loader:
            inputs = {k: v.cuda() for k, v in inputs.items()}
            targets = {k: v.cuda() for k, v in targets.items()}
            torch.cuda.synchronize()
            begin = time.perf_counter()
            optimizer.zero_grad(set_to_none=True)
            result = model(**inputs)
            losses = criterion(result, targets)
            if args.variant == "quality":
                losses["loss_f"] = quality_foreground_loss(result, targets, config["eos_coef"])
            loss = sum(losses[k] * criterion.weight_dict[k] for k in losses if k in criterion.weight_dict)
            if not torch.isfinite(loss):
                raise FloatingPointError(f"Non-finite training loss epoch={epoch} step={count}")
            loss.backward()
            norm = torch.nn.utils.clip_grad_norm_(model.parameters(), config["grad_clip"], error_if_nonfinite=True)
            optimizer.step()
            torch.cuda.synchronize()
            measured.append(time.perf_counter() - begin)
            total_loss += loss.detach().item()
            count += 1
            steps += 1
            if args.action == "smoke" and steps >= args.steps:
                timing = measured[2:] or measured
                validation_start = time.perf_counter()
                metrics, _ = validate_model(model, dev_loader, development)
                validation_seconds = time.perf_counter() - validation_start
                smoke_state = {"protocol_sha256": identity, "model": model.state_dict(),
                               "optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict(),
                               "rng": rng_state(), "training_steps": steps, "completed_epochs": 0}
                save_checkpoint(output / "smoke-state.pt", smoke_state)
                restored = torch.load(output / "smoke-state.pt", map_location="cpu", weights_only=True)
                model.load_state_dict(restored["model"])
                optimizer.load_state_dict(restored["optimizer"])
                scheduler.load_state_dict(restored["scheduler"])
                restore_rng(restored["rng"])
                report = {"event": "smoke_complete", "steps": steps, "seconds_per_step": sum(timing) / len(timing),
                          "estimated_training_hours": sum(timing) / len(timing) * len(train_loader) * args.epochs / 3600,
                          "validation": metrics, "validation_seconds": validation_seconds,
                          "checkpoint_roundtrip": "model-optimizer-scheduler-rng-weights-only-passed",
                          "estimated_training_and_validation_hours": (sum(timing) / len(timing) * len(train_loader)
                                                                      + validation_seconds) * args.epochs / 3600,
                          "estimate_scope": "Training batches and measured full validation; excludes startup and checkpoint time.",
                          "peak_cuda_bytes": torch.cuda.max_memory_allocated(), "gpu": torch.cuda.get_device_name(0),
                          "parameters": sum(p.numel() for p in model.parameters()), "protocol_sha256": identity}
                with (output / "smoke.json").open("x", encoding="utf-8") as target:
                    json.dump(report, target, indent=2)
                print(json.dumps(report), flush=True)
                return report
        scheduler.step()
        metrics, predicted = validate_model(model, dev_loader, development)
        current = (metrics["R1@0.5"], metrics["mIoU"])
        improved = current > best
        best = max(best, current)
        report = {"event": "epoch_complete", "epoch": epoch + 1, "train_batches": count,
                  "mean_train_loss": total_loss / count, "development": metrics, "best": best,
                  "epoch_seconds": time.perf_counter() - epoch_start,
                  "peak_cuda_bytes": torch.cuda.max_memory_allocated(), "last_gradient_norm": float(norm)}
        state = {"protocol_sha256": identity, "model": model.state_dict(), "optimizer": optimizer.state_dict(),
                 "scheduler": scheduler.state_dict(), "next_epoch": epoch + 1, "best": best, "rng": rng_state()}
        stage_epoch(output, state, report, predicted, improved)
        recover_pending_epoch(output, identity)
        print(json.dumps(report), flush=True)
    return {"event": "training_complete", "epochs": args.epochs, "best": best, "protocol_sha256": identity}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("train", "smoke"))
    for name in ("upstream", "metadata", "slowfast", "clip", "text", "config", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--variant", choices=("baseline", "quality"), default="baseline")
    parser.add_argument("--seed", type=int, choices=(2018, 2019, 2020), default=2018)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--steps", type=int, default=20)
    print(json.dumps(train(parser.parse_args())), flush=True)
