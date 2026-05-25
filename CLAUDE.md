# Campus Lost & Found — LUMS

Campus bulletin-board style web app for **LUMS (Lahore University of Management Sciences)** students to post lost/found items with photos. No account required to post or message — guest access is a first-class feature. Registered accounts add a dashboard and AI match alerts. Built with static HTML/JS frontend + FastAPI backend.

## Commands

**Always use `py -3.11`** — Python 3.7 is also installed on this machine and is the system default. Using plain `python` or `pip` will target 3.7 and fail.

```bash
# Start backend (must run from project root, not from backend/)
py -3.11 -m uvicorn backend.main:app --reload

# Install dependencies
py -3.11 -m pip install -r requirements.txt

# API docs (auto-generated, available when server is running)
http://127.0.0.1:8000/docs
```

Frontend is plain static HTML — open `frontend/index.html` directly in a browser or serve with any static file server.

## Architecture

### Request flow
`frontend JS (api.js fetch wrapper)` → `FastAPI router` → `SQLAlchemy ORM (SQLite)` or `matching_service.py (CLIP)`

### Backend patterns

**Imports use the `backend.` package prefix** — all modules import as `from backend.config import settings`, never relative imports. This is why the server must start from the project root.

**No DB migration tool** — `create_tables()` in `database.py` is called via the FastAPI `lifespan` hook on every startup. Adding a new column requires dropping and recreating the DB file (`campus_lostfound.db` at project root) during development.

**Two auth dependency variants** in `dependencies.py`:
- `get_current_user()` — strict, throws 401 if no token; used on protected routes (post item, dashboard, delete)
- `get_optional_user()` — returns `User | None`; used on all public routes so they work with or without a token
- Both use `HTTPBearer` (not `OAuth2PasswordBearer`) — shows a simple token paste field in Swagger UI

**Auth router is wired** — `main.py` includes `auth_router` at `/auth`. Future routers added via `app.include_router(...)`.

**LUMS-only registration** — `_require_lums_email()` in `routers/auth.py` rejects any email that doesn't end in `@lums.edu.pk`.

### Guest/registered duality
Both `Item` and `Message` models have a nullable `user_id`. The invariant: either `user_id` is set (registered user) or `poster_name` + `poster_contact` are the only identity (guest). This applies equally to messages (`sender_name` always set, `user_id` nullable). No separate guest table exists.

### AI matching
`Item.embedding` is a `Text` column storing a JSON-encoded `list[float]` (512-dim CLIP vector). It is computed once when an item is first posted and never recomputed. `matching_service.py` (Phase 6) loads the CLIP model once at module import time and reuses it for every request.

### Static file serving
Uploaded photos are saved to `backend/uploads/` and served by FastAPI's `StaticFiles` mount at `/uploads`. The `uploads/` directory is gitignored (only `.gitkeep` is committed).

## Build phases

| Phase | Description | Status |
|---|---|---|
| 1 | Skeleton: models, DB, health check | ✅ Done |
| 2 | Auth: register, login, JWT | ✅ Done |
| 3 | Item posting with photo upload | ✅ Done |
| 4 | Browse & search (backend) | ✅ Done |
| 5 | Public message threads (backend) | ✅ Done |
| 6 | Full frontend — HTML/CSS/JS | ✅ Done |
| 7 | CLIP image matching (backend) | ✅ Done |
| 8 | Registered user dashboard (backend + frontend) | ✅ Done |
| 9 | Polish & admin panel | ✅ Done |

Work one phase at a time. After each phase:
1. Update the status table above to ✅ Done
2. Update the Phase completion notes section below with what was built
3. `git add` only the files changed in that phase
4. `git commit` with a message in the format: `Phase N: short description\n\n- bullet list of changes`
5. `git push origin main`

Do NOT batch multiple phases into one commit. Each phase gets its own commit.

## Phase completion notes

### Phase 1 — Skeleton
- Created `backend/models.py` (User, Item, Message, Match ORM models)
- Created `backend/database.py` (SQLite engine, SessionLocal, create_tables)
- Created `backend/config.py` (Pydantic settings from .env)
- Created `backend/schemas.py` (all Pydantic request/response schemas)
- Created `backend/main.py` (FastAPI app, CORS, /uploads static mount, /health endpoint)

### Phase 2 — Auth
- Created `backend/dependencies.py`:
  - `get_db()` — yields SQLAlchemy session per request
  - `get_current_user()` — strict JWT auth, raises 401 if token missing/invalid
  - `get_optional_user()` — returns `User | None`, never raises 401 (for guest-friendly routes)
  - Uses `HTTPBearer` (not `OAuth2PasswordBearer`) — Swagger UI shows a paste field
- Created `backend/routers/auth.py`:
  - `POST /auth/register` — LUMS email gate (@lums.edu.pk only), bcrypt password hash, 201 Created
  - `POST /auth/login` — verifies credentials, returns JWT (7-day expiry)
  - `GET /auth/me` — returns current user profile from token
- Wired `auth_router` into `main.py`
- **Known fix**: `bcrypt` must be pinned to `==4.0.1` — version 5+ breaks passlib's internal self-test. Already pinned in `requirements.txt`.
- **Known fix**: `pydantic[email]` must be installed for `EmailStr` to work. Already in `requirements.txt`.

### Phase 3 — Item posting ← most recently completed
- Created `backend/routers/items.py`:
  - `POST /items` — multipart/form-data (text fields + optional photo). Works for guests and registered users via `get_optional_user`. Saves photo to `backend/uploads/<uuid>.<ext>`, stores `/uploads/<filename>` path in `Item.image_path`.
  - `GET /items/{id}` — returns a single item by ID, public (no auth needed), 404 if not found
  - `_save_photo()` helper validates MIME type (jpeg/png/gif/webp), enforces 5 MB limit, generates UUID filename to avoid collisions
- Wired `items_router` into `main.py`
- NOTE: Cannot use Pydantic model for POST /items because FastAPI doesn't allow mixing UploadFile with a JSON body — must use `Form(...)` for every field individually

### Phase 4 — Browse & search ← most recently completed
- Added `GET /items` to `backend/routers/items.py` (Endpoint 2, before `GET /items/{id}`)
- Query params: `type` (lost/found), `category`, `q` (keyword search title+description), `status` (default: open), `page` (default: 1), `page_size` (default: 20, max: 100)
- Returns `ItemListOut` (items + total + page + pages)
- Keyword search uses `.ilike()` for case-insensitive LIKE on both title and description
- Results sorted newest-first via `.order_by(Item.created_at.desc())`
- `pages` uses `math.ceil`, minimum 1 so frontend always shows "Page 1 of 1" even when empty

### Phase 5 — Public message threads ← most recently completed
- Created `backend/routers/messages.py`:
  - `POST /items/{item_id}/messages` — guest or registered. Guests must supply `sender_name`; registered users get their account name automatically (body `sender_name` ignored to prevent spoofing). Returns 404 if item doesn't exist.
  - `GET /items/{item_id}/messages` — returns all messages oldest-first, public, 404 if item missing
  - `_get_item_or_404()` helper shared by both endpoints
- Wired `messages_router` into `main.py`

### Phase 6 — Full frontend ← most recently completed
Files created:
- `frontend/css/style.css` — LUMS green theme, cards grid, badges, forms, spinner, responsive
- `frontend/js/api.js` — API_BASE const, getToken/saveToken/removeToken, apiGet/apiPost/apiPostForm
- `frontend/js/auth.js` — getCurrentUser (cached), logout, updateNav, escapeHtml, formatDate, formatDateTime, showAlert, clearAlert
- `frontend/js/app.js` — loadItems, renderItemCard, renderPagination, changePage, handleSearch
- `frontend/js/item.js` — loadItem, renderItem, loadMessages, renderMessages, setupMessageForm, handlePostMessage
- `frontend/js/post.js` — toggleDropOff, handleSubmit (FormData → apiPostForm), pre-fills name for logged-in users
- `frontend/index.html` — homepage with search + type + category filters, item cards grid, pagination
- `frontend/item.html` — item detail (photo + info grid), message thread, post-message form
- `frontend/post.html` — post item form (lost/found toggle, photo upload, drop-off field shown for found only)
- `frontend/login.html` — login form, saves token to localStorage on success
- `frontend/register.html` — register form, LUMS email enforced by backend
Key decisions:
- Token stored in localStorage under key "lums_token"
- escapeHtml() used on ALL user content before innerHTML to prevent XSS
- apiPostForm() does NOT set Content-Type — browser sets it with correct boundary for multipart
- Open index.html directly in browser — no server needed for frontend

### Phase 7 — CLIP image matching (backend) ← most recently completed
Files created:
- `backend/services/__init__.py` — empty package marker
- `backend/services/matching_service.py` — lazy-loads CLIP (`openai/clip-vit-base-patch32`) on first use
  - `encode_image(disk_path)` → normalised 512-dim float list, or None on failure
  - `encode_text(text)` → normalised 512-dim float list (fallback for photo-less items)
  - `compute_and_store_embedding(item, db)` — picks image or text path, saves JSON to `Item.embedding`
  - `find_and_save_matches(item, db)` — compares against all opposite-type items with embeddings, saves `Match` rows above `clip_threshold` (0.70), skips duplicates

Changes to existing files:
- `backend/routers/items.py`:
  - Added import of `matching_service` and `Match`, `MatchOut`
  - `POST /items` now calls `compute_and_store_embedding` then `find_and_save_matches` after saving (wrapped in try/except — CLIP failure never breaks posting)
  - Added `GET /items/{item_id}/matches` — returns `list[MatchOut]` sorted by score desc; `matched_item` is the OTHER item in each pair

Key decisions:
- Lazy model loading: CLIP is loaded on first embedding request, not at server startup — keeps boot time fast
- Text fallback: items without photos get a text embedding from title + description so they still participate in matching
- Non-fatal: any CLIP error is logged as a warning; the item post always succeeds
- Cosine similarity via dot product of L2-normalised vectors (no numpy needed for 512-dim)

### Phase 8 — Registered user dashboard (backend + frontend) ← most recently completed
Files created:
- `backend/routers/dashboard.py`: `GET /dashboard` (protected — 401 for guests)
  - Fetches all items posted by the logged-in user (newest first)
  - For each item, fetches pre-computed CLIP matches from the matches table
  - Returns `DashboardOut` { user, items: DashboardItemOut[], total_items, total_matches }
- `frontend/dashboard.html`: dashboard page
  - Redirects to login.html if not logged in
  - Stats bar: items posted + AI matches found
  - One card per item: photo thumbnail, type/status badges, category/location/date
  - Each card has a "Possible AI Matches" section with a horizontal scroll row of match mini-cards
  - Match mini-cards show title, category, location, type badge, and similarity % score

Changes to existing files:
- `backend/schemas.py`: added `DashboardItemOut` (item + matches) and `DashboardOut` (user + items + counts)
- `backend/main.py`: wired in `dashboard_router` at `/dashboard`
- `frontend/js/auth.js`: added "Dashboard" link in nav for logged-in users

### Phase 9 — Polish & admin panel ← most recently completed
Files created:
- `backend/routers/admin.py`: admin-only endpoints (403 for non-admins)
  - `GET /admin/users` — list all registered users, newest first
  - `GET /admin/items` — list all items with no status filter (shows resolved too), paginated
- `frontend/admin.html`: admin panel with two tab panels
  - Stats bar: total users, total items, open count, resolved count
  - Users tab: table of all accounts (name, email, student_id, is_admin, joined)
  - Items tab: table of all items with inline Delete button per row

Changes to existing files:
- `backend/dependencies.py`: added `get_admin_user` — checks valid JWT AND `is_admin=True` (raises 403 if not)
- `backend/routers/items.py`: added two Phase 9 endpoints
  - `DELETE /items/{id}` — owner or admin; deletes matches manually (no cascade), messages cascade automatically; returns 204
  - `PATCH /items/{id}/resolve` — owner or admin; sets status=resolved; returns updated ItemOut
- `backend/main.py`: wired `admin_router`
- `frontend/js/api.js`: added `apiRequest(method, path, data)` — generic DELETE/PATCH helper; returns null for 204 responses
- `frontend/js/auth.js`: added Admin nav link (visible only when `user.is_admin=true`)
- `frontend/js/item.js`: added `addOwnerActions(item)` — injects Delete + Resolve buttons on item detail page for owners and admins

### Post-launch fixes & improvements

**CLIP preloading at server startup**
- Added `preload_model()` to `backend/services/matching_service.py`
- Called in `main.py` lifespan via `await asyncio.to_thread(matching_service.preload_model)`
- CLIP now loads when the server starts so the first item post is instant for all users
- Wait for `"CLIP model loaded successfully."` in server logs before sending users to the site

**Sidebar navigation**
- Added a fixed 210px left sidebar to all main pages (`index.html`, `item.html`, `post.html`, `dashboard.html`, `admin.html`)
- Sidebar filled by `updateSidebar()` in `auth.js`, called automatically at end of `updateNav()`
- Sidebar links use `?section=` URL param (see section-based filtering below)
- Mobile: sidebar hidden by default, `☰` hamburger button in navbar toggles it as an overlay
- Active page highlighted with green left border via `.sidebar-link.active` class
- `body.has-sidebar` shifts `.page-content` right by 210px on desktop

**Section-based item filtering (replaces type/status dropdowns)**
- Old approach: `?type=lost` / `?type=found` URL params with separate status dropdown
- New approach: `?section=lost` / `?section=found` — sections defined by LOGICAL state, not DB field:
  - `section=lost`  → `GET /items?type=lost&status=open` (still missing)
  - `section=found` → two parallel API calls merged: `GET /items?type=found` + `GET /items?type=lost&status=resolved`
  - No section (All Items) → `GET /items` (everything)
- Type and status dropdowns removed from the search bar — sidebar handles navigation
- Search bar now has keyword + category only

**Badge logic redesign — 3 states**
- Old (2-state): `type=found OR status=resolved` → green FOUND; else red LOST — misleading because a resolved lost item showed as "FOUND" implying a drop-off point
- New (3-state), priority order:
  - `status=resolved` (any type)       → gray **RESOLVED** badge (`.badge-resolved`) — case closed
  - `type=found` + `status=open`       → green **FOUND** badge — item waiting at drop-off
  - `type=lost` + `status=open`        → red **LOST** badge — still missing
- Applied consistently in both `app.js` `renderItemCard()` and `item.js` `renderItem()`
- Resolved cards are dimmed (`.card-resolved` CSS class) so open items stand out
- `.badge-resolved` CSS class was already defined in `style.css` — no CSS changes needed

**Email notifications on new message**
- When someone messages a registered user's item, the poster gets an email at their `@lums.edu.pk` address
- Uses Python stdlib `smtplib` — no new pip packages; recommended sender: Brevo free SMTP (brevo.com)
- New file: `backend/services/email_service.py` — `send_message_notification()` function
- Fires as a FastAPI `BackgroundTask` in `messages.py` `create_message()` — API response is never delayed
- Skipped silently when: poster is a guest (no email), sender == poster, or SMTP not configured in `.env`
- New config fields in `backend/config.py`: `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `smtp_from`
- `.env.example` updated with Brevo SMTP template

**Backend `GET /items` default status changed**
- Was: `status: Optional[ItemStatus] = ItemStatus.open` (hid resolved items by default)
- Now: `status: Optional[ItemStatus] = None` (shows all items when no status param sent)
- Frontend controls what it shows by always sending explicit params

**Breadcrumb on item detail**
- `item.js renderItem()` fills `#breadcrumb` with `Home › Lost/Found Items › Item Title`
- Each crumb is a clickable link back to that filtered section
- Back button styled as `.btn-back` (pill with border) instead of plain text link

## Key data notes
- `Item.date_occurred` is stored as a plain `String` (`YYYY-MM-DD`), not a `Date` column
- `Item.category` is a free-form string — no enum enforcement at DB level
- `Item.drop_off_location` is only meaningful for `type = "found"` items
- JWT tokens expire after 7 days (`access_token_expire_minutes = 60 * 24 * 7` in `config.py`)
- All LUMS student emails follow the pattern `<student_id>@lums.edu.pk`

## Environment
Copy `.env.example` to `.env` before first run. The DB file (`campus_lostfound.db`) is created automatically at the project root on first startup.
