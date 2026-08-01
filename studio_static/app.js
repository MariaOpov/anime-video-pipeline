const elements = {
  projectChip: document.querySelector("#project-chip"),
  ollamaChip: document.querySelector("#ollama-chip"),
  refreshButton: document.querySelector("#refresh-button"),
  preset: document.querySelector("#preset"),
  fresh: document.querySelector("#fresh-toggle"),
  phase1Button: document.querySelector("#phase1-button"),
  phase2Button: document.querySelector("#phase2-button"),
  runAllButton: document.querySelector("#run-all-button"),
  saveScriptButton: document.querySelector("#save-script-button"),
  scriptEditor: document.querySelector("#script-editor"),
  scriptState: document.querySelector("#script-state"),
  scriptCount: document.querySelector("#script-count"),
  motionEditor: document.querySelector("#motion-editor"),
  motionSource: document.querySelector("#motion-source"),
  rulesButton: document.querySelector("#rules-button"),
  aiButton: document.querySelector("#ai-button"),
  saveMotionButton: document.querySelector("#save-motion-button"),
  motionWarnings: document.querySelector("#motion-warnings"),
  jobChip: document.querySelector("#job-chip"),
  console: document.querySelector("#console-output"),
  finalVideo: document.querySelector("#final-video"),
  videoEmpty: document.querySelector("#video-empty"),
  reloadVideoButton: document.querySelector("#reload-video-button"),
  qualityChip: document.querySelector("#quality-chip"),
  qualityList: document.querySelector("#quality-list"),
  metricGates: document.querySelector("#metric-gates"),
  metricGatesDetail: document.querySelector("#metric-gates-detail"),
  metricShots: document.querySelector("#metric-shots"),
  metricCues: document.querySelector("#metric-cues"),
  metricGestures: document.querySelector("#metric-gestures"),
  metricGesturesDetail: document.querySelector("#metric-gestures-detail"),
  metricCost: document.querySelector("#metric-cost"),
  directionSummary: document.querySelector("#direction-summary"),
  directionTimeline: document.querySelector("#direction-timeline"),
  toast: document.querySelector("#toast"),
};

let jobOffset = 0;
let jobTimer = null;
let toastTimer = null;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { message = (await response.json()).detail || message; } catch (_) { /* ignore */ }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

function toast(message, isError = false) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", isError);
  elements.toast.classList.remove("hidden");
  toastTimer = setTimeout(() => elements.toast.classList.add("hidden"), 4200);
}

function setBusy(isBusy) {
  [elements.phase1Button, elements.phase2Button, elements.runAllButton].forEach(button => {
    button.disabled = isBusy;
  });
}

function setChip(element, text, state = "muted") {
  element.textContent = text;
  element.className = "chip";
  if (state === "muted") element.classList.add("chip-muted");
  if (state === "danger") element.classList.add("chip-danger");
}

function renderWarnings(warnings = []) {
  elements.motionWarnings.replaceChildren();
  elements.motionWarnings.classList.toggle("hidden", warnings.length === 0);
  warnings.forEach(warning => {
    const line = document.createElement("div");
    line.textContent = `⚠ ${warning}`;
    elements.motionWarnings.append(line);
  });
}

function renderMotion(plan) {
  if (!plan) {
    elements.motionEditor.value = "";
    setChip(elements.motionSource, "Chưa tạo", "muted");
    return;
  }
  elements.motionEditor.value = JSON.stringify(plan, null, 2);
  setChip(elements.motionSource, plan.source.toUpperCase(), plan.source === "ollama" ? "ok" : "muted");
}

function renderReport(report) {
  const summary = report?.summary;
  if (!summary) {
    elements.metricGates.textContent = "—";
    elements.metricGatesDetail.textContent = "Chưa có báo cáo";
    elements.metricShots.textContent = "—";
    elements.metricCues.textContent = "—";
    elements.metricGestures.textContent = "—";
    elements.metricGesturesDetail.textContent = "Procedural performance";
    setChip(elements.qualityChip, "No report", "muted");
    elements.qualityList.replaceChildren();
    const empty = document.createElement("p");
    empty.className = "empty-copy";
    empty.textContent = "Chạy toàn bộ pipeline để tạo production report.";
    elements.qualityList.append(empty);
    return;
  }
  elements.metricGates.textContent = `${summary.passed_gate_count}/${summary.quality_gate_count}`;
  elements.metricGatesDetail.textContent = summary.failed_gate_count ? `${summary.failed_gate_count} failed` : "All systems passed";
  elements.metricShots.textContent = summary.shot_count;
  elements.metricCues.textContent = summary.mouth_cue_count;
  elements.metricGestures.textContent = summary.gesture_count ?? 0;
  elements.metricGesturesDetail.textContent = `${summary.pose_keyframe_count ?? 0} pose · ${summary.blink_event_count ?? 0} blink`;
  elements.metricCost.textContent = `$${summary.estimated_cost}`;
  setChip(elements.qualityChip, report.status.toUpperCase(), report.status === "complete" ? "ok" : "danger");
  elements.qualityList.replaceChildren();
  report.quality_gates.forEach(gate => {
    const item = document.createElement("div");
    item.className = `quality-item ${gate.status === "failed" ? "failed" : ""}`;
    const dot = document.createElement("span");
    dot.className = "quality-dot";
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = gate.name;
    const detail = document.createElement("small");
    detail.textContent = `Phase ${gate.phase} · ${gate.status}`;
    copy.append(title, detail);
    item.append(dot, copy);
    elements.qualityList.append(item);
  });
}

function renderDirection(manifest, report) {
  const performance = manifest?.performance;
  const summary = manifest?.summary;
  elements.directionTimeline.replaceChildren();
  if (!performance?.clips?.length || !summary) {
    elements.directionSummary.textContent = "Chưa có manifest";
    const empty = document.createElement("p");
    empty.className = "empty-copy";
    empty.textContent = "Chạy production để tạo dialogue beats, gaze, blink và listener reactions.";
    elements.directionTimeline.append(empty);
    return;
  }
  const conflicts = summary.performance_conflict_count ?? 0;
  elements.directionSummary.textContent =
    `${summary.dialogue_beat_count} beat · ${summary.gaze_target_count} gaze · ` +
    `${summary.blink_event_count} blink · ${summary.listener_reaction_count} reaction · ` +
    `${conflicts} conflict`;
  elements.directionSummary.classList.toggle("danger", conflicts > 0);

  const frameStart = Number(manifest.frame_start);
  const span = Math.max(1, Number(manifest.frame_end) - frameStart);
  performance.clips.forEach(clip => {
    const row = document.createElement("div");
    row.className = "timeline-row";
    const label = document.createElement("div");
    label.className = "timeline-label";
    const name = document.createElement("strong");
    name.textContent = clip.character;
    const role = document.createElement("small");
    role.textContent = `${clip.role} · ${clip.shot_id.replace("scene_001_", "")}`;
    label.append(name, role);

    const track = document.createElement("div");
    track.className = "timeline-track";
    const segment = document.createElement("div");
    segment.className = `timeline-segment ${clip.role}`;
    segment.style.left = `${100 * (clip.start_frame - frameStart) / span}%`;
    segment.style.width = `${Math.max(1.2, 100 * (clip.end_frame - clip.start_frame) / span)}%`;
    segment.title = `${clip.character}: ${clip.gestures.join(", ") || "idle"}`;
    track.append(segment);
    (clip.beats || []).forEach(beat => {
      const dot = document.createElement("span");
      dot.className = `timeline-beat ${beat.type}`;
      dot.style.left = `${100 * (beat.peak_frame - frameStart) / span}%`;
      dot.title = beat.gesture ? `${beat.type}: ${beat.gesture}` : beat.type;
      track.append(dot);
    });
    row.append(label, track);
    elements.directionTimeline.append(row);
  });

  const applied = report?.summary;
  if (applied) {
    elements.directionSummary.title =
      `${applied.gaze_keyframe_count ?? 0} gaze keys · ` +
      `${applied.blink_keyframe_count ?? 0} blink keys`;
  }
}

async function loadDocument(name) {
  try { return await api(`/api/documents/${name}`); }
  catch (error) {
    if (error.status === 404) return null;
    throw error;
  }
}

async function loadStatus() {
  try {
    const [status, script, motion, report, manifest] = await Promise.all([
      api("/api/status"), api("/api/script"),
      loadDocument("motion_intent"), loadDocument("production_report"),
      loadDocument("phase3_manifest"),
    ]);
    setChip(elements.projectChip, `${status.project_name} · v${status.pipeline_version}`, "ok");
    setChip(elements.ollamaChip,
      status.ollama.available ? `Ollama: ${status.ollama.model}` : "Ollama: offline",
      status.ollama.available ? "ok" : "muted");
    elements.scriptEditor.value = script.text;
    elements.scriptCount.textContent = `${script.text.length.toLocaleString("vi-VN")} ký tự`;
    elements.scriptState.textContent = "Đã đồng bộ";
    renderMotion(motion);
    renderReport(report);
    renderDirection(manifest, report);
    refreshVideo(status.artifacts.final_video);
    if (status.job?.status === "running") {
      jobOffset = 0;
      pollJob();
    }
  } catch (error) {
    setChip(elements.projectChip, "Lỗi tải project", "danger");
    setChip(elements.ollamaChip, "Ollama: chưa xác định", "muted");
    toast(error.message, true);
  }
}

function refreshVideo(available = true) {
  elements.finalVideo.classList.toggle("hidden", !available);
  elements.videoEmpty.classList.toggle("hidden", available);
  if (available) {
    elements.finalVideo.src = `/api/artifacts/final_video?t=${Date.now()}`;
    elements.finalVideo.load();
  }
}

async function saveScript() {
  try {
    await api("/api/script", { method: "PUT", body: JSON.stringify({ text: elements.scriptEditor.value }) });
    elements.scriptState.textContent = "Đã lưu · cần chạy Phase 1";
    toast("Đã lưu script.txt. Chạy Phase 1 trước khi tạo motion intent.");
  } catch (error) { toast(error.message, true); }
}

async function generateMotion(useAI) {
  const button = useAI ? elements.aiButton : elements.rulesButton;
  button.disabled = true;
  try {
    const result = await api("/api/motion-intent/generate", {
      method: "POST", body: JSON.stringify({ use_ai: useAI }),
    });
    renderMotion(result.plan);
    renderWarnings(result.warnings);
    toast(`Motion intent đã tạo bằng ${result.plan.source}.`);
  } catch (error) { toast(error.message, true); }
  finally { button.disabled = false; }
}

async function saveMotion() {
  try {
    const plan = JSON.parse(elements.motionEditor.value);
    const result = await api("/api/motion-intent", {
      method: "PUT", body: JSON.stringify({ plan }),
    });
    renderMotion(result.plan);
    renderWarnings(result.warnings);
    toast("Motion JSON hợp lệ và đã lưu.");
  } catch (error) { toast(error.message, true); }
}

async function startJob(mode) {
  setBusy(true);
  elements.console.textContent = "";
  jobOffset = 0;
  try {
    await api("/api/jobs", {
      method: "POST",
      body: JSON.stringify({ mode, preset: elements.preset.value, fresh: elements.fresh.checked }),
    });
    setChip(elements.jobChip, "RUNNING", "ok");
    pollJob();
  } catch (error) {
    setBusy(false);
    toast(error.message, true);
  }
}

async function pollJob() {
  clearTimeout(jobTimer);
  try {
    const job = await api(`/api/jobs/current?offset=${jobOffset}`);
    if (!job) return;
    job.lines.forEach(line => {
      elements.console.textContent += `${line}\n`;
    });
    jobOffset = job.next_offset;
    elements.console.scrollTop = elements.console.scrollHeight;
    if (job.status === "running") {
      setBusy(true);
      setChip(elements.jobChip, `RUNNING · ${job.mode}`, "ok");
      jobTimer = setTimeout(pollJob, 900);
    } else {
      setBusy(false);
      setChip(elements.jobChip, job.status.toUpperCase(), job.status === "complete" ? "ok" : "danger");
      toast(job.status === "complete" ? "Pipeline hoàn tất." : "Pipeline thất bại. Kiểm tra console.", job.status !== "complete");
      await loadStatus();
    }
  } catch (error) {
    setBusy(false);
    toast(error.message, true);
  }
}

elements.scriptEditor.addEventListener("input", () => {
  elements.scriptCount.textContent = `${elements.scriptEditor.value.length.toLocaleString("vi-VN")} ký tự`;
  elements.scriptState.textContent = "Chưa lưu";
});
elements.saveScriptButton.addEventListener("click", saveScript);
elements.rulesButton.addEventListener("click", () => generateMotion(false));
elements.aiButton.addEventListener("click", () => generateMotion(true));
elements.saveMotionButton.addEventListener("click", saveMotion);
elements.phase1Button.addEventListener("click", () => startJob("phase1"));
elements.phase2Button.addEventListener("click", () => startJob("phase2"));
elements.runAllButton.addEventListener("click", () => startJob("all"));
elements.refreshButton.addEventListener("click", loadStatus);
elements.reloadVideoButton.addEventListener("click", loadStatus);

loadStatus();
