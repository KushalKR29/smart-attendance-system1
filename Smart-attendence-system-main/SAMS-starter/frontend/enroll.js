// frontend/enroll.js
// Start-camera -> auto-capture multiple frames -> upload to /api/enroll
// Also keep a manual enroll button for single snapshot.

// Config
const API_BASE = "http://localhost:5000";
const MULTI_CAPTURE_COUNT = 6;        // number of frames to auto-capture on Start Camera
const MULTI_CAPTURE_DELAY_MS = 160;   // ms between frames

// Elements
const video = document.getElementById("video");
const placeholder = document.getElementById("cameraPlaceholder");
const startCamBtn = document.getElementById("startCam");
const enrollBtn = document.getElementById("enrollBtn");
const sidInput = document.getElementById("sid");
const snameInput = document.getElementById("sname");
const emailInput = document.getElementById("email");
const statusEl = document.getElementById("status");

let currentStream = null;

// Helpers
function setStatus(text, cls="") {
  statusEl.innerText = text || "";
  statusEl.className = "status" + (cls ? " " + cls : "");
}
function stopStream() {
  if (!currentStream) return;
  currentStream.getTracks().forEach(t => t.stop());
  currentStream = null;
  video.pause();
  video.srcObject = null;
  video.style.display = "none";
  if (placeholder) placeholder.style.display = "block";
}
function sleep(ms){ return new Promise(r => setTimeout(r, ms)); }

async function startCamera(constraints = { video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" }, audio: false }) {
  try {
    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    currentStream = stream;
    video.srcObject = stream;
    video.style.display = "block";
    if (placeholder) placeholder.style.display = "none";
    await video.play();
    return true;
  } catch (err) {
    console.error("startCamera error", err);
    setStatus("Cannot open camera — allow camera permission or try a different browser.", "error");
    return false;
  }
}

function captureCanvasFromVideo() {
  const w = video.videoWidth || 640;
  const h = video.videoHeight || 480;
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const ctx = c.getContext("2d");
  ctx.drawImage(video, 0, 0, w, h);
  return c;
}

async function canvasToBlob(canvas, mime="image/jpeg", quality=0.85){
  return await new Promise(res => canvas.toBlob(res, mime, quality));
}

/* ---- Multi-capture upload (auto on Start Camera) ----
   Behavior:
   - Validate fields presence
   - Start camera
   - Capture MULTI_CAPTURE_COUNT frames with small delay
   - Upload as FormData with field name 'images' (backend checks for "images")
   - Stop camera on completion
*/
startCamBtn.addEventListener("click", async (ev) => {
  ev.preventDefault();
  setStatus(""); // clear previous

  const studentId = sidInput.value.trim();
  const studentName = snameInput.value.trim();
  const email = emailInput.value.trim();

  if (!studentId || !studentName) {
    setStatus("Student ID and Full Name are required.", "error");
    return;
  }

  setStatus("Starting camera...", "");

  const ok = await startCamera();
  if (!ok) return;

  // wait briefly for camera to stabilize
  await sleep(220);

  setStatus(`Capturing ${MULTI_CAPTURE_COUNT} photos...`, "");

  const blobs = [];
  for (let i = 0; i < MULTI_CAPTURE_COUNT; i++){
    const canvas = captureCanvasFromVideo();
    const b = await canvasToBlob(canvas, "image/jpeg", 0.85);
    if (b) {
      blobs.push({ blob: b, name: `${studentId}_${i}.jpg` });
    }
    // small delay between captures; gives slight variety in frames
    await sleep(MULTI_CAPTURE_DELAY_MS);
  }

  if (blobs.length === 0) {
    setStatus("Failed to capture images from camera.", "error");
    stopStream();
    return;
  }

  setStatus("Uploading enrollment data...", "");

  // Prepare FormData - uses 'images' key for multiple files (backend handles 'images' or 'image')
  const fd = new FormData();
  fd.append("student_id", studentId);
  fd.append("name", studentName);
  if (email) fd.append("email", email);
  // append multiple under key 'images'
  blobs.forEach((it) => fd.append("images", it.blob, it.name));

  try {
    const resp = await fetch(`${API_BASE}/api/enroll`, { method: "POST", body: fd });
    const data = await resp.json().catch(() => ({ error: "Invalid JSON response" }));

    if (resp.ok && data.ok) {
      setStatus("Enrollment successful.", "success");
      // optionally reset inputs
      // sidInput.value = ""; snameInput.value = ""; emailInput.value = "";
    } else {
      // backend returned error or error field
      const msg = data.error || JSON.stringify(data);
      setStatus("Enrollment failed: " + msg, "error");
    }
  } catch (err) {
    console.error("enroll upload error", err);
    setStatus("Network error while uploading enrollment.", "error");
  } finally {
    // stop camera to free device
    stopStream();
  }
});

/* ---- Manual enroll (single snapshot) ----
   If teacher prefers to press Enroll Student after verifying preview
*/
enrollBtn.addEventListener("click", async (ev) => {
  ev.preventDefault();
  setStatus("");

  const studentId = sidInput.value.trim();
  const studentName = snameInput.value.trim();
  const email = emailInput.value.trim();

  if (!studentId || !studentName) {
    setStatus("Student ID and Full Name are required.", "error");
    return;
  }

  // If camera not active, start temporarily to capture
  let startedNow = false;
  if (!currentStream) {
    const ok = await startCamera();
    if (!ok) return;
    startedNow = true;
    // wait small time to ensure video has data
    await sleep(180);
  }

  const canvas = captureCanvasFromVideo();
  const blob = await canvasToBlob(canvas, "image/jpeg", 0.9);

  const fd = new FormData();
  fd.append("student_id", studentId);
  fd.append("name", studentName);
  if (email) fd.append("email", email);
  // single image key 'image'
  fd.append("image", blob, `${studentId}.jpg`);

  setStatus("Uploading enrollment...", "");

  try {
    const resp = await fetch(`${API_BASE}/api/enroll`, { method: "POST", body: fd });
    const data = await resp.json().catch(() => ({ error: "Invalid JSON response" }));

    if (resp.ok && data.ok) {
      setStatus("Enrollment successful.", "success");
    } else {
      const msg = data.error || JSON.stringify(data);
      setStatus("Enrollment failed: " + msg, "error");
    }
  } catch (err) {
    console.error("manual enroll error", err);
    setStatus("Network error while uploading enrollment.", "error");
  } finally {
    if (startedNow) stopStream();
  }
});

/* ---- Optional: Stop camera when page unloads ---- */
window.addEventListener("beforeunload", () => {
  stopStream();
});
