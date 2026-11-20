"use strict";

const byId = (id) => document.getElementById(id);
const state = {config: null, recordings: [], jobs: [], builds: [], visualBuilds: [], transcriptBuilds: [], selected: null, uploadBusy: false, queryBusy: false, pollBusy: false, uploadId: null, file: null, queryImage: null};

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function showError(id, message) {
  byId(id).textContent = message;
  byId(id).hidden = !message;
}

function errorText(body, response) {
  let message = body.message || (typeof body.detail === "string" ? body.detail : body.code);
  if (!message) message = JSON.stringify(body.detail || body);
  if (body.details?.completed_evidence_checks?.length) message += `\nSaved source checks: ${body.details.completed_evidence_checks.join(", ")}`;
  const requestId = body.request_id || response.headers.get("X-Request-ID");
  return `HTTP ${response.status}: ${message}${requestId ? `\nRequest ID: ${requestId}` : ""}`;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const text = await response.text();
  let body;
  try { body = text ? JSON.parse(text) : {}; }
  catch { throw new Error(`HTTP ${response.status}: The server returned an unreadable reply. ${text.slice(0, 300)}`); }
  if (!response.ok) throw new Error(errorText(body, response));
  return body;
}

const post = (path, body) => api(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: body === undefined ? undefined : JSON.stringify(body)});

function timeLabel(seconds) {
  const value = Math.max(0, Number(seconds));
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const secs = (value % 60).toFixed(1).padStart(4, "0");
  return `${hours ? `${hours}:` : ""}${String(minutes).padStart(2, "0")}:${secs}`;
}

function recordingName(recording) {
  return recording.original_filename || recording.metadata?.original_filename || recording.source_path.split("/").pop();
}

function activeBuild(recordingId) {
  return state.builds.find((build) => build.recording_id === recordingId && build.config_key === state.config.description_config_key);
}

function selectedRecording() { return state.recordings.find((recording) => recording.id === state.selected); }

function hasReadyTranscript(recordingId) {
  return state.transcriptBuilds.some((item) => item.recording_id === recordingId && item.state === "ready");
}

function anyReadyIndex() {
  return activeBuild(state.selected)?.state === "ready" || hasReadyTranscript(state.selected)
      || state.builds.some((item) => item.state === "ready");
}

function setButtons() {
  byId("search-policy").disabled = state.queryBusy || byId("search-path").value === "speech";
  byId("upload-button").disabled = state.uploadBusy || !state.file || !state.config?.uploads_enabled;
  byId("video-file").disabled = state.uploadBusy;
  byId("upload-button").textContent = state.uploadBusy ? "Uploading…" : "Upload & index";
  byId("ask-button").disabled = state.queryBusy
      || (!byId("all-videos").checked
          && activeBuild(state.selected)?.state !== "ready" && !hasReadyTranscript(state.selected))
      || (byId("all-videos").checked && !anyReadyIndex());
  byId("ask-button").textContent = state.queryBusy ? "Checking frames…" : "Find & check ↗";
}

byId("search-path").addEventListener("change", setButtons);
byId("all-videos").addEventListener("change", setButtons);

function clearAnswers() {
  byId("answer-list").replaceChildren();
  byId("player").pause();
  byId("player").removeAttribute("src");
  byId("player").load();
  byId("player-wrap").hidden = true;
  byId("query-progress").textContent = "";
  showError("query-error", "");
  showError("playback-error", "");
}

function selectRecording(id) {
  if (state.queryBusy || id === state.selected) return;
  state.selected = id;
  localStorage.setItem("video-search-selected", id);
  clearAnswers();
  renderLibrary();
}

async function indexRecording(recording) {
  showError("page-error", "");
  try {
    await post(`/recordings/${recording.id}/description-index`);
    await refresh();
  } catch (error) { showError("page-error", error.message); }
}

async function visualIndexRecording(recording) {
  showError("page-error", "");
  try {
    await post(`/recordings/${recording.id}/visual-index`);
    await refresh();
  } catch (error) { showError("page-error", error.message); }
}

async function speechIndexRecording(recording) {
  showError("page-error", "");
  try {
    await post(`/recordings/${recording.id}/transcript-index`);
    await refresh();
  } catch (error) { showError("page-error", error.message); }
}

async function retryJob(job) {
  showError("page-error", "");
  try { await post(`/jobs/${job.id}/retry`); await refresh(); }
  catch (error) { showError("page-error", error.message); }
}

function renderLibrary() {
  const list = byId("recordings");
  list.replaceChildren();
  byId("library-count").textContent = state.recordings.length;
  if (!state.recordings.length) list.append(node("p", "empty-small", "Your uploaded videos will appear here."));
  for (const recording of state.recordings) {
    const build = activeBuild(recording.id);
    const item = node("div", `recording${recording.id === state.selected ? " selected" : ""}`);
    const button = node("button", "recording-button");
    button.type = "button";
    button.disabled = state.queryBusy;
    button.setAttribute("aria-pressed", String(recording.id === state.selected));
    button.append(node("span", "recording-name", recordingName(recording)));
    const meta = node("span", "recording-meta");
    meta.append(node("span", "", timeLabel(recording.metadata.duration_seconds)));
    const labels = {ready: "Ready", running: "Indexing", queued: "Queued", failed: "Index failed"};
    meta.append(node("span", `status-pill ${build?.state || ""}`, labels[build?.state] || "Not indexed"));
    if (build && build.state !== "ready") meta.append(node("span", "", `${build.completed_windows}/${build.total_windows} windows`));
    button.append(meta);
    button.addEventListener("click", () => selectRecording(recording.id));
    item.append(button);
    if (!build) {
      const index = node("button", "secondary", "Index with current model");
      index.type = "button";
      index.disabled = state.queryBusy;
      index.addEventListener("click", async () => { index.disabled = true; await indexRecording(recording); });
      item.append(index);
    }
    const visual = state.visualBuilds.filter((item) => item.recording_id === recording.id);
    const visualState = visual.length ? visual[0].state : null;
    if (build && !visual.length) {
      const visualIndex = node("button", "secondary", "Build visual index (for image questions)");
      visualIndex.type = "button";
      visualIndex.disabled = state.queryBusy;
      visualIndex.addEventListener("click", async () => { visualIndex.disabled = true; await visualIndexRecording(recording); });
      item.append(visualIndex);
    } else if (build && visualState && visualState !== "ready" && visualState !== "failed") {
      item.append(node("span", "small muted", `Visual index ${visualState === "running" ? "building" : "queued"}…`));
    }
    const transcripts = state.transcriptBuilds.filter((item) => item.recording_id === recording.id);
    const transcriptState = transcripts.length ? transcripts[0].state : null;
    if (build && !transcripts.length) {
      const speechIndex = node("button", "secondary", "Index speech (local ASR)");
      speechIndex.type = "button";
      speechIndex.disabled = state.queryBusy || !recording.metadata?.has_audio;
      if (!recording.metadata?.has_audio) speechIndex.title = "This recording has no audio stream.";
      speechIndex.addEventListener("click", async () => { speechIndex.disabled = true; await speechIndexRecording(recording); });
      item.append(speechIndex);
    } else if (build && transcriptState && transcriptState !== "ready" && transcriptState !== "failed") {
      item.append(node("span", "small muted", `Speech index ${transcriptState === "running" ? "building" : "queued"}…`));
    }
    const dateRow = node("div", "recording-date-row");
    const dateInput = node("input", "recording-date");
    dateInput.type = "date";
    dateInput.value = recording.capture_date || "";
    dateInput.disabled = state.queryBusy;
    dateInput.setAttribute("aria-label", `Capture date for ${recordingName(recording)}`);
    dateInput.addEventListener("change", async () => {
      try {
        await post(`/recordings/${recording.id}/capture-date`, {capture_date: dateInput.value || null});
        await refresh();
      } catch (error) { showError("page-error", error.message); }
    });
    dateRow.append(dateInput, node("span", "date-chip",
      recording.capture_date_source === "file_mtime" ? "from file time" : recording.capture_date ? "set by you" : "no date yet"));
    item.append(dateRow);
    list.append(item);
  }
  const selected = selectedRecording();
  const build = activeBuild(state.selected);
  byId("selected-video").textContent = selected
    ? `${recordingName(selected)} · ${build?.state === "ready" ? "Ready for questions" : "Indexing must finish before questions can run"}`
    : "Select an indexed video from your library.";
  setButtons();
}

function renderJobs() {
  const list = byId("pending-jobs");
  list.replaceChildren();
  for (const job of state.jobs.filter((item) => item.state === "queued" || item.state === "running" || item.state === "failed")) {
    const build = state.builds.find((item) => item.id === job.description_build_id);
    const previousBuild = job.kind === "description" && build && build.config_key !== state.config.description_config_key;
    const row = node("div", "job-row");
    const name = job.original_filename || job.source_path.split("/").pop();
    const stage = job.kind === "description" ? "Index" : job.kind === "visual" ? "Visual index" : "Import";
    row.append(node("strong", "", `${stage}: ${name}`), node("span", "", `${job.state}${job.state === "running" ? " — work continues if you close this page" : ""}`));
    if (job.state === "failed") {
      if (previousBuild) {
        row.append(node("p", "small", "Earlier model settings. This failed index is kept for reference. Use the index shown with the video."));
        list.append(row);
        continue;
      }
      row.append(node("p", "job-error", job.error?.message || job.error?.code || "The job failed. Check the server logs."));
      const retry = node("button", "secondary", "Retry job");
      retry.type = "button";
      retry.addEventListener("click", async () => { retry.disabled = true; await retryJob(job); });
      row.append(retry);
    }
    list.append(row);
  }
}

async function refresh() {
  if (state.pollBusy || !state.config) return;
  state.pollBusy = true;
  try {
    const [recordings, jobs, builds, visualBuilds, transcriptBuilds] = await Promise.all([api("/recordings?limit=1000"), api("/jobs?limit=1000"), api("/description-indexes?limit=1000"), api("/visual-indexes?limit=1000"), api("/transcript-indexes?limit=1000")]);
    state.recordings = recordings;
    state.jobs = jobs;
    state.builds = builds;
    state.visualBuilds = visualBuilds;
    state.transcriptBuilds = transcriptBuilds;
    if (!state.selected && recordings.length) {
      state.selected = recordings[0].id;
      localStorage.setItem("video-search-selected", state.selected);
    }
    renderLibrary();
    renderJobs();
  } finally { state.pollBusy = false; }
}

function uploadFile(file, uploadId) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", `/uploads?filename=${encodeURIComponent(file.name)}`);
    request.setRequestHeader("Content-Type", "application/octet-stream");
    request.setRequestHeader("X-Upload-ID", uploadId);
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        const percent = Math.round(event.loaded / event.total * 100);
        byId("upload-progress").value = percent;
        byId("upload-progress-label").textContent = percent < 100 ? `Uploading · ${percent}%` : "Upload received · saving and queueing import…";
      }
    });
    request.addEventListener("load", () => {
      let body;
      try { body = JSON.parse(request.responseText); }
      catch { reject(new Error(`HTTP ${request.status}: ${request.responseText.slice(0, 300) || "Unreadable upload reply"}`)); return; }
      if (request.status >= 200 && request.status < 300) resolve(body);
      else reject(new Error(errorText(body, {status: request.status, headers: {get: (key) => request.getResponseHeader(key)}})));
    });
    request.addEventListener("error", () => reject(new Error("Upload connection failed. Keep the same file selected and try again; the upload ID will be reused.")));
    request.addEventListener("abort", () => reject(new Error("Upload stopped before completion.")));
    request.send(file);
  });
}

byId("video-file").addEventListener("change", () => {
  state.file = byId("video-file").files[0] || null;
  state.uploadId = state.file ? crypto.randomUUID() : null;
  byId("file-name").textContent = state.file ? `${state.file.name} · ${(state.file.size / 1048576).toFixed(1)} MB` : "No file selected";
  showError("upload-error", "");
  byId("upload-message").textContent = "";
  setButtons();
});

byId("upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.uploadBusy || !state.file) return;
  if (state.file.size > state.config.upload_max_bytes) { showError("upload-error", "This file exceeds the upload limit. Choose a smaller video."); return; }
  if (!state.file.size) { showError("upload-error", "This file is empty. Choose a video with content."); return; }
  state.uploadBusy = true;
  setButtons();
  showError("upload-error", "");
  byId("upload-message").textContent = "";
  byId("upload-progress-wrap").hidden = false;
  byId("upload-progress").value = 0;
  byId("upload-progress-label").textContent = "Uploading · 0%";
  try {
    const result = await uploadFile(state.file, state.uploadId);
    byId("upload-message").textContent = "Upload saved. Import and indexing are queued. You can close this page while they run.";
    localStorage.setItem("video-search-upload-job", result.job.id);
    await refresh();
  } catch (error) { showError("upload-error", error.message); }
  finally { state.uploadBusy = false; byId("upload-progress-wrap").hidden = true; setButtons(); }
});

function updatePolicyOptions() {
  const blocked = Boolean(state.queryImage);
  for (const option of byId("search-policy").options) {
    option.disabled = blocked && (option.value === "reranked" || option.value === "extent");
    if (option.disabled && option.selected) byId("search-policy").value = "adaptive";
  }
}

function localISO(value) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

function scopeDates(queryText) {
  let mode = byId("time-scope").value;
  if (mode === "all") {
    const lower = queryText.toLowerCase();
    if (/\btoday\b/.test(lower)) mode = "today";
    else if (/\byesterday\b/.test(lower)) mode = "yesterday";
    else if (/\b(this|last) week\b/.test(lower)) mode = "week";
    else if (/\b(this|last) month\b/.test(lower)) mode = "month";
  }
  if (mode === "all") return {mode, start: null, end: null, fromText: false};
  const now = new Date();
  const day = (offset) => localISO(new Date(now.getFullYear(), now.getMonth(), now.getDate() - offset));
  if (mode === "today") return {mode, start: day(0), end: day(0), fromText: byId("time-scope").value === "all"};
  if (mode === "yesterday") return {mode, start: day(1), end: day(1), fromText: byId("time-scope").value === "all"};
  if (mode === "week") return {mode, start: day(6), end: day(0), fromText: byId("time-scope").value === "all"};
  if (mode === "month") return {mode, start: day(29), end: day(0), fromText: byId("time-scope").value === "all"};
  return {mode, start: byId("scope-start").value || null, end: byId("scope-end").value || null, fromText: false};
}

byId("time-scope").addEventListener("change", () => {
  byId("scope-custom").hidden = byId("time-scope").value !== "custom";
});

byId("file-dates-button").addEventListener("click", async () => {
  const button = byId("file-dates-button");
  button.disabled = true;
  showError("page-error", "");
  try {
    const result = await post("/recordings/capture-dates/from-files", {utc_offset_minutes: -new Date().getTimezoneOffset()});
    await refresh();
    button.textContent = result.count ? `Set ${result.count} date${result.count === 1 ? "" : "s"}` : "All dated";
    setTimeout(() => { button.textContent = "Use file dates"; }, 4000);
  } catch (error) { showError("page-error", error.message); }
  finally { button.disabled = false; }
});

byId("query-image").addEventListener("change", () => {
  const file = byId("query-image").files[0] || null;
  showError("query-error", "");
  const idleText = "No image attached. With an image, search combines image similarity and description text.";
  if (!file) {
    state.queryImage = null;
    byId("query-image-name").textContent = idleText;
    updatePolicyOptions();
    return;
  }
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
    state.queryImage = null;
    byId("query-image-name").textContent = "Unsupported image. Attach a JPEG, PNG or WebP picture.";
    updatePolicyOptions();
    return;
  }
  if (file.size > 10 * 1048576) {
    state.queryImage = null;
    byId("query-image-name").textContent = "This image exceeds 10 MB. Attach a smaller picture.";
    updatePolicyOptions();
    return;
  }
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    const payload = String(reader.result);
    state.queryImage = payload.slice(payload.indexOf(",") + 1);
    byId("query-image-name").textContent = `${file.name} · ${(file.size / 1048576).toFixed(1)} MB — searching by image and text (hybrid)`;
    updatePolicyOptions();
  });
  reader.addEventListener("error", () => {
    state.queryImage = null;
    byId("query-image-name").textContent = "The image could not be read. Attach it again.";
    updatePolicyOptions();
  });
  reader.readAsDataURL(file);
});

function playAt(url, seconds, end) {
  const player = byId("player");
  byId("player-wrap").hidden = false;
  showError("playback-error", "");
  byId("player-caption").textContent = seconds === end ? `At ${timeLabel(seconds)}` : `${timeLabel(seconds)}–${timeLabel(end)}`;
  const seek = () => { player.currentTime = seconds; player.focus(); };
  if (player.getAttribute("src") !== url) {
    player.addEventListener("loadedmetadata", seek, {once: true});
    player.src = url;
    player.load();
  } else if (player.readyState >= 1) seek();
  else player.addEventListener("loadedmetadata", seek, {once: true});
  byId("player-wrap").scrollIntoView({block: "nearest"});
}

byId("player").addEventListener("error", () => {
  if (byId("player").getAttribute("src")) showError("playback-error", "The browser could not play this source video. Check that the source is available and that your browser supports its codec.");
});

function answerCard(candidate, checked, rank) {
  const result = checked.result;
  const card = node("article", "answer-card");
  const top = node("div", "answer-top");
  const labels = {match: "Match in checked frames", no_match: "No match in checked frames", insufficient_evidence: "Not enough evidence"};
  top.append(node("span", "answer-label", `Checked result ${rank}`), node("span", `status-pill ${result.status}`, labels[result.status]));
  card.append(top, node("p", "answer-observation", result.observation));
  if (result._trace?.localization_warning) card.append(node("p", "small muted", "The model's context judgment has no supporting sample timestamp. This check cannot locate an event."));
  const times = node("div", "answer-times");
  const intervals = result.intervals.length ? result.intervals : [{start_seconds: checked.new_start_seconds ?? checked.inspection_start_seconds, end_seconds: checked.new_end_seconds ?? checked.inspection_end_seconds}];
  for (const interval of intervals) {
    const point = interval.start_seconds === interval.end_seconds;
    const time = node("button", "timestamp", point ? `At ${timeLabel(interval.start_seconds)}` : `▶ ${timeLabel(interval.start_seconds)}–${timeLabel(interval.end_seconds)}`);
    time.type = "button";
    time.setAttribute("aria-label", point ? `Open source video at ${timeLabel(interval.start_seconds)}` : `Open source video from ${timeLabel(interval.start_seconds)} to ${timeLabel(interval.end_seconds)}`);
    time.addEventListener("click", () => playAt(checked.media_url, interval.start_seconds, interval.end_seconds));
    times.append(time);
  }
  card.append(times);
  card.append(node("p", "small muted", `Model checked ${checked.samples.length} ${checked.samples.length === 1 ? "frame" : "frames"} in this source check.`));
  const details = node("details", "answer-details");
  details.append(node("summary", "", checked.reference ? "Search seed description & checked scope" : "Search description & checked scope"));
  details.append(node("p", "", candidate.description?.summary || "No description was returned."));
  const uncertainties = candidate.description?.uncertainties || [];
  if (uncertainties.length) details.append(node("p", "", `Index uncertainty: ${uncertainties.join(" ")}`));
  details.append(node("p", "", `Checked ${checked.samples.length} frames from ${timeLabel(checked.inspection_start_seconds)} to ${timeLabel(checked.inspection_end_seconds)}. Source-check ID: ${checked.id}.`));
  if (checked.reference) details.append(node("p", "", `New frames cover ${timeLabel(checked.new_start_seconds)}–${timeLabel(checked.new_end_seconds)}. One input repeats a reference frame at ${timeLabel(checked.reference.source_seconds)}. Gaps remain unobserved.`));
  if (result._extent) details.append(node("p", "", result._extent.interval_note));
  card.append(details);
  return card;
}

function eventCard(proposal, checked) {
  const card = node("article", "answer-card");
  card.append(node("h3", "", "Event span estimate"));
  card.append(node("p", "small muted", proposal.onset.state === "observed" && proposal.offset.state === "observed" ? "Both event edges have model-estimated brackets in the sampled frames." : "The full event edges remain unresolved."));
  if (proposal.query_support !== "all") card.append(node("p", "small muted", "The model has not supported every part of this query."));
  for (const [label, edge] of [["Start", proposal.onset], ["End", proposal.offset]]) {
    const value = edge.state === "observed" ? `between ${timeLabel(edge.lower_seconds)} and ${timeLabel(edge.upper_seconds)}` : edge.state;
    card.append(node("p", "small", `${label}: ${value}.`));
  }
  if (proposal.start_seconds !== null && proposal.end_seconds !== null) {
    const button = node("button", "timestamp", `Open estimated span ${timeLabel(proposal.start_seconds)}–${timeLabel(proposal.end_seconds)}`);
    button.type = "button";
    button.addEventListener("click", () => playAt(checked.media_url, proposal.start_seconds, proposal.end_seconds));
    card.append(button);
  } else card.append(node("p", "small muted", "There is not enough evidence to estimate a nonzero event span."));
  card.append(node("p", "small muted", proposal.scope_note));
  const details = node("details", "answer-details");
  details.append(node("summary", "", "Supporting source checks"));
  details.append(node("p", "", proposal.supporting_check_ids.join(", ")));
  card.append(details);
  return card;
}

function countCard(result) {
  const card = node("article", "answer-card");
  const partial = !result.partitions.complete;
  card.append(node("span", "answer-label", "Observed count"));
  card.append(node("h3", "", `${result.count} ${result.count === 1 ? "occurrence" : "occurrences"}${partial ? " so far (partial scan)" : ""}`));
  card.append(node("p", "small muted", `${result.partitions.checked} of ${result.partitions.total} intervals checked${result.partitions.uncertain ? `, ${result.partitions.uncertain} uncertain` : ""}. ${result.honesty_note}`));
  const times = node("div", "answer-times");
  for (const event of result.events) {
    const button = node("button", "timestamp", `▶ ${timeLabel(event.start_seconds)}–${timeLabel(event.end_seconds)}`);
    button.type = "button";
    button.setAttribute("aria-label", `Open source video from ${timeLabel(event.start_seconds)} to ${timeLabel(event.end_seconds)}`);
    button.addEventListener("click", () => playAt(event.media_url, event.start_seconds, event.end_seconds));
    times.append(button);
  }
  if (result.events.length) card.append(times);
  return card;
}

function transcriptCard(item) {
  const card = node("article", "answer-card");
  const top = node("div", "answer-top");
  top.append(node("span", "answer-label", "Transcript match"),
             node("span", `status-pill ${item.source_status === "available" ? "ready" : ""}`, item.source_status === "available" ? "Source available" : item.source_status));
  card.append(top, node("p", "answer-observation", item.text));
  const times = node("div", "answer-times");
  const button = node("button", "timestamp", `▶ ${timeLabel(item.start_seconds)}–${timeLabel(item.end_seconds)}`);
  button.type = "button";
  button.setAttribute("aria-label", `Open source video from ${timeLabel(item.start_seconds)} to ${timeLabel(item.end_seconds)}`);
  button.addEventListener("click", () => playAt(item.media_url, item.start_seconds, item.end_seconds));
  times.append(button);
  card.append(times);
  const build = state.transcriptBuilds.find((entry) => entry.id === item.build_id);
  const origin = build?.spec?.source === "asr" ? "local ASR"
      : build?.spec?.source === "subtitle" ? `supplied subtitles (${build.spec.format})` : "";
  card.append(node("p", "small muted", origin
      ? `From ${item.source_path.split("/").pop()} · transcript from ${origin}. ${build.spec.source === "subtitle" ? "Subtitle text is supplied, not a model-verified visual check." : "ASR text is an automatic estimate, not a model-verified visual check."}`
      : `From ${item.source_path.split("/").pop()}. Transcript text is an automatic estimate or supplied subtitles, not a model-verified visual check.`));
  return card;
}

byId("query-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.queryBusy) return;
  const query = byId("query").value.trim();
  if (!query) { showError("query-error", "Enter a question about the video."); byId("query").focus(); return; }
  const recording = selectedRecording();
  const allVideos = byId("all-videos").checked;
  if (allVideos && !anyReadyIndex()) { showError("query-error", "No video has a completed index yet."); return; }
  if (!allVideos && (!recording || (activeBuild(recording.id)?.state !== "ready" && !hasReadyTranscript(recording.id)))) { showError("query-error", "Select a video with a completed index first."); return; }
  state.queryBusy = true;
  clearAnswers();
  renderLibrary();
  const image = state.queryImage;
  const searchPath = byId("search-path").value;
  try {
    const target = allVideos ? {} : {recording_ids: [recording.id]};
    if (!image && byId("count-mode").checked) {
      const scope = scopeDates(query);
      byId("query-progress").textContent = "Counting occurrences: checking each interval of the declared scope. Hosted model checks can take several minutes…";
      const result = await post("/count-events", {query, max_checks: 60, ...target, ...((scope.start || scope.end) ? {start_date: scope.start, end_date: scope.end} : {})});
      byId("answer-list").append(countCard(result));
      byId("query-progress").textContent = `Observed ${result.count} ${result.count === 1 ? "occurrence" : "occurrences"}; ${result.partitions.checked} of ${result.partitions.total} intervals checked.${result.partitions.complete ? "" : " The scan is partial: unchecked intervals are not proven absent."}${scope.mode !== "all" ? ` Time scope: ${scope.start || "…"}${scope.end && scope.end !== scope.start ? ` to ${scope.end}` : ""}${scope.fromText ? " (detected in your question)" : ""}.` : ""}`;
      return;
    }
    if (!image && searchPath === "speech") {
      const scope = scopeDates(query);
      const result = await post("/search", {query, path: "speech", limit: 12, ...target, ...((scope.start || scope.end) ? {start_date: scope.start, end_date: scope.end} : {})});
      if (!result.results.length) {
        byId("answer-list").append(node("p", "empty-small", "No transcript matches. Build a speech index with the 'Index speech (local ASR)' button in your library; recordings without one were not searched."));
      }
      for (const item of result.results) byId("answer-list").append(transcriptCard(item));
      byId("query-progress").textContent = `${result.results.length} transcript ${result.results.length === 1 ? "match" : "matches"}. Transcript text is an estimate or supplied subtitles; it is not a model-verified visual check.${scope.mode !== "all" ? ` Time scope: ${scope.start || "…"}${scope.end && scope.end !== scope.start ? ` to ${scope.end}` : ""}${scope.fromText ? " (detected in your question)" : ""}.` : ""}`;
      return;
    }
    byId("query-progress").textContent = image
      ? "Searching by image similarity and text, then checking up to 3 source intervals. Hosted model checks can take several minutes…"
      : "Searching up to 12 candidates and checking up to 3 source intervals. Hosted model checks can take several minutes…";
    const method = byId("search-policy").value;
    const imageMethod = image && (method === "reranked" || method === "extent");
    const scope = scopeDates(query);
    const payload = {query, path: image ? "hybrid" : "description", ...target, limit: 12, max_checks: 3, policy: imageMethod ? "adaptive" : method === "extent" ? "extent" : method === "ranked" ? "ranked" : "adaptive", rerank: !image && (method === "reranked" || method === "extent"), ...(image ? {image_base64: image} : {}), ...((scope.start || scope.end) ? {start_date: scope.start, end_date: scope.end} : {})};
    const result = await post("/evidence-search", payload);
    if (!result.checks.length) {
      byId("answer-list").append(node("p", "empty-small", "No indexed candidates were returned. This does not prove the event is absent from the video."));
    }
    for (const [index, step] of result.checks.entries()) {
      const card = answerCard(step.candidate, step.verification, index + 1);
      if (step.reason === "dense_refinement") card.append(node("p", "small muted", "Follow-up: a closer check of an uncertain moment."));
      byId("answer-list").append(card);
    }
    for (const proposal of result.proposals || []) {
      const source = result.checks.find((step) => step.verification.recording_id === proposal.recording_id);
      if (!source) throw new Error("An event estimate has no matching source check.");
      byId("answer-list").append(eventCard(proposal, source.verification));
    }
    const stops = {match_found: "A match was found in the checked frames.", event_bounded: "The model estimated both event edges.", query_incomplete: "Only part of the query has visual support.", event_unresolved: "Event edges remain unresolved.", scope_exhausted: "No more footage is available in this search scope.", budget_exhausted: "The source-check limit was reached.", candidates_exhausted: "No more candidates remain in this search."};
    if (!Object.hasOwn(stops, result.stop_reason)) throw new Error("The server returned an unknown stop reason.");
    byId("query-progress").textContent = `${stops[result.stop_reason]} Checked ${result.budget.frames} frames in ${result.budget.calls} source ${result.budget.calls === 1 ? "check" : "checks"}. This is not a full-video review.${scope.mode !== "all" ? ` Time scope: ${scope.start || "…"}${scope.end && scope.end !== scope.start ? ` to ${scope.end}` : ""}${scope.fromText ? " (detected in your question)" : ""}. Recordings without a capture date were skipped.` : ""}`;
    const download = node("button", "secondary", "Save search trace");
    download.type = "button";
    download.addEventListener("click", () => {
      const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], {type: "application/json"}));
      const link = node("a");
      link.href = url;
      link.download = `video-search-${result.request_id}.json`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    byId("answer-list").append(download);
  } catch (error) { showError("query-error", error.message); byId("query-progress").textContent = "The check stopped. Any source checks completed before the error remain saved on the server."; }
  finally { state.queryBusy = false; renderLibrary(); }
});

async function start() {
  try {
    state.config = await api("/app-config");
    state.selected = localStorage.getItem("video-search-selected");
    byId("model-name").textContent = `ASU · ${state.config.model}`;
    byId("file-note").textContent = `Video files · up to ${(state.config.upload_max_bytes / 1073741824).toFixed(0)} GB per upload`;
    if (!state.config.uploads_enabled) showError("upload-error", "Uploads are not enabled. Check the server upload storage and model settings.");
    await refresh();
    const uploadedJob = localStorage.getItem("video-search-upload-job");
    if (uploadedJob) {
      const job = state.jobs.find((item) => item.id === uploadedJob);
      if (job?.result?.recording_id) selectRecording(job.result.recording_id);
    }
    setInterval(async () => {
      try {
        await refresh();
        const jobId = localStorage.getItem("video-search-upload-job");
        const job = state.jobs.find((item) => item.id === jobId);
        if (job?.result?.recording_id && !state.queryBusy) {
          selectRecording(job.result.recording_id);
          localStorage.removeItem("video-search-upload-job");
        }
      } catch (error) { showError("page-error", `Could not refresh the library. ${error.message}`); }
    }, 3000);
  } catch (error) { showError("page-error", `Could not load the workspace. ${error.message}`); }
}

start();
