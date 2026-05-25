// frontend/js/app.js
// ─────────────────────────────────────────────────────────────────────────────
// Homepage logic — loads, filters, and paginates items based on the active
// "section" chosen from the sidebar.
//
// Sections (set via ?section= in the URL by sidebar links):
//   section=lost  → Lost Items  = type:lost AND status:open (still missing)
//   section=found → Found Items = type:found OR (type:lost AND status:resolved)
//   (none)        → All Items   = every item regardless of type or status
//
// Badge rules (what colour badge each card gets):
//   • type=found                        → green FOUND badge
//   • type=lost  + status=open          → red   LOST badge
//   • type=lost  + status=resolved      → green FOUND badge (it was returned!)
// ─────────────────────────────────────────────────────────────────────────────

let currentPage = 1;

// Read the active section from the URL once on load — stays constant per page.
// sidebar links set this: index.html?section=lost / index.html?section=found
const SECTION = new URLSearchParams(window.location.search).get("section"); // "lost"|"found"|null


// ── loadItems ─────────────────────────────────────────────────────────────────
//
// Decides which API call(s) to make based on the active section, then renders.
async function loadItems() {
    document.getElementById("items-container").innerHTML = '<div class="spinner"></div>';
    document.getElementById("pagination").innerHTML = "";
    document.getElementById("result-count").textContent = "";

    // Common search filters that apply in every section
    const q        = document.getElementById("search-q").value.trim();
    const category = document.getElementById("filter-category").value;

    try {
        if (SECTION === "found") {
            // ── Found Items ────────────────────────────────────────────────────
            // "Found" means either:
            //   a) someone posted a found item (type=found), OR
            //   b) a lost item was resolved/returned (type=lost, status=resolved)
            // The backend can't express this OR in one call, so we make two
            // parallel requests and merge the results.

            const buildParams = (extra) => {
                const p = new URLSearchParams({ page_size: 100, ...extra });
                if (q)        p.set("q", q);
                if (category) p.set("category", category);
                return p.toString();
            };

            const [foundData, resolvedLostData] = await Promise.all([
                apiGet(`/items?${buildParams({ type: "found" })}`),
                apiGet(`/items?${buildParams({ type: "lost", status: "resolved" })}`),
            ]);

            // Merge both result sets and sort newest-first
            const merged = [...foundData.items, ...resolvedLostData.items]
                .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

            renderItems(merged, merged.length);
            // No pagination for the merged view — we fetched up to 100 each

        } else if (SECTION === "lost") {
            // ── Lost Items ─────────────────────────────────────────────────────
            // Items that are actively lost and not yet resolved.
            const params = new URLSearchParams({
                type:      "lost",
                status:    "open",
                page:      currentPage,
                page_size: 12,
            });
            if (q)        params.set("q", q);
            if (category) params.set("category", category);

            const data = await apiGet(`/items?${params.toString()}`);
            renderItems(data.items, data.total);
            renderPagination(data.page, data.pages);

        } else {
            // ── All Items ──────────────────────────────────────────────────────
            // No section filter — show everything with appropriate badges.
            const params = new URLSearchParams({
                page:      currentPage,
                page_size: 12,
            });
            if (q)        params.set("q", q);
            if (category) params.set("category", category);

            const data = await apiGet(`/items?${params.toString()}`);
            renderItems(data.items, data.total);
            renderPagination(data.page, data.pages);
        }

    } catch (err) {
        document.getElementById("items-container").innerHTML =
            `<div class="alert alert-error" style="grid-column:1/-1">
                Could not load items: ${escapeHtml(err.message)}
             </div>`;
    }
}


// ── renderItems ───────────────────────────────────────────────────────────────
//
// Updates the page heading and renders all item cards.
function renderItems(items, total) {
    // ── Dynamic heading based on the active section ───────────────────────────
    const headingEl  = document.getElementById("page-heading");
    const subtitleEl = document.getElementById("page-subtitle");

    if (headingEl) {
        if (SECTION === "lost") {
            headingEl.textContent  = "Lost Items";
            if (subtitleEl) subtitleEl.textContent =
                "Items that are currently missing on LUMS campus.";
        } else if (SECTION === "found") {
            headingEl.textContent  = "Found Items";
            if (subtitleEl) subtitleEl.textContent =
                "Items that have been found or returned on LUMS campus.";
        } else {
            headingEl.textContent  = "Lost & Found Board";
            if (subtitleEl) subtitleEl.textContent =
                "All lost and found items across LUMS campus.";
        }
    }

    // ── Result count ──────────────────────────────────────────────────────────
    document.getElementById("result-count").textContent =
        total === 0 ? "" : total === 1 ? "1 item found" : `${total} items found`;

    if (items.length === 0) {
        const emptyMsg = SECTION === "lost"
            ? { icon: "🔍", text: "No lost items right now — great news!" }
            : SECTION === "found"
                ? { icon: "📦", text: "No found items yet. If you found something on campus, post it!" }
                : { icon: "?",  text: "No items found. Try a different search." };

        document.getElementById("items-container").innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1">
                <div style="font-size:3rem; opacity:0.3; margin-bottom:1rem">${emptyMsg.icon}</div>
                <h3>${emptyMsg.text}</h3>
                <p><a href="post.html">+ Post an item</a></p>
            </div>
        `;
        return;
    }

    document.getElementById("items-container").innerHTML =
        items.map(renderItemCard).join("");
}


// ── renderItemCard ────────────────────────────────────────────────────────────
//
// Builds the HTML for one item card.
//
// Badge logic:
//   • type=found                   → green FOUND badge  (someone found something)
//   • type=lost + status=open      → red   LOST     badge (still missing)
//   • type=found + status=open     → green FOUND    badge (claimable, has drop-off)
//   • status=resolved (any type)   → gray  RESOLVED badge (case closed, reunited with owner)
function renderItemCard(item) {
    // 3-state badge: resolved takes priority, then found vs lost
    // "FOUND" only shows when there is actually an item waiting at a drop-off point.
    // "RESOLVED" means the case is closed — the owner got their item back.
    const badgeHtml = item.status === "resolved"
        ? `<span class="badge badge-resolved">RESOLVED</span>`
        : item.type === "found"
            ? `<span class="badge badge-found">FOUND</span>`
            : `<span class="badge badge-lost">LOST</span>`;

    // Photo or emoji placeholder
    const imgSection = item.image_path
        ? `<img class="card-img"
                src="${API_BASE}${escapeHtml(item.image_path)}"
                alt="${escapeHtml(item.title)}"
                loading="lazy">`
        : `<div class="card-no-img">${isFound ? "📦" : "🔍"}</div>`;

    // Dim resolved cards slightly so open items stand out in the All Items view
    const resolvedClass = item.status === "resolved" ? " card-resolved" : "";

    return `
        <div class="card${resolvedClass}">
            ${imgSection}
            <div class="card-body">
                ${badgeHtml}
                <div class="card-title">${escapeHtml(item.title)}</div>
                <div class="card-meta">Category: ${escapeHtml(item.category)}</div>
                <div class="card-meta">Location: ${escapeHtml(item.location)}</div>
                <div class="card-meta">Date: ${escapeHtml(item.date_occurred)}</div>
            </div>
            <div class="card-footer">
                <span class="text-muted" style="font-size:0.8rem">
                    by ${escapeHtml(item.poster_name)}
                </span>
                <a href="item.html?id=${item.id}" class="btn btn-sm btn-outline">View</a>
            </div>
        </div>
    `;
}


// ── renderPagination ──────────────────────────────────────────────────────────

function renderPagination(page, pages) {
    const container = document.getElementById("pagination");
    if (pages <= 1) { container.innerHTML = ""; return; }

    const prevDisabled = page <= 1    ? "disabled" : "";
    const nextDisabled = page >= pages ? "disabled" : "";

    container.innerHTML = `
        <button class="btn btn-outline btn-sm" ${prevDisabled}
                onclick="changePage(${page - 1})">&larr; Previous</button>
        <span>Page ${page} of ${pages}</span>
        <button class="btn btn-outline btn-sm" ${nextDisabled}
                onclick="changePage(${page + 1})">Next &rarr;</button>
    `;
}


// ── changePage ────────────────────────────────────────────────────────────────

function changePage(newPage) {
    currentPage = newPage;
    loadItems();
    window.scrollTo({ top: 0, behavior: "smooth" });
}


// ── handleSearch ──────────────────────────────────────────────────────────────

function handleSearch(e) {
    if (e) e.preventDefault();
    currentPage = 1;
    loadItems();
}


// ── Page initialisation ───────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
    await updateNav();

    // Pre-fill keyword and category from URL params (for bookmarked searches)
    const urlParams    = new URLSearchParams(window.location.search);
    const qParam       = urlParams.get("q");
    const categoryParam = urlParams.get("category");
    if (qParam)        document.getElementById("search-q").value        = qParam;
    if (categoryParam) document.getElementById("filter-category").value = categoryParam;

    await loadItems();

    document.getElementById("search-form")
        .addEventListener("submit", handleSearch);
    document.getElementById("filter-category")
        .addEventListener("change", handleSearch);
});
