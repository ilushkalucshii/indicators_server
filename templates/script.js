let socket;
let userGroup = 'default';

document.addEventListener("DOMContentLoaded", () => {
    const savedUsername = sessionStorage.getItem("username");
    if (savedUsername) {
        showDashboard(savedUsername);
    } else {
        showLoginForm();
    }
});

function showLoginForm() {
    document.getElementById("login-form").classList.remove("hidden");
    document.getElementById("register-form").classList.add("hidden");
    document.getElementById("dashboard").classList.add("hidden");
}

function showRegisterForm() {
    document.getElementById("login-form").classList.add("hidden");
    document.getElementById("register-form").classList.remove("hidden");
}

function showDashboard(username) {
    document.getElementById("user-name").innerText = username;
    document.getElementById("auth-section").classList.add("hidden");
    document.getElementById("dashboard").classList.remove("hidden");

    connectSocket(username);
}

function login() {
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;

    fetch('http://localhost:5000/login', {
        method: 'POST',
        body: new URLSearchParams({ username, password })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            sessionStorage.setItem("username", username);
            showDashboard(username);
        } else {
            alert("Login failed. Please try again.");
        }
    });
}

function register() {
    const username = document.getElementById("new-username").value;
    const password = document.getElementById("new-password").value;
    const confirmPassword = document.getElementById("confirm-password").value;

    if (password !== confirmPassword) {
        alert("Passwords do not match.");
        return;
    }

    fetch('http://localhost:5000/register', {
        method: 'POST',
        body: new URLSearchParams({ username, password })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            sessionStorage.setItem("username", username);
            showDashboard(username);
        } else {
            alert("Registration failed. Try again.");
        }
    });
}

function logout() {
    sessionStorage.clear();
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.close();
    }
    window.location.reload();
}

function connectSocket(username) {
    // Use wss:// if your site is HTTPS, otherwise ws://
    socket = new WebSocket(`ws://${window.location.hostname}:5001`);

    socket.onopen = () => {
        console.log("🟢 WebSocket connected.");
        const initPayload = {
            type: 'client_ready',
            user_group: username
        };
        socket.send(JSON.stringify(initPayload));
    };

    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            console.log("📥 Received data:", data);
            
            // Handle different message types
            if (data.type === 'level_analysis') {
                displayData(data);
            }
            // Add more message type handlers as needed
            
        } catch (e) {
            console.error("❌ Error parsing message:", e);
        }
    };

    socket.onerror = (error) => {
        console.error("🚨 WebSocket error:", error);
    };

    socket.onclose = () => {
        console.warn("🔴 WebSocket disconnected. Attempting to reconnect...");
        setTimeout(() => connectSocket(username), 3000);  // Reconnect after 3 seconds
    };
}

function displayData(data) {
    const consoleDiv = document.getElementById("data-console");
    const timestamp = new Date(data.timestamp * 1000).toLocaleString();
    let output = `Timestamp: ${timestamp}\nLevels:\n`;

    for (const [level, value] of Object.entries(data.levels)) {
        output += `  - ${level}: ${value}\n`;
    }

    consoleDiv.textContent = output;
}
