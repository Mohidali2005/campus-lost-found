# backend/main.py
# ─────────────────────────────────────────────────────────────────────────────
# FastAPI application entry point for the LUMS Campus Lost & Found app.
#
# This file wires everything together:
#   - Database setup on startup (via lifespan hook)
#   - CORS middleware (so the browser frontend can call the API)
#   - Static file serving for uploaded photos
#   - All API routers (auth, items, messages, etc. — added phase by phase)
# ─────────────────────────────────────────────────────────────────────────────

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from backend.database import create_tables
from backend.config import settings

# Import routers — each router lives in backend/routers/<name>.py
# We add more routers here as each phase is completed.
from backend.routers.auth import router as auth_router
from backend.routers.items import router as items_router
from backend.routers.messages import router as messages_router


# ── Lifespan: startup/shutdown logic ─────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Code before `yield` runs once when the server starts.
    Code after `yield` runs once when the server shuts down.

    We use this to:
      1. Create all database tables (if they don't already exist)
      2. Ensure the uploads directory exists for photo storage
    """
    create_tables()                                  # Phase 1: creates users, items, messages, matches tables
    os.makedirs(settings.upload_dir, exist_ok=True)  # create backend/uploads/ if missing
    yield
    # Nothing to clean up on shutdown for now


# ── App creation ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="LUMS Campus Lost & Found",
    description=(
        "A community bulletin board for LUMS students to report lost items "
        "and return found ones. No account required to browse or post."
    ),
    version="2.0.0",  # bumped to 2 — Phase 2 (auth) complete
    lifespan=lifespan,
)


# ── CORS middleware ───────────────────────────────────────────────────────────

# CORS (Cross-Origin Resource Sharing) allows the browser to make API requests
# from a different origin (e.g. frontend at localhost:5500 → API at localhost:8000).
# Without this middleware, the browser would block the requests with a CORS error.
#
# `allow_origins=["*"]` permits all origins — fine for development.
# In production for LUMS, this should be restricted to the actual frontend domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # allow requests from any origin (dev mode)
    allow_credentials=True,    # allow cookies and Authorization headers
    allow_methods=["*"],       # allow GET, POST, PUT, DELETE, etc.
    allow_headers=["*"],       # allow any headers (including Authorization)
)


# ── Static file serving ───────────────────────────────────────────────────────

# Makes uploaded photos available at /uploads/<filename>.
# For example: a file saved as backend/uploads/photo.jpg is accessible at
# http://localhost:8000/uploads/photo.jpg
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


# ── Routers ───────────────────────────────────────────────────────────────────

# Each phase adds its router here via app.include_router(...)
# The router's own `prefix` setting (e.g. "/auth") determines the URL path.

app.include_router(auth_router)     # Phase 2: /auth/register, /auth/login, /auth/me
app.include_router(items_router)    # Phase 3+4: POST /items, GET /items, GET /items/{id}
app.include_router(messages_router) # Phase 5: POST+GET /items/{id}/messages


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
def health_check():
    """
    Simple endpoint to verify the server is running.
    Used by deployment health checks and monitoring tools.
    Returns 200 OK as long as the server process is alive.
    """
    return {"status": "ok", "app": "LUMS Campus Lost & Found"}
