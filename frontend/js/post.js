// frontend/js/post.js
// ─────────────────────────────────────────────────────────────────────────────
// Post item form logic — handles the form on post.html.
//
// The form uses multipart/form-data (not JSON) because it can include a photo.
// We call apiPostForm() from api.js which sends a FormData object.
//
// Features:
//   - Lost/Found toggle: highlights the selected type like a button group
//   - Drop-off location field: only visible when "Found" is selected
//   - Pre-fills name and contact for logged-in users from their account
//   - Redirects to the new item's detail page after successful posting
// ─────────────────────────────────────────────────────────────────────────────


// ── toggleDropOff ─────────────────────────────────────────────────────────────

// Shows or hides the "Drop-off Location" field depending on the selected type.
// Drop-off location only makes sense for Found items — it's where the finder
// is keeping the item so the owner knows where to collect it.
function toggleDropOff() {
    // Read whichever radio button (lost/found) is currently checked
    const selectedType = document.querySelector('input[name="type"]:checked')?.value;
    const dropOffGroup = document.getElementById("drop-off-group");

    if (selectedType === "found") {
        dropOffGroup.classList.remove("hidden");  // show drop-off field
    } else {
        dropOffGroup.classList.add("hidden");     // hide drop-off field
        // Clear the value so it doesn't get submitted when type is "lost"
        document.getElementById("drop_off_location").value = "";
    }
}


// ── handleSubmit ─────────────────────────────────────────────────────────────

// Handles form submission: builds FormData and sends it to POST /items.
async function handleSubmit(e) {
    e.preventDefault();  // prevent browser's default form reload behaviour

    clearAlert("form-alert");

    const submitBtn = document.getElementById("submit-btn");
    submitBtn.disabled    = true;
    submitBtn.textContent = "Posting...";

    try {
        // ── Build FormData from the form element ───────────────────────────────
        // new FormData(formElement) automatically reads all named <input>, <select>,
        // <textarea> fields, and <input type="file"> — including the binary file data.
        const form     = document.getElementById("post-form");
        const formData = new FormData(form);

        // If no photo was selected, the photo field contains an empty File object.
        // Remove it so the backend receives nothing rather than an empty file.
        const photoFile = formData.get("photo");
        if (!photoFile || photoFile.size === 0) {
            formData.delete("photo");
        }

        // Send the multipart form to POST /items
        // apiPostForm() in api.js handles the Authorization header + fetch
        const newItem = await apiPostForm("/items", formData);

        // Success — tell the user and redirect to the new item's page
        showAlert("form-alert", "Item posted successfully! Taking you there...", "success");
        setTimeout(() => {
            window.location.href = `item.html?id=${newItem.id}`;
        }, 1200);

    } catch (err) {
        // Show the backend's error message (e.g. "Only JPEG images allowed")
        showAlert("form-alert", err.message);
        submitBtn.disabled    = false;
        submitBtn.textContent = "Post Item";
    }
}


// ── Page initialisation ───────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
    await updateNav();

    // Set today's date as the default value for the date field
    // so users don't have to type it manually for same-day posts
    const today = new Date().toISOString().substring(0, 10);  // "2026-05-25"
    document.getElementById("date_occurred").value = today;

    // Wire up the form submit handler
    document.getElementById("post-form").addEventListener("submit", handleSubmit);

    // Show/hide drop-off field whenever the lost/found radio changes
    document.querySelectorAll('input[name="type"]').forEach(radio => {
        radio.addEventListener("change", toggleDropOff);
    });

    // Set correct initial visibility (default is "lost" so drop-off should be hidden)
    toggleDropOff();

    // Pre-fill poster name and contact for logged-in users
    // so they don't have to type them every time
    const user = await getCurrentUser();
    if (user) {
        document.getElementById("poster_name").value    = user.name;
        document.getElementById("poster_contact").value = user.email;
    }
});
