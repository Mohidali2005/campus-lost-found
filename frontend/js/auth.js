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
        // Show Admin link only if the user has is_admin=true on their account
        const adminLink = user.is_admin
            ? `<a href="admin.html" style="color:rgba(255,255,255,0.9); font-size:0.9rem;">Admin</a>`
            : "";

        navLinks.innerHTML = `
            <a href="post.html" class="btn-nav btn">+ Post Item</a>
            <a href="dashboard.html" style="color:rgba(255,255,255,0.9); font-size:0.9rem;">Dashboard</a>
            ${adminLink}
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

    // Also fill the sidebar if this page has one
    await updateSidebar();
}


// ── updateSidebar ─────────────────────────────────────────────────────────────

// Fills the #sidebar-nav element with navigation links appropriate to the
// current page and auth state.
// Called automatically at the end of updateNav() — no need to call it manually.
// Safe to call on pages that have no sidebar (#sidebar-nav won't exist → return early).
async function updateSidebar() {
    const nav = document.getElementById("sidebar-nav");
    if (!nav) return;  // page has no sidebar — nothing to do

    // getCurrentUser() is cached so this won't fire a second network request
    const user = await getCurrentUser();

    // Work out which page and filter are active so we can highlight the right link
    const page       = window.location.pathname.split("/").pop() || "index.html";
    const typeFilter = new URLSearchParams(window.location.search).get("type");

    // Returns the class string for a sidebar link — adds "active" when this link
    // matches the current page + (optionally) the query-string filter
    function linkClass(href) {
        let isActive = false;
        if (href === "index.html?type=lost")  isActive = page === "index.html" && typeFilter === "lost";
        else if (href === "index.html?type=found") isActive = page === "index.html" && typeFilter === "found";
        else if (href === "index.html")        isActive = page === "index.html" && !typeFilter;
        else                                   isActive = page === href;
        return isActive ? "sidebar-link active" : "sidebar-link";
    }

    // Auth-specific section: show account links or login/register
    const accountSection = user ? `
        <hr class="sidebar-divider">
        <div class="sidebar-section-label">My Account</div>
        <a href="dashboard.html" class="${linkClass("dashboard.html")}">📊 My Dashboard</a>
        ${user.is_admin ? `<a href="admin.html" class="${linkClass("admin.html")}">🛡️ Admin Panel</a>` : ""}
        <hr class="sidebar-divider">
        <a href="#" class="sidebar-link" onclick="logout();return false;">🚪 Logout</a>
    ` : `
        <hr class="sidebar-divider">
        <div class="sidebar-section-label">Account</div>
        <a href="login.html"    class="${linkClass("login.html")}">🔑 Login</a>
        <a href="register.html" class="${linkClass("register.html")}">📝 Register</a>
    `;

    nav.innerHTML = `
        <div class="sidebar-section-label">Browse</div>
        <a href="index.html"           class="${linkClass("index.html")}">🏠 All Items</a>
        <a href="index.html?type=lost"  class="${linkClass("index.html?type=lost")}">🔍 Lost Items</a>
        <a href="index.html?type=found" class="${linkClass("index.html?type=found")}">📦 Found Items</a>
        <hr class="sidebar-divider">
        <a href="post.html" class="${linkClass("post.html")}">➕ Post an Item</a>
        ${accountSection}
    `;
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
