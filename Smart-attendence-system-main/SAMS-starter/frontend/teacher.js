// frontend/teacher.js (COMPLETE VERSION)
const API = "http://localhost:5000";
let autoRefreshTimer = null;

// --- 1. Helper Functions ---
async function safeFetchJSON(url, opts={}) {
  try {
    const r = await fetch(url, opts);
    if (!r.ok) throw new Error("bad status " + r.status);
    return r.json();
  } catch(e) {
    console.warn("fetch failed", url, e);
    return null;
  }
}

function formatTime(timeString) {
    if (!timeString) return "--";
    const [hours, minutes] = timeString.split(':');
    const date = new Date();
    date.setHours(hours);
    date.setMinutes(minutes);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// --- 2. Top Section: Current & Next Period ---
async function loadCurrentPeriod() {
    const data = await safeFetchJSON(`${API}/api/teacher/current_period`);
    if (!data) return;

    // Update Current Period
    const currentClassEl = document.getElementById('currentClassName');
    const currentTimeEl = document.getElementById('currentTime');
    const currentRoomEl = document.getElementById('currentRoom');
    const takeBtn = document.getElementById('takeAttendanceBtn');

    if (data.current) {
        if(currentClassEl) currentClassEl.innerText = data.current.class_name;
        if(currentTimeEl) currentTimeEl.innerText = formatTime(data.current.start_time) + " - " + formatTime(data.current.end_time);
        if(currentRoomEl) currentRoomEl.innerText = data.current.room || "Room N/A";
        if(takeBtn) takeBtn.disabled = false;
    } else {
        if(currentClassEl) currentClassEl.innerText = "No active period";
        if(currentTimeEl) currentTimeEl.innerText = "--";
        if(currentRoomEl) currentRoomEl.innerText = "--";
        if(takeBtn) takeBtn.disabled = true;
    }

    // Update Next Period
    const nextClassEl = document.getElementById('nextClassName');
    const nextTimeEl = document.getElementById('nextTime');
    const nextRoomEl = document.getElementById('nextRoom');

    if (data.next) {
        if(nextClassEl) nextClassEl.innerText = data.next.class_name;
        if(nextTimeEl) nextTimeEl.innerText = formatTime(data.next.start_time) + " - " + formatTime(data.next.end_time);
        if(nextRoomEl) nextRoomEl.innerText = data.next.room || "Room N/A";
    } else {
        if(nextClassEl) nextClassEl.innerText = "No upcoming classes";
        if(nextTimeEl) nextTimeEl.innerText = "--";
        if(nextRoomEl) nextRoomEl.innerText = "--";
    }
}

// --- 3. Bottom Section: Student Summary Table ---
async function loadStudentSummary() {
    // Fetch summary from backend
    const data = await safeFetchJSON(`${API}/api/attendance/summary`);
    if (!data || !data.summary) return;

    const tbody = document.getElementById('attendanceBody');
    const totalLabel = document.getElementById('totalClassesLabel');
    
    if (totalLabel) totalLabel.innerText = `Total classes held: ${data.total_classes || 0}`;
    if (!tbody) return;

    tbody.innerHTML = ""; // Clear existing rows

    if (data.summary.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 20px;">No students found</td></tr>`;
        return;
    }

    data.summary.forEach(student => {
        const tr = document.createElement('tr');
        
        // Determine status badge color
        let statusClass = "badge-danger";
        let statusText = "Low";
        if (student.percentage >= 75) {
            statusClass = "badge-success"; 
            statusText = "Good";
        } else if (student.percentage >= 60) {
            statusClass = "badge-warning";
            statusText = "Average";
        }

        tr.innerHTML = `
            <td>
                <div style="font-weight:bold;">${student.name || "Unknown"}</div>
                <div style="font-size:0.85em; color:#888;">${student.student_id}</div>
            </td>
            <td>${student.present_count}</td>
            <td>${student.total_classes}</td>
            <td>${student.percentage}%</td>
            <td><span class="badge ${statusClass}">${statusText}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

// --- 4. Event Listeners ---
document.getElementById('takeAttendanceBtn')?.addEventListener('click', () => {
    // Save class name so live page knows what to show
    const currentClass = document.getElementById('currentClassName')?.innerText;
    if (currentClass) {
        localStorage.setItem("active_class_name", currentClass);
    }
    window.location.href = "live.html"; 
});

document.getElementById('enrollNavBtn')?.addEventListener('click', () => {
    window.location.href = "enroll.html";
});

document.getElementById('logoutBtn')?.addEventListener('click', () => {
    localStorage.removeItem("teacher_logged_in");
    window.location.href = "login.html";
});

// --- 5. Initialization ---
document.addEventListener("DOMContentLoaded", () => {
    // Load immediately
    loadCurrentPeriod();
    loadStudentSummary();
    
    // Auto-refresh data every 5 seconds
    if (autoRefreshTimer) clearInterval(autoRefreshTimer);
    autoRefreshTimer = setInterval(() => {
        loadCurrentPeriod();
        loadStudentSummary();
    }, 5000);
});