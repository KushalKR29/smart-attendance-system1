const API = "http://localhost:5000";

async function loginTeacher() {
    const usernameInput = document.getElementById("username");
    const passwordInput = document.getElementById("password");
    const errorMsg = document.getElementById("login-error");
    const btn = document.querySelector("button");

    const username = usernameInput.value.trim();
    const password = passwordInput.value.trim();

    // Basic Validation
    if (!username || !password) {
        errorMsg.innerText = "Please enter both username and password.";
        return;
    }

    // UI: Disable button while loading
    btn.disabled = true;
    btn.innerText = "Signing in...";
    errorMsg.innerText = "";

    try {
        const res = await fetch(`${API}/api/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });

        const data = await res.json();

        if (res.ok && data.token) {
            // Login Success
            // 1. Save login state
            localStorage.setItem("teacher_logged_in", "true");
            localStorage.setItem("teacher_name", data.name || username);
            
            // 2. Redirect to Dashboard
            // NOTE: Make sure the file name matches exactly!
            window.location.href = "dashboard.html"; 
        } else {
            // Login Failed
            errorMsg.innerText = data.error || "Invalid credentials";
            btn.disabled = false;
            btn.innerText = "Sign In";
        }
    } catch (err) {
        console.error("Login error:", err);
        errorMsg.innerText = "Server connection failed. Is backend running?";
        btn.disabled = false;
        btn.innerText = "Sign In";
    }
}

// Allow pressing "Enter" key to submit
document.getElementById("password")?.addEventListener("keypress", function(event) {
  if (event.key === "Enter") {
    loginTeacher();
  }
});