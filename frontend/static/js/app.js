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
  live: { title: "Live Translate", subtitle: "Real-time camera sign recognition and live speech captions, side by side." },
  blind: { title: "Blind & low-vision", subtitle: "Hear what's in front of you, and read text out loud." },
  hearing: { title: "Deaf & hard-of-hearing", subtitle: "Turn speech into captions, and signs into text." },
  comm: { title: "Communication bridge", subtitle: "A shared conversation between a hearing and a deaf participant." },
};

let currentView = "dashboard";

function navigate(view) {
  if (!VIEW_META[view]) view = "dashboard";

  // Leaving the Live Translate view always stops camera/mic -- nothing
  // should keep recording in the background once it's off-screen.
  if (currentView !== view && ["blind", "hearing", "comm"].includes(currentView)) {
    stopViewMedia(currentView);
  }
  if (currentView === "live" && view !== "live") stopLiveTranslate();
  if (currentView === "hearing" && view !== "hearing") stopHearingCaptions();
  currentView = view;

  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  $(`view-${view}`).classList.add("active");

  document.querySelectorAll(".nav-link").forEach((n) => n.classList.toggle("active", n.dataset.view === view));

  $("view-title").textContent = VIEW_META[view].title;
  $("view-subtitle").textContent = VIEW_META[view].subtitle;

  if (view === "dashboard") refreshDashboard();

  history.replaceState(null, "", `#${view}`);
  window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
}

// Also stop everything if the person closes/reloads the tab mid-session.
window.addEventListener("beforeunload", () => {
  stopLiveTranslate();
  stopHearingCaptions();
  stopAllRecorders();
});

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
const PENDING_UI = {
  speech: { action: "speech-btn", preview: "speech-preview", label: "speech-filename", input: "speech-file", clear: "speech-clear-file", emptyLabel: "Or drop / choose an audio file" },
  sign: { action: "sign-btn", preview: "sign-preview", label: "sign-filename", input: "sign-file", clear: "sign-clear-file", emptyLabel: "Drop a photo here, or click to choose one" },
  h2d: { action: "h2d-btn", preview: "h2d-preview", label: "h2d-filename", input: "h2d-file", clear: "h2d-clear-file", emptyLabel: "Or drop / choose an audio file" },
  d2h: { action: "d2h-btn", preview: "d2h-preview", label: "d2h-filename", input: "d2h-file", clear: "d2h-clear-file", emptyLabel: "Or drop / choose a photo" },
};

function setPending(key, blob, name, labelId) {
  const previous = pending[key];
  if (previous?.previewUrl) URL.revokeObjectURL(previous.previewUrl);
  pending[key] = { blob, name };
  const label = $(labelId);
  if (label) {
    label.replaceChildren();
    const filename = document.createElement("span");
    filename.className = "filename";
    filename.textContent = name;
    label.appendChild(filename);
  }
  const ui = PENDING_UI[key];
  if (!ui) return;
  const preview = $(ui.preview);
  if (preview) {
    const previewUrl = URL.createObjectURL(blob);
    pending[key].previewUrl = previewUrl;
    preview.src = previewUrl;
    preview.hidden = false;
    if (preview instanceof HTMLImageElement) preview.alt = `Preview of ${name}`;
  }
  $(ui.action).disabled = false;
  $(ui.clear).disabled = false;
}

function clearPending(key) {
  const ui = PENDING_UI[key];
  const item = pending[key];
  if (item?.previewUrl) URL.revokeObjectURL(item.previewUrl);
  delete pending[key];
  if (!ui) return;
  const preview = $(ui.preview);
  if (preview) {
    preview.removeAttribute("src");
    preview.hidden = true;
  }
  $(ui.input).value = "";
  $(ui.label).textContent = ui.emptyLabel;
  $(ui.action).disabled = true;
  $(ui.clear).disabled = true;
}

Object.keys(PENDING_UI).forEach((key) => {
  $(PENDING_UI[key].action).disabled = true;
});

document.querySelectorAll("[data-clear-pending]").forEach((button) => {
  button.addEventListener("click", () => clearPending(button.dataset.clearPending));
});

function setupDropzone(dropId, inputId, filenameId, key) {
  const drop = $(dropId);
  const input = $(inputId);
  if (!drop || !input) return;

  input.addEventListener("change", () => {
    if (input.files[0]) setPending(key, input.files[0], input.files[0].name, filenameId);
  });
  drop.addEventListener("keydown", (event) => {
    if (event.target === drop && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      input.click();
    }
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
const CAMERA_BOXES_BY_VIEW = {
  blind: ["object-camera", "ocr-camera"],
  hearing: ["sign-camera"],
  comm: ["d2h-camera"],
};
const RECORDERS_BY_VIEW = {
  hearing: ["speech-record-btn"],
  comm: ["h2d-record-btn"],
};
const RECORDER_VIEW_BY_ID = { "speech-record-btn": "hearing", "h2d-record-btn": "comm" };
const activeRecorders = new Map();

function stopRecorder(buttonId) {
  const active = activeRecorders.get(buttonId);
  if (active?.recorder.state === "recording") active.recorder.stop();
}

function stopAllRecorders() {
  activeRecorders.forEach(({ recorder }) => {
    if (recorder.state === "recording") recorder.stop();
  });
}

function stopViewMedia(view) {
  (CAMERA_BOXES_BY_VIEW[view] || []).forEach((boxId) => closeCamera(boxId));
  (RECORDERS_BY_VIEW[view] || []).forEach(stopRecorder);
}

async function openCamera(boxId, videoId) {
  if (activeStreams[boxId]) return;
  if (!navigator.mediaDevices?.getUserMedia) {
    toast("Camera access requires a supported browser and a secure page (localhost or HTTPS).");
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
    });
    if (!(CAMERA_BOXES_BY_VIEW[currentView] || []).includes(boxId)) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    activeStreams[boxId] = stream;
    const video = $(videoId);
    video.srcObject = stream;
    $(boxId).classList.add("active");
    await video.play();
  } catch (err) {
    const stream = activeStreams[boxId];
    if (stream) stream.getTracks().forEach((track) => track.stop());
    delete activeStreams[boxId];
    $(boxId).classList.remove("active");
    toast(`Camera could not start: ${err.message || "check camera permissions and close other apps using the camera."}`);
  }
}

function closeCamera(boxId) {
  const stream = activeStreams[boxId];
  if (stream) stream.getTracks().forEach((t) => t.stop());
  delete activeStreams[boxId];
  $(boxId).classList.remove("active");
  const video = $(boxId).querySelector("video");
  if (video) video.srcObject = null;
}

function captureFrame(videoId) {
  const video = $(videoId);
  if (!video.videoWidth || !video.videoHeight) {
    return Promise.reject(new Error("Camera is not ready yet. Wait for the preview, then capture."));
  }
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("Could not capture a camera frame.")), "image/jpeg", 0.9);
  });
}

function wireCamera({ camBtnId, boxId, videoId, snapId, closeId, key, filenameId, onCaptured }) {
  const camBtn = $(camBtnId);
  if (!camBtn) return;
  camBtn.addEventListener("click", async () => {
    camBtn.disabled = true;
    await openCamera(boxId, videoId);
    camBtn.disabled = false;
  });
  $(closeId).addEventListener("click", () => closeCamera(boxId));
  $(snapId).addEventListener("click", async () => {
    try {
      const blob = await captureFrame(videoId);
      setPending(key, blob, "camera-capture.jpg", filenameId);
      closeCamera(boxId);
      if (onCaptured) onCaptured();
    } catch (err) {
      toast(err.message);
    }
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
    let stream = null;
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
        throw new Error("This browser does not support microphone recording.");
      }
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (currentView !== RECORDER_VIEW_BY_ID[btnId]) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      const mimeType = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"]
        .find((type) => MediaRecorder.isTypeSupported(type));
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      chunks = [];
      recorder.ondataavailable = (e) => chunks.push(e.data);
      recorder.onstop = () => {
        activeRecorders.delete(btnId);
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        const extension = blob.type.includes("mp4") ? "m4a" : blob.type.includes("ogg") ? "ogg" : "webm";
        setPending(key, blob, `recording.${extension}`, filenameId);
        btn.textContent = btn.dataset.idleLabel;
        btn.classList.remove("recording");
      };
      recorder.onerror = (event) => {
        activeRecorders.delete(btnId);
        stream.getTracks().forEach((track) => track.stop());
        btn.textContent = btn.dataset.idleLabel;
        btn.classList.remove("recording");
        toast(`Audio recording failed: ${event.error?.message || "the browser stopped the recording."}`);
      };
      btn.dataset.idleLabel = btn.textContent;
      btn.textContent = "Stop recording";
      btn.classList.add("recording");
      activeRecorders.set(btnId, { recorder, stream });
      recorder.start();
    } catch (err) {
      if (stream) stream.getTracks().forEach((track) => track.stop());
      toast(`Microphone recording could not start: ${err.message || "check microphone permissions."}`);
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

function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

async function fallbackSpeak(text, audioUrl) {
  try {
    if (!audioUrl) {
      const form = new FormData();
      form.append("text", text);
      const response = await fetch(`${API}/api/text-to-speech`, { method: "POST", body: form });
      const json = await response.json();
      if (json.code !== 200) throw new Error(json.message || "Speech generation failed.");
      audioUrl = mediaUrl(json.data.audio_path);
    }
    if (!audioUrl) throw new Error("No playable audio was returned.");
    const audio = new Audio(audioUrl);
    await audio.play();
  } catch (err) {
    toast(`Spoken output failed: ${err.message || "check the device's sound settings."}`);
  }
}

function speakText(text, audioUrl = null) {
  if (!text) return;
  if (!("speechSynthesis" in window)) {
    fallbackSpeak(text, audioUrl);
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.onerror = (event) => {
    if (event.error !== "canceled" && event.error !== "interrupted") fallbackSpeak(text, audioUrl);
  };
  window.speechSynthesis.speak(utterance);
}

function spokenControls(audioUrl, text) {
  const player = audioUrl ? `<audio controls preload="none" src="${escapeHTML(audioUrl)}"></audio>` : "";
  return `${player}<button class="btn btn-ghost result-speak" type="button" data-spoken-text="${escapeHTML(text)}" data-audio-url="${escapeHTML(audioUrl || "")}">Speak result</button>`;
}

document.addEventListener("click", (event) => {
  const button = event.target.closest(".result-speak");
  if (button) speakText(button.dataset.spokenText, button.dataset.audioUrl || null);
  const copyButton = event.target.closest(".result-copy");
  if (copyButton) {
    if (!navigator.clipboard?.writeText) return toast("Clipboard access is unavailable in this browser.");
    navigator.clipboard.writeText(copyButton.dataset.copyText)
      .then(() => toast("Captions copied."))
      .catch((err) => toast(`Could not copy captions: ${err.message}`));
  }
});

function mediaUrl(path) {
  if (!path) return null;
  const filename = path.replace(/\\/g, "/").split("/").pop();
  return `/media/${encodeURIComponent(filename)}`;
}

async function postPending(url, key, fieldName, extra = {}) {
  const item = pending[key];
  if (!item) { toast("Add a photo or recording first."); return null; }
  const fd = new FormData();
  fd.append(fieldName, item.blob, item.name);
  Object.entries(extra).forEach(([k, v]) => fd.append(k, v));
  try {
    const res = await fetch(url, { method: "POST", body: fd });
    return await res.json();
  } catch (err) {
    toast(`The request failed: ${err.message || "could not reach the backend."}`);
    return null;
  }
}

async function runButtonAction(button, busyText, action) {
  if (button.disabled) return;
  const idleText = button.textContent;
  button.disabled = true;
  button.textContent = busyText;
  try {
    await action();
  } catch (err) {
    toast(`Action failed: ${err.message || "please try again."}`);
  } finally {
    button.textContent = idleText;
    button.disabled = button.dataset.pendingKey
      ? !pending[button.dataset.pendingKey]
      : false;
  }
}

/* =========================================================
   Blind mode: object detection
   ========================================================= */

$("object-btn").addEventListener("click", async () => {
  showResult("object-result", "Looking&hellip;");
  const speak = $("object-speak").checked;
  const json = await postPending(`${API}/api/detect-object?speak=${speak}`, "object", "file");
  if (!json) return showResult("object-result", "", true);
  if (json.code !== 200) return showResult("object-result", `<span class="error-text">${escapeHTML(json.message)}</span>`, true);

  const conf = json.data.detections.length ? Math.max(...json.data.detections.map((d) => d.confidence)) : null;
  const audio = mediaUrl(json.data.audio_path);
  const description = json.data.description || "Nothing recognizable found.";
  showResult(
    "object-result",
    confidenceBadge(conf, "detection confidence") +
      `<p class="result-text big">${escapeHTML(description)}</p>` +
      spokenControls(audio, description)
  );
  if (speak) speakText(description, audio);
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
  if (json.code !== 200) return showResult("ocr-result", `<span class="error-text">${escapeHTML(json.message)}</span>`, true);

  const avgConf = json.data.words.length
    ? json.data.words.reduce((a, w) => a + w.confidence, 0) / json.data.words.length
    : null;
  const audio = mediaUrl(json.data.audio_path);
  const text = json.data.text || "No text found.";
  showResult(
    "ocr-result",
    confidenceBadge(avgConf, "reading confidence") +
      `<p class="result-text big">${escapeHTML(text)}</p>` +
      spokenControls(audio, text)
  );
  if (speak && json.data.text) speakText(text, audio);
  refreshDashboard();
});

/* =========================================================
   Hearing mode: speech to text
   ========================================================= */

$("speech-btn").dataset.pendingKey = "speech";
$("speech-btn").addEventListener("click", async () => {
  await runButtonAction($("speech-btn"), "Transcribing\u2026", async () => {
    showResult("speech-result", "Transcribing\u2026");
    const json = await postPending(`${API}/api/speech-to-text`, "speech", "file");
    if (!json) return showResult("speech-result", `<span class="error-text">Could not reach the speech service.</span>`, true);
    if (json.code !== 200) return showResult("speech-result", `<span class="error-text">${escapeHTML(json.message)}</span>`, true);
    const text = json.data.text || "(no speech detected)";
    showResult("speech-result", `<p class="result-text big">${escapeHTML(text)}</p><button class="btn btn-ghost result-copy" type="button" data-copy-text="${escapeHTML(text)}">Copy captions</button>`);
    refreshDashboard();
  });
});

/* =========================================================
   Hearing mode: sign to text
   ========================================================= */

$("sign-btn").dataset.pendingKey = "sign";
$("sign-btn").addEventListener("click", async () => {
  await runButtonAction($("sign-btn"), "Recognizing\u2026", async () => {
    showResult("sign-result", "Recognizing\u2026");
    const speak = $("sign-speak").checked;
    const json = await postPending(`${API}/api/recognize-sign?speak=${speak}`, "sign", "file");
    if (!json) return showResult("sign-result", `<span class="error-text">Could not reach the sign recognition service.</span>`, true);
    if (json.code !== 200) return showResult("sign-result", `<span class="error-text">${escapeHTML(json.message)}</span>`, true);

    const audio = mediaUrl(json.data.audio_path);
    showResult(
      "sign-result",
      confidenceBadge(json.data.confidence, "recognition confidence") +
      `<p class="result-text big">${escapeHTML(json.data.prediction)}</p>` +
        rankList(json.data.top_k) +
      spokenControls(audio, json.data.prediction)
    );
    if (speak) speakText(json.data.prediction, audio);
    refreshDashboard();
  });
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
  const meta = document.createElement("span");
  meta.className = "bubble-meta";
  const time = document.createElement("time");
  time.className = "bubble-time";
  time.dateTime = new Date().toISOString();
  time.textContent = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date());
  meta.textContent = side === "hearing" ? "Hearing participant" : "Deaf participant";
  meta.appendChild(time);
  const content = document.createElement("span");
  content.className = "bubble-text";
  content.textContent = text;
  bubble.append(meta, content);
  if (audio) {
    const player = document.createElement("audio");
    player.controls = true;
    player.preload = "none";
    player.src = audio;
    bubble.appendChild(player);
  }
  wrap.appendChild(bubble);
  wrap.scrollTop = wrap.scrollHeight;
  $("conversation-status").textContent = `${side === "hearing" ? "Hearing participant" : "Deaf participant"} sent a message.`;
}

$("h2d-btn").dataset.pendingKey = "h2d";
$("h2d-btn").addEventListener("click", async () => {
  await runButtonAction($("h2d-btn"), "Transcribing\u2026", async () => {
    $("conversation-status").textContent = "Transcribing the hearing participant’s audio\u2026";
    const json = await postPending(`${API}/api/communicate/hearing-to-deaf`, "h2d", "file");
    if (!json) {
      $("conversation-status").textContent = "Could not reach speech recognition. Your audio is still selected.";
      return;
    }
    if (json.code !== 200) {
      $("conversation-status").textContent = json.message;
      toast(json.message);
      return;
    }
    if (!json.data.text?.trim()) {
      $("conversation-status").textContent = "No speech was detected. Try a clearer or longer recording.";
      return;
    }
    addBubble("hearing", json.data.text.trim());
    refreshDashboard();
  });
});

$("d2h-btn").dataset.pendingKey = "d2h";
$("d2h-btn").addEventListener("click", async () => {
  await runButtonAction($("d2h-btn"), "Recognizing\u2026", async () => {
    $("conversation-status").textContent = "Recognizing the hand sign\u2026";
    const json = await postPending(`${API}/api/communicate/deaf-to-hearing`, "d2h", "file");
    if (!json) {
      $("conversation-status").textContent = "Could not reach sign recognition. Your photo is still selected.";
      return;
    }
    if (json.code !== 200) {
      $("conversation-status").textContent = json.message;
      toast(json.message);
      return;
    }
    addBubble(
      "deaf",
      `${json.data.text} (${Math.round(json.data.confidence * 100)}% confidence)`,
      json.data.audio_path,
    );
    refreshDashboard();
  });
});

async function sendTypedMessage() {
  const text = $("type-input").value.trim();
  if (!text) return toast("Type a message first.");
  const fd = new FormData();
  fd.append("text", text);
  try {
    const res = await fetch(`${API}/api/communicate/type-to-hearing`, { method: "POST", body: fd });
    const json = await res.json();
    if (json.code !== 200) return toast(json.message);
    addBubble("deaf", text, json.data.audio_path);
    $("type-input").value = "";
    refreshDashboard();
  } catch (err) {
    toast(`Message could not be sent: ${err.message}`);
  }
}

$("type-btn").addEventListener("click", () => sendTypedMessage());
$("type-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    sendTypedMessage();
  }
});

$("conversation-clear").addEventListener("click", () => {
  $("transcript").replaceChildren();
  const empty = document.createElement("p");
  empty.className = "transcript-empty";
  empty.textContent = "Conversation cleared from this screen. Start a new message below.";
  $("transcript").appendChild(empty);
  $("conversation-status").textContent = "Conversation cleared. Past activity remains in History.";
});

/* =========================================================================
   LIVE TRANSLATE
   Real-time camera -> sign -> sentence, and real-time speech -> captions.
   ========================================================================= */

/* ---------- Sign -> Speech: live camera + polling + debounce ---------- */

const POLL_INTERVAL_MS = 450;       // delay after each completed request; never stack camera polls
const COMMIT_STREAK = 4;            // consecutive matching polls needed to commit a letter
const COMMIT_CONFIDENCE = 0.55;     // minimum confidence to even consider a candidate

let liveStream = null;
let pollTimer = null;
let liveSessionId = 0;
let confidenceSamples = [];
let liveErrorShown = false;
let candidateLabel = null;
let candidateStreak = 0;
let lastCommittedLabel = null;
let requireBreakBeforeRepeat = false;
let sentenceText = "";
let lastCommitTime = 0;
let spokenThisPause = true;

function setLiveIndicator(id, active, label) {
  const el = $(id);
  el.classList.toggle("active", active);
  el.lastChild.textContent = label;
}

function renderSentence() {
  const box = $("sentence-box");
  box.innerHTML = sentenceText
    ? sentenceText.replace(/</g, "&lt;")
    : `<span class="sentence-placeholder">Your signed letters will build up here&hellip;</span>`;
}

function renderCandidate(label, conf, streak) {
  const row = $("candidate-row");
  if (!label) { row.hidden = true; return; }
  row.hidden = false;
  $("candidate-label").textContent = label;
  $("candidate-fill").style.width = `${Math.round((conf || 0) * 100)}%`;
  const dot = $("candidate-dot");
  dot.className = "confidence-dot " + (streak >= COMMIT_STREAK ? "high" : streak >= 2 ? "mid" : "low");
}

const HAND_BONES = [
  [0, 1, 2, 3, 4], [0, 5, 6, 7, 8], [0, 9, 10, 11, 12],
  [0, 13, 14, 15, 16], [0, 17, 18, 19, 20],
];

function renderHandPattern(points) {
  const lines = $("hand-pattern-lines");
  const dots = $("hand-pattern-points");
  lines.replaceChildren();
  dots.replaceChildren();
  if (!Array.isArray(points) || points.length !== 21) {
    $("hand-pattern-status").textContent = "No hand landmarks detected yet.";
    return;
  }

  HAND_BONES.forEach((bone) => {
    const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    line.setAttribute("points", bone.map((index) => {
      const point = points[index];
      return `${Math.max(0, Math.min(100, point[0] * 100))},${Math.max(0, Math.min(100, point[1] * 100))}`;
    }).join(" "));
    lines.appendChild(line);
  });
  [[5, 9], [9, 13], [13, 17]].forEach(([start, end]) => {
    const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    line.classList.add("palm-connection");
    line.setAttribute("points", [start, end].map((index) => {
      const point = points[index];
      return `${Math.max(0, Math.min(100, point[0] * 100))},${Math.max(0, Math.min(100, point[1] * 100))}`;
    }).join(" "));
    lines.appendChild(line);
  });
  points.forEach(([x, y]) => {
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", Math.max(0, Math.min(100, x * 100)));
    dot.setAttribute("cy", Math.max(0, Math.min(100, y * 100)));
    dot.setAttribute("r", "1.8");
    dots.appendChild(dot);
  });
  $("hand-pattern-status").textContent = "21 hand landmarks captured from the guide area.";
}

function updateConfidenceChart(label, confidence) {
  confidenceSamples.push(Math.max(0, Math.min(1, confidence || 0)));
  if (confidenceSamples.length > 40) confidenceSamples.shift();
  const points = confidenceSamples.map((value, index) => {
    const x = 8 + (confidenceSamples.length > 1 ? index * 224 / (confidenceSamples.length - 1) : 112);
    const y = 78 - value * 66;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  $("confidence-line").setAttribute("points", points.join(" "));
  $("confidence-chart-status").textContent = label
    ? `${label}: ${Math.round(confidence * 100)}% (latest sample)`
    : "No sign detected in the latest sample.";
}

function getGuideCrop(video) {
  const frame = video.parentElement.getBoundingClientRect();
  const guide = $("guide-box").getBoundingClientRect();
  const scale = Math.max(frame.width / video.videoWidth, frame.height / video.videoHeight);
  const offsetX = (video.videoWidth * scale - frame.width) / 2;
  const offsetY = (video.videoHeight * scale - frame.height) / 2;
  const left = Math.max(0, (guide.left - frame.left + offsetX) / scale);
  const top = Math.max(0, (guide.top - frame.top + offsetY) / scale);
  const right = Math.min(video.videoWidth, (guide.right - frame.left + offsetX) / scale);
  const bottom = Math.min(video.videoHeight, (guide.bottom - frame.top + offsetY) / scale);
  return { left, top, width: right - left, height: bottom - top };
}

async function pollLiveFrame(sessionId) {
  const video = $("live-video");
  try {
    if (sessionId !== liveSessionId || !liveStream) return;
    if (!video.videoWidth || !video.videoHeight) {
      $("live-status-chip").textContent = "Waiting for camera frame\u2026";
      return;
    }
    const crop = getGuideCrop(video);
    if (crop.width <= 0 || crop.height <= 0) throw new Error("Camera guide area is not visible.");

    const canvas = document.createElement("canvas");
    const scale = Math.min(1, 640 / Math.max(crop.width, crop.height));
    canvas.width = Math.max(1, Math.round(crop.width * scale));
    canvas.height = Math.max(1, Math.round(crop.height * scale));
    canvas.getContext("2d").drawImage(
      video, crop.left, crop.top, crop.width, crop.height, 0, 0, canvas.width, canvas.height,
    );
    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob((image) => image ? resolve(image) : reject(new Error("Could not capture camera frame.")), "image/jpeg", 0.78);
    });
    const fd = new FormData();
    fd.append("file", blob, "frame.jpg");
    const res = await fetch(`${API}/api/recognize-sign?log=false`, { method: "POST", body: fd });
    const json = await res.json();
    if (sessionId !== liveSessionId) return;

    if (json.code !== 200 || !json.data?.prediction) {
      const isHandMissing = json.data?.error?.toLowerCase().includes("hand") || json.code === 422;
      $("live-status-chip").textContent = isHandMissing
        ? "No hand detected inside the guide area"
        : (json.message || "Recognition unavailable");
      candidateLabel = null;
      candidateStreak = 0;
      renderCandidate(null);
      renderHandPattern([]);
      updateConfidenceChart(null, 0);
      return;
    }

    const { prediction, confidence } = json.data;
    renderHandPattern(json.data.hand_landmarks);
    updateConfidenceChart(prediction, confidence);
    $("live-status-chip").textContent = "Watching\u2026";

    if (confidence < COMMIT_CONFIDENCE) {
      candidateLabel = null;
      candidateStreak = 0;
      renderCandidate(prediction, confidence, 0);
      return;
    }

    if (prediction === candidateLabel) {
      candidateStreak += 1;
    } else {
      candidateLabel = prediction;
      candidateStreak = 1;
    }

    if (prediction !== lastCommittedLabel) requireBreakBeforeRepeat = false;
    renderCandidate(candidateLabel, confidence, candidateStreak);

    const readyToCommit =
      candidateStreak >= COMMIT_STREAK &&
      !(candidateLabel === lastCommittedLabel && requireBreakBeforeRepeat);

    if (readyToCommit) {
      sentenceText += candidateLabel;
      renderSentence();
      lastCommittedLabel = candidateLabel;
      requireBreakBeforeRepeat = true;
      lastCommitTime = Date.now();
      spokenThisPause = false;
      candidateStreak = 0;
      $("live-status-chip").textContent = `Added "${candidateLabel}"`;
    }
  } catch (err) {
    if (sessionId === liveSessionId) {
      $("live-status-chip").textContent = `Recognition error: ${err.message}`;
      if (!liveErrorShown) {
        toast(`Live recognition error: ${err.message}`);
        liveErrorShown = true;
      }
    }
  } finally {
    if (liveStream && sessionId === liveSessionId) {
      pollTimer = setTimeout(() => pollLiveFrame(sessionId), POLL_INTERVAL_MS);
    }
  }
}

async function startLiveCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    toast("Camera access requires a supported browser and a secure page (localhost or HTTPS).");
    return;
  }
  const sessionId = ++liveSessionId;
  const button = $("live-cam-toggle");
  button.disabled = true;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "user" }, width: { ideal: 1280 }, height: { ideal: 720 } },
    });
    if (sessionId !== liveSessionId) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    liveStream = stream;
    const video = $("live-video");
    video.srcObject = stream;
    await video.play();
  } catch (err) {
    if (liveStream) liveStream.getTracks().forEach((track) => track.stop());
    liveStream = null;
    $("live-video").srcObject = null;
    $("live-status-chip").textContent = "Camera could not start";
    toast(`Camera could not start: ${err.message || "check camera permissions."}`);
    button.disabled = false;
    return;
  }
  button.disabled = false;
  button.textContent = "Stop camera";
  setLiveIndicator("sign-live-indicator", true, "live");
  $("live-status-chip").textContent = "Waiting for camera frame\u2026";
  confidenceSamples = [];
  $("confidence-line").setAttribute("points", "");
  liveErrorShown = false;
  pollLiveFrame(sessionId);

  // Auto-speak-on-pause watcher: separate from the fast poll loop.
  pauseWatcher = setInterval(() => {
    if (!$("auto-speak").checked || spokenThisPause || !sentenceText) return;
    if (Date.now() - lastCommitTime > 1500) {
      speakSentence();
      spokenThisPause = true;
    }
  }, 500);
}

let pauseWatcher = null;

function stopLiveCamera() {
  liveSessionId += 1;
  if (pollTimer) clearTimeout(pollTimer);
  if (pauseWatcher) clearInterval(pauseWatcher);
  pollTimer = null;
  pauseWatcher = null;
  if (liveStream) liveStream.getTracks().forEach((t) => t.stop());
  liveStream = null;
  $("live-video").srcObject = null;
  $("live-cam-toggle").textContent = "Start camera";
  $("live-cam-toggle").disabled = false;
  setLiveIndicator("sign-live-indicator", false, "off");
  $("live-status-chip").textContent = "Camera off";
  renderCandidate(null);
  renderHandPattern([]);
  updateConfidenceChart(null, 0);
  candidateLabel = null;
  candidateStreak = 0;
}

$("live-cam-toggle").addEventListener("click", () => {
  if (liveStream) stopLiveCamera();
  else startLiveCamera();
});

function speakSentence() {
  if (!sentenceText.trim()) return;
  speakText(sentenceText);
  // Log the finished sentence as one meaningful event (not every poll).
  const fd = new FormData();
  fd.append("modality", "sign_language");
  fd.append("text", sentenceText);
  fetch(`${API}/api/history/log`, { method: "POST", body: fd }).then(() => {
    if (currentView === "dashboard") refreshDashboard();
  });
}

$("sentence-speak").addEventListener("click", speakSentence);
$("sentence-space").addEventListener("click", () => { sentenceText += " "; renderSentence(); });
$("sentence-backspace").addEventListener("click", () => { sentenceText = sentenceText.slice(0, -1); renderSentence(); });
$("sentence-clear").addEventListener("click", () => {
  sentenceText = "";
  lastCommittedLabel = null;
  requireBreakBeforeRepeat = false;
  renderSentence();
});

/* ---------- Speech -> Captions: Web Speech API, with a recorded-clip fallback ---------- */

const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;

let hearingRecognizer = null;
let hearingLiveActive = false;
let hearingLiveRestartTimer = null;
let hearingLiveFinalText = "";

function renderHearingLiveCaptions(interim = "") {
  const box = $("hearing-live-box");
  box.replaceChildren();
  if (!hearingLiveFinalText && !interim) {
    const placeholder = document.createElement("span");
    placeholder.className = "sentence-placeholder";
    placeholder.textContent = "Live captions will appear here.";
    box.appendChild(placeholder);
  } else {
    box.append(document.createTextNode(hearingLiveFinalText));
    if (interim) {
      const pendingText = document.createElement("span");
      pendingText.className = "caption-interim";
      pendingText.textContent = interim;
      box.appendChild(pendingText);
    }
  }
  box.scrollTop = box.scrollHeight;
}

function stopHearingCaptions() {
  const text = hearingLiveFinalText.trim();
  const wasActive = hearingLiveActive;
  hearingLiveActive = false;
  if (hearingLiveRestartTimer) clearTimeout(hearingLiveRestartTimer);
  hearingLiveRestartTimer = null;
  if (wasActive && hearingRecognizer) {
    try {
      hearingRecognizer.stop();
    } catch (err) {
      if (err.name !== "InvalidStateError") {
        toast(`Live captions could not stop cleanly: ${err.message}`);
      }
    }
  }
  $("hearing-live-toggle").textContent = "Start live captions";
  $("hearing-live-toggle").classList.remove("recording");
  if (text) {
    const form = new FormData();
    form.append("modality", "speech");
    form.append("text", text);
    fetch(`${API}/api/history/log`, { method: "POST", body: form }).catch((err) => {
      toast(`Could not save live captions to History: ${err.message}`);
    });
  }
}

function startHearingCaptions() {
  if (!SpeechRecognitionAPI) return;
  hearingLiveFinalText = "";
  renderHearingLiveCaptions();
  const recognizer = new SpeechRecognitionAPI();
  hearingRecognizer = recognizer;
  recognizer.continuous = true;
  recognizer.interimResults = true;
  recognizer.lang = navigator.language || "en-US";
  recognizer.onresult = (event) => {
    let interim = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      if (result.isFinal) hearingLiveFinalText += `${result[0].transcript.trim()} `;
      else interim += result[0].transcript;
    }
    renderHearingLiveCaptions(interim);
  };
  recognizer.onerror = (event) => {
    if (["not-allowed", "service-not-allowed", "audio-capture"].includes(event.error)) {
      hearingLiveActive = false;
      $("hearing-live-toggle").textContent = "Start live captions";
      $("hearing-live-toggle").classList.remove("recording");
      $("hearing-live-note").textContent = event.error === "audio-capture"
        ? "No microphone was found. Connect one or record/upload a clip instead."
        : "Microphone or speech service access was blocked. Check browser permissions or record/upload a clip instead.";
      return;
    }
    if (event.error && !["no-speech", "aborted"].includes(event.error)) {
      $("hearing-live-note").textContent = `Live captions stopped (${event.error}). Record or upload a clip instead.`;
    }
  };
  recognizer.onend = () => {
    if (!hearingLiveActive) return;
    hearingLiveRestartTimer = setTimeout(() => {
      if (hearingLiveActive && hearingRecognizer === recognizer) {
        try {
          recognizer.start();
        } catch (err) {
          stopHearingCaptions();
          $("hearing-live-note").textContent = `Live captions could not restart: ${err.message}`;
        }
      }
    }, 250);
  };
  hearingLiveActive = true;
  try {
    recognizer.start();
    $("hearing-live-toggle").textContent = "Stop live captions";
    $("hearing-live-toggle").classList.add("recording");
    $("hearing-live-note").textContent = "Listening. Captions appear as speech is recognized.";
  } catch (err) {
    hearingLiveActive = false;
    $("hearing-live-note").textContent = `Live captions could not start: ${err.message}`;
  }
}

if (SpeechRecognitionAPI) {
  $("hearing-live-toggle").addEventListener("click", () => {
    if (hearingLiveActive) stopHearingCaptions();
    else startHearingCaptions();
  });
} else {
  $("hearing-live-toggle").hidden = true;
  $("hearing-live-note").textContent =
    "Live browser captions are unavailable here. Record or upload a clip for transcription.";
}

$("hearing-live-clear").addEventListener("click", () => {
  hearingLiveFinalText = "";
  renderHearingLiveCaptions();
});

let recognizer = null;
let listening = false;
let captionFinalText = "";

function renderCaptions(interim) {
  const box = $("caption-box");
  const final = captionFinalText.replace(/</g, "&lt;");
  const interimSafe = (interim || "").replace(/</g, "&lt;");
  if (!final && !interimSafe) {
    box.innerHTML = `<span class="sentence-placeholder">Captions will appear here while listening&hellip;</span>`;
  } else {
    box.innerHTML = `${final}<span class="caption-interim">${interimSafe}</span>`;
  }
  box.scrollTop = box.scrollHeight;
}

function logCaptionSession() {
  const text = captionFinalText.trim();
  if (!text) return;
  const fd = new FormData();
  fd.append("modality", "speech");
  fd.append("text", text);
  fetch(`${API}/api/history/log`, { method: "POST", body: fd }).then(() => {
    if (currentView === "dashboard") refreshDashboard();
  });
}

function startCaptions() {
  if (!SpeechRecognitionAPI) return;
  recognizer = new SpeechRecognitionAPI();
  recognizer.continuous = true;
  recognizer.interimResults = true;
  recognizer.lang = "en-US";

  recognizer.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript;
      if (event.results[i].isFinal) captionFinalText += transcript + " ";
      else interim += transcript;
    }
    renderCaptions(interim);
  };
  recognizer.onerror = (event) => {
    const fatal = ["not-allowed", "service-not-allowed", "audio-capture"].includes(event.error);
    if (fatal) {
      listening = false;
      $("caption-toggle").textContent = "Start listening";
      setLiveIndicator("caption-live-indicator", false, "off");
      toast(event.error === "audio-capture"
        ? "No microphone was found. Connect a microphone and try again."
        : "Microphone access or browser speech recognition was blocked. Check permissions and try again.");
      return;
    }
    if (event.error && event.error !== "no-speech" && event.error !== "aborted") {
      toast(`Live captions stopped: ${event.error}. Try recording a clip instead.`);
    }
  };
  recognizer.onend = () => {
    if (listening) {
      setTimeout(() => {
        if (!listening) return;
        try {
          recognizer.start();
        } catch (err) {
          listening = false;
          $("caption-toggle").textContent = "Start listening";
          setLiveIndicator("caption-live-indicator", false, "off");
          toast(`Live captions could not restart: ${err.message}`);
        }
      }, 250);
    }
  };

  listening = true;
  try {
    recognizer.start();
  } catch (err) {
    listening = false;
    toast(`Live captions could not start: ${err.message}`);
    return;
  }
  $("caption-toggle").textContent = "Stop listening";
  setLiveIndicator("caption-live-indicator", true, "live");
}

function stopCaptions() {
  listening = false;
  if (recognizer) recognizer.stop();
  $("caption-toggle").textContent = "Start listening";
  setLiveIndicator("caption-live-indicator", false, "off");
  logCaptionSession();
}

if (SpeechRecognitionAPI) {
  $("caption-toggle").addEventListener("click", () => {
    if (listening) stopCaptions();
    else startCaptions();
  });
} else {
  $("caption-toggle").hidden = true;
  $("caption-fallback").hidden = false;

  let fallbackRecorder = null;
  let fallbackChunks = [];
  let fallbackBlob = null;

  $("caption-record-btn").addEventListener("click", async () => {
    if (fallbackRecorder && fallbackRecorder.state === "recording") {
      fallbackRecorder.stop();
      return;
    }
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
        throw new Error("This browser does not support microphone recording.");
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"]
        .find((type) => MediaRecorder.isTypeSupported(type));
      fallbackRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      fallbackChunks = [];
      fallbackRecorder.ondataavailable = (e) => fallbackChunks.push(e.data);
      fallbackRecorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        fallbackBlob = new Blob(fallbackChunks, { type: fallbackRecorder.mimeType || "audio/webm" });
        $("caption-record-btn").textContent = "Record audio";
      };
      $("caption-record-btn").textContent = "Stop recording";
      fallbackRecorder.start();
    } catch (err) {
      toast(`Microphone recording could not start: ${err.message || "check microphone permissions."}`);
    }
  });

  $("caption-upload-btn").addEventListener("click", async () => {
    if (!fallbackBlob) return toast("Record a clip first.");
    const fd = new FormData();
    fd.append("file", fallbackBlob, "clip.webm");
    const res = await fetch(`${API}/api/speech-to-text`, { method: "POST", body: fd });
    try {
      const json = await res.json();
      if (json.code !== 200) return toast(json.message);
      captionFinalText += json.data.text + " ";
      renderCaptions("");
    } catch (err) {
      toast(`Transcription request failed: ${err.message}`);
    }
  });
}

$("caption-clear").addEventListener("click", () => {
  captionFinalText = "";
  renderCaptions("");
});

/* ---------- Whole-word signs (only if a word model has been trained) ---------- */

fetch(`${API}/api/word-model-status`)
  .then((r) => r.json())
  .then((json) => {
    const trained = json.code === 200 && json.data.trained;
    $("word-mode-box").hidden = !trained;
    $("word-mode-unavailable").hidden = trained;
  })
  .catch(() => { /* leave the "not trained yet" message showing */ });

let wordRecorder = null;
let wordChunks = [];

function startWordRecording() {
  if (!liveStream) return toast("Start the camera first.");
  wordChunks = [];
  wordRecorder = new MediaRecorder(liveStream, { mimeType: "video/webm" });
  wordRecorder.ondataavailable = (e) => wordChunks.push(e.data);
  wordRecorder.onstop = sendWordClip;
  wordRecorder.start();
  $("word-record-btn").textContent = "\u25CF Recording\u2026 release to send";
  $("word-record-btn").classList.add("recording");
}

function stopWordRecording() {
  if (wordRecorder && wordRecorder.state === "recording") wordRecorder.stop();
  $("word-record-btn").textContent = "\u25CF Record word";
  $("word-record-btn").classList.remove("recording");
}

async function sendWordClip() {
  const blob = new Blob(wordChunks, { type: "video/webm" });
  $("word-mode-result").textContent = "Recognizing\u2026";
  const fd = new FormData();
  fd.append("file", blob, "word.webm");
  const res = await fetch(`${API}/api/recognize-word?log=false`, { method: "POST", body: fd });
  const json = await res.json();
  if (json.code !== 200) {
    $("word-mode-result").textContent = json.message;
    return;
  }
  $("word-mode-result").textContent = `"${json.data.prediction}" (${Math.round(json.data.confidence * 100)}%)`;
  sentenceText += (sentenceText && !sentenceText.endsWith(" ") ? " " : "") + json.data.prediction.toUpperCase() + " ";
  renderSentence();
  lastCommitTime = Date.now();
  spokenThisPause = false;
}

const wordBtn = $("word-record-btn");
wordBtn.addEventListener("mousedown", startWordRecording);
wordBtn.addEventListener("mouseup", stopWordRecording);
wordBtn.addEventListener("mouseleave", stopWordRecording);
wordBtn.addEventListener("touchstart", (e) => { e.preventDefault(); startWordRecording(); });
wordBtn.addEventListener("touchend", (e) => { e.preventDefault(); stopWordRecording(); });

/* ---------- Shared cleanup ---------- */

function stopLiveTranslate() {
  stopLiveCamera();
  if (listening) stopCaptions();
}
