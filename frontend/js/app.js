// frontend/js/app.js
// ─────────────────────────────────────────────────────────────────────────────
// Homepage logic — loads, filters, searches and paginates lost/found items.
//
// This file runs only on index.html.
// Flow:
//   Page loads → loadItems() → GET /items?... → renderItems() + renderPagination()
//   User types in search → handleSearch() → reset page to 1 → loadItems()
//   User clicks Next/Prev → changePage() → loadItems()
// ─────────────────────────────────────────────────────────────────────────────

// Track the current page number so Next/Prev buttons know which page to go to
let currentPage = 1;


// ── loadItems ─────────────────────────────────────────────────────────────────

// Reads the search/filter form, calls the API, and renders the results.
// This is the main function called on load and on every filter/page change.
async function loadItems() {
    // Show a spinner while we wait for the API response
    document.getElementById("items-container").innerHTML = '<div class="spinner"></div>';
    document.getElementById("pagination").innerHTML = "";
    document.getElementById("result-count").textContent = "";

    // ── Read current filter values from the form ───────────────────────────────
    const q        = document.getElementById("search-q").value.trim();
    const type     = document.getElementById("filter-type").value;      // "" | "lost" | "found"
    const category = document.getElementById("filter-category").value;  // "" | "Electronics" | ...
    const status   = document.getElementById("filter-status").value;    // "open" | "resolved" | ""

    // ── Build query string ─────────────────────────────────────────────────────
    // URLSearchParams safely encodes values — handles spaces, special chars etc.
    const params = new URLSearchParams();
    params.set("page", currentPage);
    params.set("page_size", 12);         // 12 cards fits a 4-column grid nicely
    if (q)        params.set("q", q);
    if (type)     params.set("type", type);
    if (category) params.set("category", category);
    // Only send status when a specific value is selected.
    // "" (All Items) omits the param so the backend shows every status.
    if (status)   params.set("status", status);

    try {
        // Call GET /items?page=1&page_size=12&q=laptop&type=lost etc.
        const data = await apiGet(`/items?${params.toString()}`);

        // data = { items: [...], total: 42, page: 1, pages: 4 }
        renderItems(data.items, data.total);
        renderPagination(data.page, data.pages);

    } catch (err) {
        document.getElementById("items-container").innerHTML =
            `<div class="alert alert-error" style="grid-column:1/-1">
                Could not load items: ${escapeHtml(err.message)}
             </div>`;
    }
}


// ── renderItems ───────────────────────────────────────────────────────────────

// Renders the array of item objects as a grid of cards.
function renderItems(items, total) {
    const container = document.getElementById("items-container");

    // Update the small "X items found" text above the grid
    document.getElementById("result-count").textContent =
        total === 0 ? "" : total === 1 ? "1 item found" : `${total} items found`;

    if (items.length === 0) {
        // Empty state — no items matched the filters
        container.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1">
                <div style="font-size:3rem; opacity:0.3; margin-bottom:1rem">?</div>
                <h3>No items found</h3>
                <p>Try different search terms or remove a filter</p>
            </div>
        `;
        return;
    }

    // Build each card's HTML and join into one string, then set innerHTML once.
    // This is more efficient than calling appendChild() for each card separately.
    container.innerHTML = items.map(renderItemCard).join("");
}


// ── renderItemCard ────────────────────────────────────────────────────────────

// Builds and returns the HTML string for one item card.
// We return a string (not a DOM node) because we join all cards and set innerHTML once.
function renderItemCard(item) {
    // Photo section: real image if item has one, styled placeholder if not
    const imgSection = item.image_path
        ? `<img class="card-img"
                src="${API_BASE}${escapeHtml(item.image_path)}"
                alt="${escapeHtml(item.title)}"
                loading="lazy">`    // lazy loading = only loads when card is visible
        : `<div class="card-no-img">${item.type === "lost" ? "L" : "F"}</div>`;

    return `
        <div class="card">
            ${imgSection}
            <div class="card-body">
                <span class="badge badge-${item.type}">${item.type.toUpperCase()}</span>
                <div class="card-title">${escapeHtml(item.title)}</div>
                <div class="card-meta">Category: ${escapeHtml(item.category)}</div>
                <div class="card-meta">Location: ${escapeHtml(item.location)}</div>
                <div class="card-meta">Date: ${escapeHtml(item.date_occurred)}</div>
            </div>
            <div class="card-footer">
                <span class="text-muted" style="font-size:0.8rem">
                    by ${escapeHtml(item.poster_name)}
                </span>
                <!-- Link to the item detail page, passing the id as a URL query param -->
                <a href="item.html?id=${item.id}" class="btn btn-sm btn-outline">View</a>
            </div>
        </div>
    `;
}


// ── renderPagination ──────────────────────────────────────────────────────────

// Renders Previous / "Page X of Y" / Next controls below the grid.
// Only shown when there is more than one page.
function renderPagination(page, pages) {
    const container = document.getElementById("pagination");
    if (pages <= 1) { container.innerHTML = ""; return; }

    // disabled attribute makes the button unclickable and styled as greyed out
    const prevDisabled = page <= 1    ? "disabled" : "";
    const nextDisabled = page >= pages ? "disabled" : "";

    container.innerHTML = `
        <button class="btn btn-outline btn-sm" ${prevDisabled}
                onclick="changePage(${page - 1})">
            &larr; Previous
        </button>
        <span>Page ${page} of ${pages}</span>
        <button class="btn btn-outline btn-sm" ${nextDisabled}
                onclick="changePage(${page + 1})">
            Next &rarr;
        </button>
    `;
}


// ── changePage ────────────────────────────────────────────────────────────────

// Called by the Previous/Next buttons.
// Updates currentPage and re-fetches items for the new page.
function changePage(newPage) {
    currentPage = newPage;
    loadItems();
    // Scroll smoothly back to top so the user sees the new items from the start
    window.scrollTo({ top: 0, behavior: "smooth" });
}


// ── handleSearch ──────────────────────────────────────────────────────────────

// Called when the search form is submitted or a select changes.
// Resets to page 1 so results always start from the beginning after a new search.
function handleSearch(e) {
    if (e) e.preventDefault();   // stop the form from doing a full page reload
    currentPage = 1;
    loadItems();
}


// ── Page initialisation ───────────────────────────────────────────────────────

// DOMContentLoaded fires once the HTML is parsed and all elements exist.
// Without this, our getElementById calls would return null.
document.addEventListener("DOMContentLoaded", async () => {
    // Render the nav (shows login/logout state)
    await updateNav();

    // Pre-fill the filter form from URL query params.
    // This makes sidebar links like index.html?type=found actually filter correctly —
    // without this, loadItems() reads the <select> which defaults to "" (all types).
    const urlParams = new URLSearchParams(window.location.search);
    const typeParam     = urlParams.get("type");
    const categoryParam = urlParams.get("category");
    const qParam        = urlParams.get("q");
    const statusParam   = urlParams.get("status");
    if (typeParam)                document.getElementById("filter-type").value     = typeParam;
    if (categoryParam)            document.getElementById("filter-category").value = categoryParam;
    if (qParam)                   document.getElementById("search-q").value        = qParam;
    // statusParam===null means not in URL → keep default "open" selected in the dropdown
    if (statusParam !== null)     document.getElementById("filter-status").value   = statusParam;

    // Load items immediately so the page isn't blank on arrival
    await loadItems();

    // Search form: prevent default submit + reload items
    document.getElementById("search-form")
        .addEventListener("submit", handleSearch);

    // Filter dropdowns: re-run search instantly when changed (no need to click Search)
    document.getElementById("filter-type")
        .addEventListener("change", handleSearch);
    document.getElementById("filter-category")
        .addEventListener("change", handleSearch);
    document.getElementById("filter-status")
        .addEventListener("change", handleSearch);
});
