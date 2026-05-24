// frontend/js/api.js
// ─────────────────────────────────────────────────────────────────────────────
// Central API layer — every call to the FastAPI backend goes through this file.
//
// Why centralise API calls here?
//   Without this, every page would repeat the same fetch() boilerplate:
//   base URL, auth headers, error parsing. Having one file means one place
//   to update if the backend URL ever changes, and consistent error handling
//   across all pages.
//
// This file exposes:
//   getToken / saveToken / removeToken / isLoggedIn  — token management
//   apiGet(path)             — authenticated GET
//   apiPost(path, data)      — authenticated POST with JSON body
//   apiPostForm(path, form)  — authenticated POST with multipart/form-data (for file uploads)
// ─────────────────────────────────────────────────────────────────────────────

// The FastAPI backend URL. All API functions prepend this to the path.
// Change this one constant if the backend moves to a different port or domain.
const API_BASE = "http://127.0.0.1:8000";


// ── Token helpers ─────────────────────────────────────────────────────────────

// We store the JWT in localStorage so it survives page refreshes.
// localStorage is specific to the origin (http://127.0.0.1:8000) so it's
// not shared across different sites.
const TOKEN_KEY = "lums_token";  // the localStorage key we use

function getToken()        { return localStorage.getItem(TOKEN_KEY); }
function saveToken(token)  { localStorage.setItem(TOKEN_KEY, token); }
function removeToken()     { localStorage.removeItem(TOKEN_KEY); }

// isLoggedIn() returns true if a JWT is stored. It does NOT validate the token
// against the server — use apiGet("/auth/me") if you need server-side validation.
function isLoggedIn() {
    return !!getToken();  // !! converts truthy/falsy to boolean true/false
}


// ── Auth header ───────────────────────────────────────────────────────────────

// Returns { Authorization: "Bearer eyJ..." } if a token exists, or {} if not.
// Spread this into fetch headers: { ...authHeader(), "Content-Type": "..." }
function authHeader() {
    const token = getToken();
    return token ? { "Authorization": `Bearer ${token}` } : {};
}


// ── Error handler ─────────────────────────────────────────────────────────────

// Reads the error JSON from a failed response and throws a plain JS Error.
// FastAPI always returns { "detail": "..." } for HTTP errors.
async function handleError(response) {
    let detail = `HTTP ${response.status}`;
    try {
        const data = await response.json();
        // FastAPI wraps all errors in { detail: "..." }
        if (data.detail) detail = data.detail;
    } catch {
        // Response body wasn't JSON — use the status text instead
    }
    throw new Error(detail);
}


// ── GET ───────────────────────────────────────────────────────────────────────

// Makes a GET request to the backend. Attaches the Bearer token if logged in.
// Throws an Error with the backend's message if the response isn't 2xx.
//
// Usage:  const items = await apiGet("/items?type=lost&page=1");
async function apiGet(path) {
    const response = await fetch(`${API_BASE}${path}`, {
        headers: { ...authHeader() },
    });
    if (!response.ok) await handleError(response);
    return response.json();
}


// ── POST JSON ─────────────────────────────────────────────────────────────────

// Makes a POST request with a JSON body. Used for login, register, messages.
//
// Usage:  const result = await apiPost("/auth/login", { email, password });
async function apiPost(path, data) {
    const response = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",  // tell FastAPI to parse body as JSON
            ...authHeader(),
        },
        body: JSON.stringify(data),              // convert JS object → JSON string
    });
    if (!response.ok) await handleError(response);
    return response.json();
}


// ── Generic request (DELETE, PATCH, etc.) ────────────────────────────────────

// Sends a request with any HTTP method. Used for DELETE and PATCH endpoints.
// Returns the parsed JSON body, or null for 204 No Content responses.
//
// Usage:
//   await apiRequest("DELETE", "/items/42");
//   await apiRequest("PATCH",  "/items/42/resolve");
async function apiRequest(method, path, data = null) {
    const options = {
        method,
        headers: { ...authHeader() },
    };
    // Only attach a JSON body if data was provided (DELETE usually has no body)
    if (data !== null) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(data);
    }
    const response = await fetch(`${API_BASE}${path}`, options);
    if (!response.ok) await handleError(response);
    // 204 No Content has no body — return null instead of calling .json()
    if (response.status === 204) return null;
    return response.json();
}


// ── POST multipart form ───────────────────────────────────────────────────────

// Makes a POST request with a FormData body. Used for posting items with photos.
//
// CRITICAL: Do NOT set Content-Type manually here.
// When you pass a FormData object to fetch(), the browser automatically sets
// Content-Type to "multipart/form-data; boundary=<random>" with the correct
// boundary string. Setting it manually removes the boundary and breaks the request.
//
// Usage:
//   const form = new FormData(document.getElementById("my-form"));
//   const result = await apiPostForm("/items", form);
async function apiPostForm(path, formData) {
    const response = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { ...authHeader() },  // auth only — NO Content-Type
        body: formData,
    });
    if (!response.ok) await handleError(response);
    return response.json();
}
