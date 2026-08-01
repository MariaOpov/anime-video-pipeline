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
  metricCost: document.querySelector("#metric-cost"),
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

async function loadDocument(name) {
  try { return await api(`/api/documents/${name}`); }
  catch (error) {
    if (error.status === 404) return null;
    throw error;
  }
}

async function loadStatus() {
  try {
    const [status, script, motion, report] = await Promise.all([
      api("/api/status"), api("/api/script"),
      loadDocument("motion_intent"), loadDocument("production_report"),
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
