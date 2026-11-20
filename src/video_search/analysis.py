"""Source-linked description and verification operations."""

from video_search import frames, media, store
from video_search.text_encoder import SPEC as TEXT_SPEC
from video_search.vlm import Client, DEFAULT_SPEC, GEMMA_SPEC, VERIFICATION_SCHEMA_VERSION


def description_spec(settings=None):
    spec = GEMMA_SPEC if settings is not None and settings.vision_provider == "gemma" else DEFAULT_SPEC
    return {**spec, "dimensions": 384, "embedding": TEXT_SPEC,
            "sampling_version": "eight-slots-sorted-actual-pts-v1",
            "runtime": "openai-structured-vision-v1"}


def client(settings):
    if settings.vision_provider == "gemma":
        return Client(settings.voyager_base_url, settings.voyager_api_key, provider="gemma")
    return Client(settings.qwen_base_url, settings.qwen_api_key)


def source(settings, recording, check=None):
    path = media.source_file(settings.media_root, recording["source_path"], upload_root=settings.upload_read_root)
    expected = (recording["size"], recording["mtime_ns"])
    if media.fingerprint(path) != expected or media.hash_source(path, check) != recording["sha256"]:
        raise media.MediaError("source_changed", "Source differs from the indexed recording", path=recording["source_path"])
    return path


def inspect_frames(path, metadata, start, end, check=None):
    images, samples = frames.sample_window(path, metadata, start, end, check, sample_count=8)
    # Sparse-window samples can repeat an earlier frame; present actual chronology to the VLM.
    ordered = sorted(zip(images, samples), key=lambda item: item[1]["source_seconds"])
    return [item[0] for item in ordered], [item[1] for item in ordered]


def verify(settings, recording, query, start, end, context=2):
    model = client(settings)
    inspect_start = max(0, start-context)
    inspect_end = min(recording["metadata"]["duration_seconds"], end+context)
    path = source(settings, recording)
    images, samples = inspect_frames(path, recording["metadata"], inspect_start, inspect_end)
    try:
        result = model.verify(query, images, samples, inspect_start, inspect_end)
    finally:
        for image in images:
            image.close()
    source(settings, recording)
    verification_id = store.save_verification(
        settings.database_url, str(recording["id"]), query, inspect_start, inspect_end,
        {**model.spec, "prompt_version": result["_trace"]["prompt_version"],
         "sampling_version": "eight-slots-sorted-actual-pts-v1",
         "verification_schema_version": VERIFICATION_SCHEMA_VERSION}, samples, result,
    )
    return {"id": verification_id, "recording_id": str(recording["id"]), "query": query,
            "inspection_start_seconds": inspect_start, "inspection_end_seconds": inspect_end,
            "samples": samples, "result": result, "checked_by_model": True,
            "media_url": f"/recordings/{recording['id']}/media"}


def inspect_extent(settings, recording, query, start, end, anchor=None, *, policy="extent", reason="ranked_seed"):
    """Return a saved check and its retained seed frame; the controller closes the frame."""
    if end - start > (8.75 if anchor else 10):
        raise ValueError("Extent windows must preserve at least 0.8 new frame slots per second")
    if anchor is not None and anchor["recording_id"] != str(recording["id"]):
        raise ValueError("A reference frame must belong to the inspected recording")
    model = client(settings)
    path = source(settings, recording)
    images, samples = frames.sample_window(path, recording["metadata"], start, end, sample_count=7 if anchor else 8)
    samples = [{**sample, "is_reference": False} for sample in samples]
    if anchor:
        images.append(anchor["image"].copy())
        samples.append({**anchor["sample"], "requested_seconds": anchor["sample"]["source_seconds"], "is_reference": True})
    ordered = sorted(zip(images, samples), key=lambda item: item[1]["source_seconds"])
    images, samples = [p[0] for p in ordered], [p[1] for p in ordered]
    reference_index = next((i for i, sample in enumerate(samples) if sample["is_reference"]), None)
    evidence_start = min(start, *(min(p["source_seconds"], p["requested_seconds"]) for p in samples))
    evidence_end = max(end, max(max(p["source_seconds"], p["requested_seconds"]) for p in samples) + 1e-9)
    try:
        result = model.inspect_extent(query, images, samples, start, end, reference_index)
        reference = None
        if anchor:
            if result["_trace"]["frame_sha256"][reference_index] != anchor["frame_sha256"]:
                raise media.MediaError("reference_changed", "The reference frame differs from its saved seed",
                                       recording_id=str(recording["id"]), verification_id=anchor["verification_id"])
            reference = {"sample_index": reference_index, "source_seconds": anchor["sample"]["source_seconds"],
                         "frame_sha256": anchor["frame_sha256"], "verification_id": anchor["verification_id"]}
        intervals, run = [], []
        for sample, state in zip(samples, result["sample_support"]):
            if sample["is_reference"]:
                continue
            if state == "present":
                run.append(sample["source_seconds"])
            else:
                if len(run) >= 2 and run[0] < run[-1]:
                    intervals.append({"start_seconds": run[0], "end_seconds": run[-1]})
                run = []
        if len(run) >= 2 and run[0] < run[-1]:
            intervals.append({"start_seconds": run[0], "end_seconds": run[-1]})
        result["intervals"] = intervals if result["status"] == "match" else []
        result["_extent"] = {"new_start_seconds": start, "new_end_seconds": end, "reference": reference,
                             "controller_policy": policy, "inspection_reason": reason,
                             "interval_note": "Intervals span present samples; they do not certify continuous visibility."}
        source(settings, recording)
        verification_id = store.save_verification(
            settings.database_url, str(recording["id"]), query, evidence_start, evidence_end,
            {**model.spec, "prompt_version": result["_trace"]["prompt_version"], "task": "extent",
             "sampling_version": "eight-source-slots-seven-new-one-seed-anchor-v1",
             "extent_schema_version": "sample-support-v5-context-support", "controller_policy": policy}, samples, result,
        )
        retained = anchor
        if anchor is None and result["status"] == "match":
            first = result["sample_support"].index("present")
            last = first
            while last + 1 < len(samples) and result["sample_support"][last + 1] == "present":
                last += 1
            index = (first + last) // 2
            retained = {"image": images[index].copy(), "sample": samples[index], "recording_id": str(recording["id"]),
                        "frame_sha256": result["_trace"]["frame_sha256"][index], "verification_id": verification_id}
        return {"id": verification_id, "recording_id": str(recording["id"]), "query": query,
                "inspection_start_seconds": evidence_start, "inspection_end_seconds": evidence_end,
                "new_start_seconds": start, "new_end_seconds": end, "reference": reference,
                "samples": samples, "result": result, "checked_by_model": True,
                "media_url": f"/recordings/{recording['id']}/media"}, retained
    finally:
        for image in images:
            image.close()
