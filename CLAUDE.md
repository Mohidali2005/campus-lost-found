# Campus Lost & Found

Campus bulletin-board style web app where students post lost/found items with photos. No account required to post or message — guest access is a first-class feature. Registered accounts add a dashboard and AI match alerts. Built with static HTML/JS frontend + FastAPI backend.

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

**Two auth dependency variants** in `dependencies.py` (not yet written, Phase 2):
- `get_current_user()` — strict, throws 401 if no token; used on protected routes (post item, dashboard, delete)
- `get_optional_user()` — returns `User | None`; used on all public routes so they work with or without a token

**Routers are not yet wired** — `main.py` currently only has the `/health` endpoint. Each phase adds a router via `app.include_router(...)`.

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
| 2 | Auth: register, login, JWT | ⬜ |
| 3 | Item posting with photo upload | ⬜ |
| 4 | Browse & search | ⬜ |
| 5 | Public message threads on items | ⬜ |
| 6 | CLIP image matching | ⬜ |
| 7 | Registered user dashboard | ⬜ |
| 8 | Polish & admin panel | ⬜ |

Work one phase at a time. After each phase: update the status above, commit with a descriptive message, and push to `https://github.com/Mohidali2005/campus-lost-found`.

## Key data notes
- `Item.date_occurred` is stored as a plain `String` (`YYYY-MM-DD`), not a `Date` column
- `Item.category` is a free-form string — no enum enforcement at DB level
- `Item.drop_off_location` is only meaningful for `type = "found"` items
- JWT tokens expire after 7 days (`access_token_expire_minutes = 60 * 24 * 7` in `config.py`)

## Environment
Copy `.env.example` to `.env` before first run. The DB file (`campus_lostfound.db`) is created automatically at the project root on first startup.
