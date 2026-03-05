
const API = "http://localhost:5000";
const trendCtx = document.getElementById("trendChart")?.getContext("2d"); // Added ?. check safety

let trendChart = null;
let autoRefreshTimer = null;

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

//  Fetches the Current/Next Period Info ---
async function loadCurrentPeriod() {
    console.log("Fetching current period...");
    const data = await safeFetchJSON(`${API}/api/teacher/current_period`);
    
    if (!data) return;

    // 1. Update Current Period
    const currentClassEl = document.querySelector('.current-period-class');
    const currentTimeEl = document.querySelector('.current-period-time');
    const currentRoomEl = document.querySelector('.current-period-room');
    const takeBtn = document.getElementById('take-attendance-btn'); // Assuming your button has this ID

    if (data.current) {
        // We use 'class_name' because that is what  backend JSON sends
        if(currentClassEl) currentClassEl.innerText = data.current.class_name;
        if(currentTimeEl) currentTimeEl.innerText = formatTime(data.current.start_time) + " - " + formatTime(data.current.end_time);
        if(currentRoomEl) currentRoomEl.innerText = data.current.room || "Room N/A";
        
        // Enable the button since there is a class
        if(takeBtn) takeBtn.disabled = false;
    } else {
        if(currentClassEl) currentClassEl.innerText = "No active period";
        if(currentTimeEl) currentTimeEl.innerText = "--";
        if(currentRoomEl) currentRoomEl.innerText = "--";
        
        // Disable the button if no class
        if(takeBtn) takeBtn.disabled = true;
    }

    // 2. Update Next Period
    const nextClassEl = document.querySelector('.next-period-class');
    const nextTimeEl = document.querySelector('.next-period-time');
    const nextRoomEl = document.querySelector('.next-period-room');

    if (data.next) {
        if(nextClassEl) nextClassEl.innerText = data.next.class_name;
        if(nextTimeEl) nextTimeEl.innerText = formatTime(data.next.start_time) + " - " + formatTime(data.next.end_time);
        if(nextRoomEl) nextRoomEl.innerText = data.next.room || "Room N/A";
    } else {
        if(nextClassEl) nextClassEl.innerText = "No upcoming classes";
        if(nextTimeEl) nextTimeEl.innerText = "--";
    }
}

function normalizeSummary(data) {
  const out = (data && data.summary) ? data.summary.slice() : [];
  const total_classes = data && data.total_classes ? data.total_classes : 0;

  return out.map(s => {
    let percentage = s.percentage;
    if ((percentage === undefined || percentage === null) && (s.present_count !== undefined)) {
      const tot = s.total_classes || total_classes || 0;
      if (tot > 0) percentage = Math.round((s.present_count / tot) * 100);
      else percentage = Math.round((s.present_count / (tot || 30)) * 100); 
    }
    return {
      student_id: s.student_id,
      name: (s.name || s.student_id),
      percentage: (percentage !== undefined && percentage !== null) ? percentage : 0,
      last_seen: s.last_seen || s.last_seen_at || s.lastSeen || null,
      present_count: s.present_count || 0,
      total_classes: s.total_classes || total_classes || 0
    };
  });
}

function renderKPI(data, students){
  document.getElementById("kpi-overall").innerText = (data.overall || 0) + "%";
  document.getElementById("kpi-total").innerText = (students.length || 0);
  const presentToday = students.filter(s => s.last_seen).length;
  document.getElementById("kpi-present").innerText = presentToday;
  const low = students.filter(s => (s.percentage||0) < 75).length;
  document.getElementById("kpi-low").innerText = low;
}

function renderStudents(students){
  const body = document.getElementById("studentsTableBody");
  if (!body) return; // Safety check
  if (!students || students.length === 0) {
    body.innerHTML = `<tr class="muted-row"><td colspan="5">No students yet</td></tr>`;
    return;
  }
  body.innerHTML = students.map(s => {
    const status = (s.percentage >= 90)? 'Excellent' : (s.percentage >= 75) ? 'Good' : 'Needs attention';
    const last = s.last_seen ? new Date(s.last_seen).toLocaleString() : '—';
    return `<tr>
      <td><div style="font-weight:600">${escapeHtml(s.name)}<div style="font-size:12px;color:var(--muted)">${escapeHtml(s.student_id)}</div></div></td>
      <td><div class="progress-bubble">${s.percentage}%</div></td>
      <td>${last}</td>
      <td><span class="badge ${s.percentage>=75 ? 'good':'warn'}">${status}</span></td>
      <td><button class="btn small outline" onclick="viewStudent('${escapeJs(s.student_id)}')">View</button></td>
    </tr>`;
  }).join("");
}

function renderTrend(dates, values){
  if (!trendCtx) return; 
  if (trendChart) { trendChart.destroy(); }
  trendChart = new Chart(trendCtx, {
    type: 'line',
    data: {
      labels: dates,
      datasets: [{
        label: 'Attendance',
        data: values,
        fill: false,
        tension: 0.2,
        borderColor: '#b892ff',
        pointBackgroundColor: '#cdb9ff',
        borderWidth: 2,
        pointRadius: 4
      }]
    },
    options: {
      scales: {
        y: { beginAtZero:true, max:100, grid: { color: 'rgba(255,255,255,0.03)'}, ticks: { color: '#bfc9e6'} },
        x: { grid: { color: 'transparent'}, ticks: { color: '#bfc9e6'} }
      },
      plugins: { legend: { display: false } }
    }
  });
}

async function loadDashboard(){
  // 1. Fetch Student Summary
  const url = `${API}/api/attendance/summary`;
  let data = await safeFetchJSON(url);
  if (!data) data = { summary: [], overall: 0 }; 

  const students = normalizeSummary(data);
  renderKPI(data, students);
  renderStudents(students);

  // 2. Fetch Current Period Info (Added this call!)
  await loadCurrentPeriod();

  // 3. Render Trend
  const dates = [];
  const values = [];
  for (let i=6;i>=0;i--){
    const d = new Date(); d.setDate(d.getDate()-i);
    dates.push(d.toLocaleDateString(undefined, {month:'short', day:'numeric'}));
    values.push(75 + Math.round(Math.random()*12 - 6));
  }
  renderTrend(dates, values);
}

function viewStudent(id){
  alert("Open detail for " + id);
}

function escapeHtml(s) {
  return String(s||'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function escapeJs(s){ return String(s||'').replace(/'/g,"\\'"); }

document.addEventListener("DOMContentLoaded", ()=>{
  loadDashboard();

  const refreshBtn = document.getElementById("refreshBtn");
  if (refreshBtn) refreshBtn.addEventListener("click", loadDashboard);

  const exportBtn = document.getElementById("exportBtn");
  if (exportBtn) exportBtn.addEventListener("click", async ()=> {
    const s = await safeFetchJSON(`${API}/api/attendance/summary`);
    const rows = (s && s.summary) ? s.summary : [];
    if (!rows || rows.length === 0) {
      alert("No data to export");
      return;
    }
    const header = Object.keys(rows[0] || {});
    const csv = [header.join(",")].concat(rows.map(r => header.map(h => `"${String(r[h]||'')}"`).join(","))).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "attendance_summary.csv"; a.click();
    URL.revokeObjectURL(url);
  });

  const logoutBtn = document.getElementById("logoutBtn");
  if (logoutBtn) logoutBtn.addEventListener("click", ()=> {
    localStorage.removeItem("teacher_logged_in");
    window.location.href = "login.html";
  });

  if (autoRefreshTimer) clearInterval(autoRefreshTimer);
  autoRefreshTimer = setInterval(loadDashboard, 5000);
});