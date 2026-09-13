// Access Bridge frontend. Vanilla JS, no build step -- calls the
// FastAPI backend under /api directly.

const API = "";
const $ = (id) => document.getElementById(id);

/* =========================================================
   Accessibility controls: text size + theme, both persisted
   ========================================================= */

const root = document.documentElement;
let fontScale = parseFloat(localStorage.getItem("ab-font-scale") || "1");
applyFontScale();

function applyFontScale() {
  fontScale = Math.min(1.4, Math.max(0.85, fontScale));
  root.style.setProperty("--font-scale", fontScale.toFixed(2));
  localStorage.setItem("ab-font-scale", fontScale.toFixed(2));
}
$("font-inc").addEventListener("click", () => { fontScale += 0.1; applyFontScale(); });
$("font-dec").addEventListener("click", () => { fontScale -= 0.1; applyFontScale(); });

const savedTheme = localStorage.getItem("ab-theme");
if (savedTheme) root.setAttribute("data-theme", savedTheme);
$("theme-toggle").addEventListener("click", () => {
  const next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
  root.setAttribute("data-theme", next);
  localStorage.setItem("ab-theme", next);
});

/* =========================================================
   Backend health check
   ========================================================= */

let backendUp = false;

function checkHealth() {
  fetch(`${API}/api/health`)
    .then((r) => r.json())
    .then(() => {
      backendUp = true;
      $("status-dot").classList.remove("down");
      $("status-dot").classList.add("up");
      $("status-text").textContent = "Backend connected";
      $("stat-backend").textContent = "Online";
    })
    .catch(() => {
      backendUp = false;
      $("status-dot").classList.remove("up");
      $("status-dot").classList.add("down");
      $("status-text").textContent = "Backend not reachable";
      $("stat-backend").textContent = "Offline";
    });
}
checkHealth();

/* =========================================================
   Toasts
   ========================================================= */

function toast(message) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = message;
  $("toast-stack").appendChild(el);
  setTimeout(() => el.remove(), 5000);
}

/* =========================================================
   Routing: sidebar nav + quick-launch cards all switch views
   ========================================================= */

const VIEW_META = {
  dashboard: { title: "Dashboard", subtitle: "An overview of everything Access Bridge has recognized." },
  blind: { title: "Blind & low-vision", subtitle: "Hear what's in front of you, and read text out loud." },
  hearing: { title: "Deaf & hard-of-hearing", subtitle: "Turn speech into captions, and signs into text." },
  comm: { title: "Communication bridge", subtitle: "A shared conversation between a hearing and a deaf participant." },
};

function navigate(view) {
  if (!VIEW_META[view]) view = "dashboard";

  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  $(`view-${view}`).classList.add("active");

  document.querySelectorAll(".nav-link").forEach((n) => n.classList.toggle("active", n.dataset.view === view));

  $("view-title").textContent = VIEW_META[view].title;
  $("view-subtitle").textContent = VIEW_META[view].subtitle;

  if (view === "dashboard") refreshDashboard();

  history.replaceState(null, "", `#${view}`);
  window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
}

document.querySelectorAll("[data-view]").forEach((el) => {
  el.addEventListener("click", () => navigate(el.dataset.view));
});

navigate((location.hash || "#dashboard").slice(1));

/* =========================================================
   Dashboard: live stats + recent activity, driven by /api/history
   ========================================================= */

const MODALITY_LABEL = {
  object_detection: "Object", ocr: "Text read", speech: "Speech", sign_language: "Sign",
};

function timeAgo(iso) {
  if (!iso) return "";
  const diff = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function bumpValue(el) {
  el.classList.remove("bump");
  void el.offsetWidth; // restart animation
  el.classList.add("bump");
}

async function refreshDashboard() {
  try {
    const res = await fetch(`${API}/api/history?limit=100`);
    const json = await res.json();
    const rows = json.code === 200 ? json.data : [];

    const totalEl = $("stat-total");
    if (totalEl.textContent !== String(rows.length)) bumpValue(totalEl);
    totalEl.textContent = rows.length;

    const withConf = rows.filter((r) => r.confidence !== null && r.confidence !== undefined);
    const avgConf = withConf.length ? withConf.reduce((a, r) => a + r.confidence, 0) / withConf.length : null;
    $("stat-confidence").textContent = avgConf === null ? "—" : `${Math.round(avgConf * 100)}%`;

    const counts = {};
    rows.forEach((r) => { counts[r.modality] = (counts[r.modality] || 0) + 1; });
    const topModality = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
    $("stat-top-mode").textContent = topModality ? (MODALITY_LABEL[topModality[0]] || topModality[0]) : "—";

    const list = $("activity-list");
    if (!rows.length) {
      list.innerHTML = `<li class="activity-empty">Nothing recognized yet — try a mode above.</li>`;
      return;
    }
    list.innerHTML = rows
      .slice(0, 8)
      .map((r) => `
        <li>
          <span class="activity-icon ${r.modality}">${(MODALITY_LABEL[r.modality] || "?")[0]}</span>
          <span class="activity-modality">${MODALITY_LABEL[r.modality] || r.modality}</span>
          <span class="activity-text">${(r.result_text || "").replace(/</g, "&lt;")}</span>
          <span class="activity-conf">${r.confidence !== null && r.confidence !== undefined ? Math.round(r.confidence * 100) + "%" : ""}</span>
          <span class="activity-time">${timeAgo(r.created_at)}</span>
        </li>`)
      .join("");
  } catch (err) {
    // backend not reachable yet -- leave dashboard in its empty state
  }
}
refreshDashboard();

/* =========================================================
   Per-tool "pending file" state + dropzone wiring
   ========================================================= */

const pending = {};

function setPending(key, blob, name, labelId) {
  pending[key] = { blob, name };
  const label = $(labelId);
  if (label) label.innerHTML = `<span class="filename">${name}</span>`;
}

function setupDropzone(dropId, inputId, filenameId, key) {
  const drop = $(dropId);
  const input = $(inputId);
  if (!drop || !input) return;

  input.addEventListener("change", () => {
    if (input.files[0]) setPending(key, input.files[0], input.files[0].name, filenameId);
  });

  ["dragover", "dragenter"].forEach((evt) =>
    drop.addEventListener(evt, (e) => { e.preventDefault(); drop.classList.add("drag-over"); })
  );
  ["dragleave", "drop"].forEach((evt) =>
    drop.addEventListener(evt, (e) => { e.preventDefault(); drop.classList.remove("drag-over"); })
  );
  drop.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) setPending(key, file, file.name, filenameId);
  });
}

setupDropzone("object-drop", "object-file", "object-filename", "object");
setupDropzone("ocr-drop", "ocr-file", "ocr-filename", "ocr");
setupDropzone("sign-drop", "sign-file", "sign-filename", "sign");
setupDropzone("speech-drop", "speech-file", "speech-filename", "speech");
setupDropzone("h2d-drop", "h2d-file", "h2d-filename", "h2d");
setupDropzone("d2h-drop", "d2h-file", "d2h-filename", "d2h");

/* =========================================================
   Camera capture (getUserMedia)
   ========================================================= */

const activeStreams = {};

async function openCamera(boxId, videoId) {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
    activeStreams[boxId] = stream;
    $(videoId).srcObject = stream;
    $(boxId).classList.add("active");
  } catch (err) {
    toast("Couldn't access the camera -- check your browser permissions.");
  }
}

function closeCamera(boxId) {
  const stream = activeStreams[boxId];
  if (stream) stream.getTracks().forEach((t) => t.stop());
  delete activeStreams[boxId];
  $(boxId).classList.remove("active");
}

function captureFrame(videoId) {
  const video = $(videoId);
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
}

function wireCamera({ camBtnId, boxId, videoId, snapId, closeId, key, filenameId, onCaptured }) {
  const camBtn = $(camBtnId);
  if (!camBtn) return;
  camBtn.addEventListener("click", () => openCamera(boxId, videoId));
  $(closeId).addEventListener("click", () => closeCamera(boxId));
  $(snapId).addEventListener("click", async () => {
    const blob = await captureFrame(videoId);
    setPending(key, blob, "camera-capture.jpg", filenameId);
    closeCamera(boxId);
    if (onCaptured) onCaptured();
  });
}

wireCamera({ camBtnId: "object-cam-btn", boxId: "object-camera", videoId: "object-video", snapId: "object-snap", closeId: "object-cam-close", key: "object", filenameId: "object-filename" });
wireCamera({ camBtnId: "ocr-cam-btn", boxId: "ocr-camera", videoId: "ocr-video", snapId: "ocr-snap", closeId: "ocr-cam-close", key: "ocr", filenameId: "ocr-filename" });
wireCamera({ camBtnId: "sign-cam-btn", boxId: "sign-camera", videoId: "sign-video", snapId: "sign-snap", closeId: "sign-cam-close", key: "sign", filenameId: "sign-filename" });
wireCamera({
  camBtnId: "d2h-cam-btn", boxId: "d2h-camera", videoId: "d2h-video", snapId: "d2h-snap", closeId: "d2h-cam-close",
  key: "d2h", filenameId: "d2h-filename", onCaptured: () => $("d2h-btn").click(),
});

/* =========================================================
   Mic recording (MediaRecorder)
   ========================================================= */

function wireRecorder(btnId, key, filenameId) {
  const btn = $(btnId);
  if (!btn) return;
  let recorder = null;
  let chunks = [];

  btn.addEventListener("click", async () => {
    if (recorder && recorder.state === "recording") {
      recorder.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recorder = new MediaRecorder(stream);
      chunks = [];
      recorder.ondataavailable = (e) => chunks.push(e.data);
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks, { type: "audio/webm" });
        setPending(key, blob, "recording.webm", filenameId);
        btn.textContent = btn.dataset.idleLabel;
        btn.classList.remove("recording");
      };
      btn.dataset.idleLabel = btn.textContent;
      btn.textContent = "Stop recording";
      btn.classList.add("recording");
      recorder.start();
    } catch (err) {
      toast("Couldn't access the microphone -- check your browser permissions.");
    }
  });
}

wireRecorder("speech-record-btn", "speech", "speech-filename");
wireRecorder("h2d-record-btn", "h2d", "h2d-filename");

/* =========================================================
   Result rendering helpers -- confidence is color, everywhere
   ========================================================= */

function confidenceTier(conf) {
  if (conf === null || conf === undefined) return null;
  if (conf >= 0.66) return "high";
  if (conf >= 0.33) return "mid";
  return "low";
}

function confidenceBadge(conf, label) {
  const tier = confidenceTier(conf);
  if (!tier) return "";
  return `<div class="confidence-row">
    <span class="confidence-dot ${tier}"></span>
    <span class="confidence-label">${label || "confidence"} ${Math.round(conf * 100)}%</span>
  </div>`;
}

function rankList(topK) {
  if (!topK || topK.length < 2) return "";
  const items = topK
    .map((item) => `<li>
        <span class="rank-label">${item.label}</span>
        <span class="rank-bar-track"><span class="rank-bar-fill" style="width:${Math.round(item.confidence * 100)}%"></span></span>
        <span class="rank-pct">${Math.round(item.confidence * 100)}%</span>
      </li>`)
    .join("");
  return `<ul class="rank-list">${items}</ul>`;
}

function showResult(elId, html, isError = false) {
  const el = $(elId);
  el.classList.add("visible");
  el.classList.toggle("error", isError);
  el.innerHTML = html;
}

function mediaUrl(path) {
  if (!path) return null;
  return `/media/${path.split("/").pop()}`;
}

async function postPending(url, key, fieldName, extra = {}) {
  const item = pending[key];
  if (!item) { toast("Add a photo or recording first."); return null; }
  const fd = new FormData();
  fd.append(fieldName, item.blob, item.name);
  Object.entries(extra).forEach(([k, v]) => fd.append(k, v));
  const res = await fetch(url, { method: "POST", body: fd });
  return res.json();
}

/* =========================================================
   Blind mode: object detection
   ========================================================= */

$("object-btn").addEventListener("click", async () => {
  showResult("object-result", "Looking&hellip;");
  const speak = $("object-speak").checked;
  const json = await postPending(`${API}/api/detect-object?speak=${speak}`, "object", "file");
  if (!json) return showResult("object-result", "", true);
  if (json.code !== 200) return showResult("object-result", `<span class="error-text">${json.message}</span>`, true);

  const conf = json.data.detections.length ? Math.max(...json.data.detections.map((d) => d.confidence)) : null;
  const audio = mediaUrl(json.data.audio_path);
  showResult(
    "object-result",
    confidenceBadge(conf, "detection confidence") +
      `<p class="result-text big">${json.data.description || "Nothing recognizable found."}</p>` +
      (audio ? `<audio controls src="${audio}"></audio>` : "")
  );
  refreshDashboard();
});

/* =========================================================
   Blind mode: OCR
   ========================================================= */

$("ocr-btn").addEventListener("click", async () => {
  showResult("ocr-result", "Reading&hellip;");
  const speak = $("ocr-speak").checked;
  const json = await postPending(`${API}/api/read-text?speak=${speak}`, "ocr", "file");
  if (!json) return showResult("ocr-result", "", true);
  if (json.code !== 200) return showResult("ocr-result", `<span class="error-text">${json.message}</span>`, true);

  const avgConf = json.data.words.length
    ? json.data.words.reduce((a, w) => a + w.confidence, 0) / json.data.words.length
    : null;
  const audio = mediaUrl(json.data.audio_path);
  showResult(
    "ocr-result",
    confidenceBadge(avgConf, "reading confidence") +
      `<p class="result-text big">${json.data.text || "No text found."}</p>` +
      (audio ? `<audio controls src="${audio}"></audio>` : "")
  );
  refreshDashboard();
});

/* =========================================================
   Hearing mode: speech to text
   ========================================================= */

$("speech-btn").addEventListener("click", async () => {
  showResult("speech-result", "Transcribing&hellip;");
  const json = await postPending(`${API}/api/speech-to-text`, "speech", "file");
  if (!json) return showResult("speech-result", "", true);
  if (json.code !== 200) return showResult("speech-result", `<span class="error-text">${json.message}</span>`, true);
  showResult("speech-result", `<p class="result-text big">${json.data.text || "(no speech detected)"}</p>`);
  refreshDashboard();
});

/* =========================================================
   Hearing mode: sign to text
   ========================================================= */

$("sign-btn").addEventListener("click", async () => {
  showResult("sign-result", "Recognizing&hellip;");
  const speak = $("sign-speak").checked;
  const json = await postPending(`${API}/api/recognize-sign?speak=${speak}`, "sign", "file");
  if (!json) return showResult("sign-result", "", true);
  if (json.code !== 200) return showResult("sign-result", `<span class="error-text">${json.message}</span>`, true);

  const audio = mediaUrl(json.data.audio_path);
  showResult(
    "sign-result",
    confidenceBadge(json.data.confidence, "recognition confidence") +
      `<p class="result-text big">${json.data.prediction}</p>` +
      rankList(json.data.top_k) +
      (audio ? `<audio controls src="${audio}"></audio>` : "")
  );
  refreshDashboard();
});

/* =========================================================
   Communication mode: shared transcript
   ========================================================= */

function addBubble(side, text, audioPath) {
  const wrap = $("transcript");
  const empty = wrap.querySelector(".transcript-empty");
  if (empty) empty.remove();

  const bubble = document.createElement("div");
  bubble.className = `bubble from-${side}`;
  const audio = mediaUrl(audioPath);
  bubble.innerHTML = `<span class="bubble-meta">${side === "hearing" ? "Hearing participant" : "Deaf participant"}</span>
    <span class="bubble-text">${text}</span>
    ${audio ? `<audio controls src="${audio}"></audio>` : ""}`;
  wrap.appendChild(bubble);
  wrap.scrollTop = wrap.scrollHeight;
}

$("h2d-btn").addEventListener("click", async () => {
  const json = await postPending(`${API}/api/communicate/hearing-to-deaf`, "h2d", "file");
  if (!json) return;
  if (json.code !== 200) return toast(json.message);
  addBubble("hearing", json.data.text || "(no speech detected)");
  refreshDashboard();
});

$("d2h-btn").addEventListener("click", async () => {
  const json = await postPending(`${API}/api/communicate/deaf-to-hearing`, "d2h", "file");
  if (!json) return;
  if (json.code !== 200) return toast(json.message);
  addBubble("deaf", `${json.data.text} (${Math.round(json.data.confidence * 100)}%)`, json.data.audio_path);
  refreshDashboard();
});

$("type-btn").addEventListener("click", async () => {
  const text = $("type-input").value.trim();
  if (!text) return;
  const fd = new FormData();
  fd.append("text", text);
  const res = await fetch(`${API}/api/communicate/type-to-hearing`, { method: "POST", body: fd });
  const json = await res.json();
  if (json.code !== 200) return toast(json.message);
  addBubble("deaf", text, json.data.audio_path);
  $("type-input").value = "";
});
