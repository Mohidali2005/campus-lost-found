// frontend/js/item.js
// ─────────────────────────────────────────────────────────────────────────────
// Item detail page logic — loads one item and its message thread.
//
// This file runs only on item.html.
// The item's ID comes from the URL query string: item.html?id=42
//
// Flow:
//   Page loads → read ?id from URL → loadItem(id) + loadMessages(id)
//   User submits message form → handlePostMessage() → POST /items/id/messages
//                             → loadMessages() to refresh the thread
// ─────────────────────────────────────────────────────────────────────────────


// ── Read item ID from the URL ──────────────────────────────────────────────────

// window.location.search is the "?id=42" part of the URL.
// URLSearchParams parses it into a key-value structure.
const urlParams = new URLSearchParams(window.location.search);
const ITEM_ID   = parseInt(urlParams.get("id"), 10);  // "42" → 42 (integer)


// ── loadItem ──────────────────────────────────────────────────────────────────

// Fetches the item from GET /items/{id} and renders it on the page.
async function loadItem() {
    // Guard: if there's no valid id in the URL, show an error immediately
    if (!ITEM_ID || isNaN(ITEM_ID)) {
        document.getElementById("item-detail").innerHTML =
            `<div class="alert alert-error">
                Invalid item ID. <a href="index.html">Go back home</a>
             </div>`;
        return;
    }

    try {
        const item = await apiGet(`/items/${ITEM_ID}`);
        renderItem(item);
        // After rendering, inject Delete/Resolve buttons if user is owner or admin
        await addOwnerActions(item);
    } catch (err) {
        document.getElementById("item-detail").innerHTML =
            `<div class="alert alert-error">
                ${escapeHtml(err.message)} — <a href="index.html">Go back home</a>
             </div>`;
    }
}


// ── renderItem ────────────────────────────────────────────────────────────────

// Fills the #item-detail div with the item's full details.
function renderItem(item) {
    // Update the browser tab title to match the item
    document.title = `${item.title} — LUMS Lost & Found`;

    // Update the breadcrumb trail at the top of the page with the real item title
    const breadcrumb = document.getElementById("breadcrumb");
    if (breadcrumb) {
        breadcrumb.innerHTML = `
            <a href="index.html">Home</a>
            <span class="breadcrumb-sep">›</span>
            <a href="index.html?type=${item.type}">${item.type === "lost" ? "Lost Items" : "Found Items"}</a>
            <span class="breadcrumb-sep">›</span>
            <span>${escapeHtml(item.title)}</span>
        `;
    }

    // Photo: show the real image or a styled placeholder
    const imgSection = item.image_path
        ? `<img class="item-detail-img"
                src="${API_BASE}${escapeHtml(item.image_path)}"
                alt="${escapeHtml(item.title)}">`
        : `<div class="item-detail-no-img">?</div>`;

    // Drop-off row: only meaningful for "found" items
    const dropOffRow = (item.type === "found" && item.drop_off_location)
        ? `<div class="detail-row">
               <span class="detail-label">Drop-off at</span>
               <span class="detail-value">${escapeHtml(item.drop_off_location)}</span>
           </div>`
        : "";

    document.getElementById("item-detail").innerHTML = `
        <div class="item-detail">

            <!-- Left column: photo or placeholder -->
            <div>${imgSection}</div>

            <!-- Right column: all item details -->
            <div class="item-detail-info">
                <!-- Single badge: FOUND (green) if resolved or type=found, else LOST (red) -->
                ${(item.type === "found" || item.status === "resolved")
                    ? `<span class="badge badge-found">FOUND</span>`
                    : `<span class="badge badge-lost">LOST</span>`
                }

                <h1>${escapeHtml(item.title)}</h1>

                <div class="detail-row">
                    <span class="detail-label">Description</span>
                    <span class="detail-value">${escapeHtml(item.description)}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Category</span>
                    <span class="detail-value">${escapeHtml(item.category)}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Location</span>
                    <span class="detail-value">${escapeHtml(item.location)}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Date</span>
                    <span class="detail-value">${escapeHtml(item.date_occurred)}</span>
                </div>
                ${dropOffRow}
                <div class="detail-row">
                    <span class="detail-label">Posted by</span>
                    <span class="detail-value">${escapeHtml(item.poster_name)}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Contact</span>
                    <span class="detail-value">${escapeHtml(item.poster_contact)}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Posted on</span>
                    <span class="detail-value">${formatDate(item.created_at)}</span>
                </div>
            </div>
        </div>
    `;
}


// ── loadMessages ──────────────────────────────────────────────────────────────

// Fetches all messages for this item and renders the thread.
async function loadMessages() {
    try {
        const messages = await apiGet(`/items/${ITEM_ID}/messages`);
        renderMessages(messages);
    } catch {
        document.getElementById("messages-list").innerHTML =
            `<div class="alert alert-error">Could not load messages.</div>`;
    }
}


// ── renderMessages ────────────────────────────────────────────────────────────

// Fills the messages list with the fetched messages.
// Messages come back oldest-first from the API (ascending created_at).
function renderMessages(messages) {
    // Update the heading to show the message count
    document.getElementById("messages-count").textContent =
        messages.length === 1 ? "1 Message" : `${messages.length} Messages`;

    const container = document.getElementById("messages-list");

    if (messages.length === 0) {
        container.innerHTML = `
            <p class="text-muted" style="padding: 0.75rem 0; font-size: 0.9rem;">
                No messages yet. Be the first to leave one!
            </p>`;
        return;
    }

    // Build all message HTML at once and inject it
    container.innerHTML = messages.map(msg => `
        <div class="message-item">
            <div class="message-header">
                <span class="message-sender">${escapeHtml(msg.sender_name)}</span>
                <span class="message-time">${formatDateTime(msg.created_at)}</span>
            </div>
            <div class="message-body">${escapeHtml(msg.body)}</div>
        </div>
    `).join("");
}


// ── setupMessageForm ──────────────────────────────────────────────────────────

// Shows or hides the sender name field based on whether the user is logged in.
// Registered users: name comes from their account, no need to type it.
// Guests: must provide their name so messages aren't completely anonymous.
async function setupMessageForm() {
    const user      = await getCurrentUser();
    const nameGroup = document.getElementById("sender-name-group");

    if (user) {
        // Hide the name field — backend will use the account name
        if (nameGroup) nameGroup.classList.add("hidden");
        document.getElementById("posting-as").textContent =
            `Posting as: ${user.name}`;
    } else {
        // Show the name field for guests
        if (nameGroup) nameGroup.classList.remove("hidden");
        document.getElementById("posting-as").textContent =
            "Posting as guest — please enter your name below";
    }
}


// ── handlePostMessage ─────────────────────────────────────────────────────────

// Handles the message form submission:
// 1. Validates input
// 2. Calls POST /items/{id}/messages
// 3. Clears the form and reloads the thread on success
async function handlePostMessage(e) {
    e.preventDefault();       // stop the browser from reloading the page
    clearAlert("msg-alert");

    const bodyInput   = document.getElementById("msg-body");
    const nameInput   = document.getElementById("msg-sender-name");  // may be hidden
    const submitBtn   = document.getElementById("msg-submit");

    const body       = bodyInput.value.trim();
    const senderName = nameInput ? nameInput.value.trim() : "";

    if (!body) {
        showAlert("msg-alert", "Message cannot be empty.");
        return;
    }

    // Disable button to prevent double-submitting while the request is in flight
    submitBtn.disabled    = true;
    submitBtn.textContent = "Sending...";

    try {
        await apiPost(`/items/${ITEM_ID}/messages`, {
            sender_name: senderName,  // backend ignores this if user is logged in
            body: body,
        });

        // Clear the form on success
        bodyInput.value = "";
        if (nameInput) nameInput.value = "";

        // Reload the thread so the new message appears immediately
        await loadMessages();
        showAlert("msg-alert", "Message sent!", "success");

    } catch (err) {
        showAlert("msg-alert", err.message);
    } finally {
        // Re-enable button whether or not the request succeeded
        submitBtn.disabled    = false;
        submitBtn.textContent = "Send Message";
    }
}


// ── addOwnerActions ───────────────────────────────────────────────────────────

// If the current user is the item's owner OR an admin, inject Delete and
// Resolve buttons into the item detail panel.
// Called after renderItem() so the #item-detail div already exists.
async function addOwnerActions(item) {
    const user = await getCurrentUser();
    if (!user) return;  // guests see no action buttons

    // Only show buttons if this user posted the item, or they are an admin
    const isOwner = (item.user_id === user.id);
    if (!isOwner && !user.is_admin) return;

    // Don't show Resolve if it's already resolved
    const resolveBtn = item.status === "open"
        ? `<button id="resolve-btn" class="btn" style="background:#2d7a3a;color:white;">
               Mark as Resolved
           </button>`
        : "";

    // Inject the action bar right after the item detail grid
    const detailEl = document.getElementById("item-detail");
    const bar = document.createElement("div");
    bar.id = "owner-actions";
    bar.style.cssText = "display:flex;gap:0.75rem;margin-top:1rem;flex-wrap:wrap;";
    bar.innerHTML = `
        ${resolveBtn}
        <button id="delete-btn" class="btn" style="background:#c0392b;color:white;">
            Delete Item
        </button>
        <div id="action-alert" style="width:100%;"></div>
    `;
    detailEl.appendChild(bar);

    // ── Resolve button handler ────────────────────────────────────────────────
    const resolveBtnEl = document.getElementById("resolve-btn");
    if (resolveBtnEl) {
        resolveBtnEl.addEventListener("click", async () => {
            if (!confirm("Mark this item as resolved?")) return;
            resolveBtnEl.disabled = true;
            resolveBtnEl.textContent = "Saving...";
            try {
                // PATCH /items/{id}/resolve — returns the updated item
                await apiRequest("PATCH", `/items/${ITEM_ID}/resolve`);
                showAlert("action-alert", "Item marked as resolved!", "success");
                resolveBtnEl.remove();  // hide the button since it's now resolved
                // Update the status badge on the page without a full reload
                const statusBadge = document.querySelector(".badge-open");
                if (statusBadge) {
                    statusBadge.textContent = "RESOLVED";
                    statusBadge.className = "badge badge-resolved";
                }
            } catch (err) {
                showAlert("action-alert", err.message);
                resolveBtnEl.disabled = false;
                resolveBtnEl.textContent = "Mark as Resolved";
            }
        });
    }

    // ── Delete button handler ─────────────────────────────────────────────────
    document.getElementById("delete-btn").addEventListener("click", async () => {
        if (!confirm("Permanently delete this item? This cannot be undone.")) return;
        const deleteBtn = document.getElementById("delete-btn");
        deleteBtn.disabled = true;
        deleteBtn.textContent = "Deleting...";
        try {
            // DELETE /items/{id} — returns 204 No Content on success
            await apiRequest("DELETE", `/items/${ITEM_ID}`);
            // Redirect to homepage after deletion
            window.location.href = "index.html";
        } catch (err) {
            showAlert("action-alert", err.message);
            deleteBtn.disabled = false;
            deleteBtn.textContent = "Delete Item";
        }
    });
}


// ── Page initialisation ───────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
    await updateNav();
    await loadItem();
    await loadMessages();
    await setupMessageForm();

    // Wire up the message form submit handler
    document.getElementById("message-form")
        .addEventListener("submit", handlePostMessage);
});
