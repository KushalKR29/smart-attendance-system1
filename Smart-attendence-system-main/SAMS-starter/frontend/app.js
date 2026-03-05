// app.js — improved: wait for camera, enable buttons, and log errors
const video = document.getElementById('video');
const enrollBtn = document.getElementById('enrollBtn');
const recognizeBtn = document.getElementById('recognizeBtn');
const studentIdInput = document.getElementById('studentId');
const studentNameInput = document.getElementById('studentName');
const log = document.getElementById('log');
const state = document.getElementById('state');

function logMsg(...args){
  console.log(...args);
  log.innerText = `${new Date().toLocaleTimeString()} — ` + args.map(a => (typeof a === 'object' ? JSON.stringify(a, null, 2) : String(a))).join(' ');
}

// Update UI state
function setState(s){
  state.innerText = s;
  logMsg('STATE:', s);
}

// Initialize camera and enable controls when ready
async function init() {
  setState('requesting camera...');
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false });
    video.srcObject = stream;

    // Wait until video has enough metadata to capture frames
    await new Promise((resolve) => {
      if (video.readyState >= 2) return resolve();
      video.onloadedmetadata = () => resolve();
    });

    setState('camera ready');
    enrollBtn.disabled = false;
    recognizeBtn.disabled = false;

  } catch (e) {
    setState('camera error');
    logMsg('Error accessing camera:', e);
    alert('Camera access failed. Check permissions and that no other app is using the camera.');
  }
}

// capture a blob from the video element
function captureBlob() {
  if (!video.videoWidth || !video.videoHeight) {
    throw new Error('video not ready (width/height missing)');
  }
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.9));
}

// generic uploader with error handling
async function postImageToEndpoint(endpoint, formFields={}) {
  try {
    const blob = await captureBlob();
    if (!blob) throw new Error('captureBlob returned null - video may not be ready');
    const fd = new FormData();
    for (const k in formFields) {
      fd.append(k, formFields[k]);
    }
    fd.append('image', blob, 'capture.jpg');

    setState(`posting to ${endpoint}...`);
    const res = await fetch(endpoint, { method: 'POST', body: fd });
    const text = await res.text();
    let json;
    try { json = JSON.parse(text); } catch(e){ json = { raw: text }; }
    setState(`response ${res.status}`);
    logMsg({ endpoint, status: res.status, body: json });
    return { ok: res.ok, status: res.status, body: json };
  } catch (err) {
    setState('network/error');
    logMsg('Upload error:', err);
    return { ok: false, error: String(err) };
  }
}

async function enroll() {
  const student_id = studentIdInput.value.trim();
  const name = studentNameInput.value.trim();
  if (!student_id) { alert('enter student id'); return; }
  enrollBtn.disabled = true;
  const endpoint = 'http://localhost:5000/api/enroll';
  const result = await postImageToEndpoint(endpoint, { student_id, name });
  enrollBtn.disabled = false;
  if (!result.ok) {
    alert('Enroll failed — see console/log');
  }
}

async function recognize() {
  recognizeBtn.disabled = true;
  const endpoint = 'http://localhost:5000/api/recognize';
  const result = await postImageToEndpoint(endpoint, {});
  recognizeBtn.disabled = false;
  if (!result.ok) {
    alert('Recognize failed — see console/log');
  }
}

enrollBtn.addEventListener('click', enroll);
recognizeBtn.addEventListener('click', recognize);

init();
