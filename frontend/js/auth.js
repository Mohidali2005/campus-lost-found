// frontend/js/auth.js
// ─────────────────────────────────────────────────────────────────────────────
// Authentication utilities shared across all pages.
//
// Every HTML page loads this file so it can:
//   1. Show correct nav links (Login/Register vs username + Logout)
//   2. Know who is logged in when posting items or messages
//   3. Provide helper functions for formatting and safe HTML rendering
//
// This file depends on api.js being loaded first (it uses apiGet, getToken etc.)
// ─────────────────────────────────────────────────────────────────────────────

// Cache the current user in memory so we don't call /auth/me multiple times
// per page load. Reset to null on logout.
let _currentUser = null;


// ── getCurrentUser ────────────────────────────────────────────────────────────

// Fetches the logged-in user from the backend and caches the result.
// Returns a User object { id, name, email, student_id, is_admin, created_at }
// or null if the user is not logged in or the token has expired.
async function getCurrentUser() {
    if (_currentUser) return _currentUser;      // already fetched this page load — reuse it
    if (!isLoggedIn()) return null;             // no token at all — skip the network request

    try {
        _currentUser = await apiGet("/auth/me");
        return _currentUser;
    } catch {
        // Token exists but is invalid or expired.
        // Clean it up so the user isn't stuck in a broken state.
        removeToken();
        return null;
    }
}


// ── logout ────────────────────────────────────────────────────────────────────

// Removes the JWT, clears the in-memory user cache, and redirects to homepage.
// Called when the user clicks the Logout button in the nav.
function logout() {
    removeToken();
    _currentUser = null;
    window.location.href = "index.html";
}


// ── updateNav ─────────────────────────────────────────────────────────────────

// Fills the #nav-links div with the appropriate links based on auth state.
// Call this once on every page inside DOMContentLoaded.
//
// Logged in  → "Hello, <FirstName>"  +  Logout button
// Logged out → Post Item  |  Login  |  Register button
async function updateNav() {
    const navLinks = document.getElementById("nav-links");
    if (!navLinks) return;  // page doesn't have a nav — nothing to do

    const user = await getCurrentUser();

    if (user) {
        // Extract just the first name so the nav doesn't overflow
        const firstName = escapeHtml(user.name.split(" ")[0]);

        // Logged-in nav: Post Item | Dashboard | Hello, Name | Logout
        // Dashboard link is only shown to registered users — guests have no dashboard
        navLinks.innerHTML = `
            <a href="post.html" class="btn-nav btn">+ Post Item</a>
            <a href="dashboard.html" style="color:rgba(255,255,255,0.9); font-size:0.9rem;">Dashboard</a>
            <span style="color:rgba(255,255,255,0.8); font-size:0.9rem;">
                Hello, ${firstName}
            </span>
            <button
                onclick="logout()"
                class="btn btn-sm"
                style="background:rgba(255,255,255,0.15); color:white; border:1px solid rgba(255,255,255,0.3);">
                Logout
            </button>
        `;
    } else {
        navLinks.innerHTML = `
            <a href="post.html">Post Item</a>
            <a href="login.html">Login</a>
            <a href="register.html" class="btn-nav btn">Register</a>
        `;
    }
}


// ── escapeHtml ────────────────────────────────────────────────────────────────

// Escapes HTML characters in a string to prevent XSS (Cross-Site Scripting).
// XSS is when an attacker injects malicious HTML/JS into your page through
// user-provided content (names, descriptions, messages, etc.)
//
// Example:
//   escapeHtml('<script>alert("hack")</script>')
//   → '&lt;script&gt;alert("hack")&lt;/script&gt;'
//
// Always call this before inserting user data into innerHTML.
function escapeHtml(text) {
    if (text === null || text === undefined) return "";
    const div = document.createElement("div");
    div.textContent = text;  // textContent treats the value as plain text, auto-escaping HTML
    return div.innerHTML;    // innerHTML gives us the escaped string back
}


// ── formatDate ────────────────────────────────────────────────────────────────

// Converts a raw "YYYY-MM-DD" or ISO datetime string into a readable date.
// "2026-05-25" → "May 25, 2026"
// "2026-05-25T19:11:27" → "May 25, 2026"
function formatDate(str) {
    if (!str) return "";
    // Parse just the date part so timezone differences don't shift the day
    const [y, m, d] = str.substring(0, 10).split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
    });
}


// ── formatDateTime ────────────────────────────────────────────────────────────

// Converts an ISO datetime string to a friendly date + time.
// "2026-05-25T19:11:27.064529" → "May 25, 2026, 7:11 PM"
// Used for message timestamps.
function formatDateTime(isoString) {
    if (!isoString) return "";
    return new Date(isoString).toLocaleString("en-US", {
        year:   "numeric",
        month:  "short",
        day:    "numeric",
        hour:   "numeric",
        minute: "2-digit",
    });
}


// ── showAlert ─────────────────────────────────────────────────────────────────

// Renders a coloured alert inside a container element by its ID.
// type: "error" | "success" | "info"
// The message is HTML-escaped to prevent XSS.
function showAlert(containerId, message, type = "error") {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = `<div class="alert alert-${type}">${escapeHtml(message)}</div>`;
}


// ── clearAlert ────────────────────────────────────────────────────────────────

// Clears any alert currently shown in the given container.
function clearAlert(containerId) {
    const el = document.getElementById(containerId);
    if (el) el.innerHTML = "";
}
