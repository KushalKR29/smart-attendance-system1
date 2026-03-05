// frontend/live.js (FIXED: Sends Class & Period ID)
const API_BASE = "http://localhost:5000";

// 1. DOM Elements
const videoEl = document.getElementById("liveVideo");
const overlayEl = document.getElementById("cameraOverlay");
const recognizedListEl = document.getElementById("recognizedList");
const recognizedCountEl = document.getElementById("recognizedCount");
const liveClassLabel = document.getElementById("liveClassLabel");
const stopBtn = document.getElementById("stopBtn");

let stream = null;
let captureInterval = null;
let isScanning = false;
const recognizedSet = new Set(); 

// Variables to store current class info
let currentPeriodId = null;
let currentClassCode = null;

// 2. Setup Page on Load
document.addEventListener("DOMContentLoaded", async () => {
    // A. Load Class Name (Visual only)
    const className = localStorage.getItem("active_class_name") || "General Attendance";
    if (liveClassLabel) liveClassLabel.innerText = className;

    // B. FETCH ACTIVE PERIOD ID (Crucial for Database Saving!)
    try {
        const res = await fetch(`${API_BASE}/api/teacher/current_period`);
        const data = await res.json();
        
        if (data.current && data.current.id) {
            currentPeriodId = data.current.id;
            currentClassCode = data.current.class_code;
            console.log(`Live Attendance Active for: Period ${currentPeriodId}, Class ${currentClassCode}`);
        } else {
            console.warn("No active period found in backend. Attendance might not be saved to DB.");
            if (overlayEl) overlayEl.innerText = "Warning: No active period found.";
        }
    } catch (e) {
        console.error("Failed to load period info:", e);
    }

    // C. Start Camera
    startCamera();
});

// 3. Start Camera Function
async function startCamera() {
    try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true });
        videoEl.srcObject = stream;
        videoEl.play();
        isScanning = true;
        
        if (overlayEl) overlayEl.innerText = "Camera Active — Scanning...";

        // Start capturing frames every 2 seconds
        captureInterval = setInterval(captureAndSend, 2000);
    } catch (err) {
        console.error("Camera error:", err);
        if (overlayEl) overlayEl.innerText = "Error: Camera access denied.";
        alert("Could not start camera. Please allow permissions.");
    }
}

// 4. Capture & Send to Backend
async function captureAndSend() {
    if (!isScanning) return;

    const canvas = document.createElement("canvas");
    canvas.width = videoEl.videoWidth;
    canvas.height = videoEl.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(videoEl, 0, 0);

    canvas.toBlob(async (blob) => {
        if (!blob) return;

        const formData = new FormData();
        formData.append("image", blob, "capture.jpg");

        // --- IMPORTANT FIX: Send Period ID & Class Code ---
        if (currentPeriodId) formData.append("period_id", currentPeriodId);
        if (currentClassCode) formData.append("class_code", currentClassCode);

        try {
            const res = await fetch(`${API_BASE}/api/recognize`, {
                method: "POST",
                body: formData
            });

            const data = await res.json();
            
            if (data.matches && data.matches.length > 0) {
                handleMatches(data.matches);
            }
        } catch (err) {
            console.error("Recognition API error:", err);
        }
    }, "image/jpeg", 0.8);
}

// 5. Handle Results
function handleMatches(matches) {
    matches.forEach(m => {
        if (m.confidence > 0.5) {
            // Check if backend confirmed recording
            const isRecorded = m.recorded === true;
            
            if (!recognizedSet.has(m.student_id)) {
                recognizedSet.add(m.student_id);
                addStudentToList(m.student_id, isRecorded);
            }
        }
    });
    
    if (recognizedCountEl) {
        recognizedCountEl.innerText = `${recognizedSet.size} detected`;
    }
}

// 6. Add Student to UI List
function addStudentToList(studentId, isRecorded) {
    const div = document.createElement("div");
    div.className = "recognized-item"; 
    div.style.padding = "10px";
    div.style.borderBottom = "1px solid #444";
    div.style.display = "flex";
    div.style.justifyContent = "space-between";
    div.style.alignItems = "center";

    const timeStr = new Date().toLocaleTimeString();
    
    // Green check if saved to DB, yellow if just recognized but not saved
    const statusIcon = isRecorded ? "✅ Saved" : "⚠️ Not Saved";
    const statusColor = isRecorded ? "#4cc9f0" : "#ffbd00";

    div.innerHTML = `
        <div>
            <span style="font-weight:bold; color:${statusColor};">${studentId}</span>
            <span style="color:#aaa; font-size:0.9em; margin-left:10px;">${statusIcon}</span>
        </div>
        <span style="font-size:0.8em; color:#666;">${timeStr}</span>
    `;

    if (recognizedListEl) recognizedListEl.prepend(div);
}

// 7. Stop Button Logic
if (stopBtn) {
    stopBtn.addEventListener("click", () => {
        isScanning = false;
        clearInterval(captureInterval);
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
        }
        window.location.href = "dashboard.html";
    });
}