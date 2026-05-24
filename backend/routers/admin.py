# backend/routers/admin.py
# ─────────────────────────────────────────────────────────────────────────────
# Admin router — Phase 9.
# All routes here require is_admin=True on the user's account.
# A non-admin hitting any of these routes gets 403 Forbidden.
#
# Endpoints:
#   GET /admin/users        — list all registered users
#   GET /admin/items        — list ALL items regardless of status (for moderation)
# ─────────────────────────────────────────────────────────────────────────────

import math
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies import get_admin_user, get_db
from backend.models import Item, ItemStatus, ItemType, User
from backend.schemas import ItemListOut, UserOut

router = APIRouter(prefix="/admin", tags=["admin"])


# ── GET /admin/users — list all registered users ──────────────────────────────

@router.get(
    "/users",
    response_model=list[UserOut],
    summary="[Admin] List all registered users",
)
def list_all_users(
    # get_admin_user checks valid JWT AND is_admin=True; raises 401/403 otherwise
    _admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    Returns every registered user account, newest first.
    Admin only — students cannot see other students' account details.
    """
    # Order by created_at descending so the newest accounts appear first
    return db.query(User).order_by(User.created_at.desc()).all()


# ── GET /admin/items — list ALL items (no status filter) ──────────────────────

@router.get(
    "/items",
    response_model=ItemListOut,
    summary="[Admin] List all items including resolved ones",
)
def list_all_items_admin(
    # Optional filters — same as the public GET /items but status defaults to None
    # so admins see EVERYTHING (open AND resolved) by default
    type:      Optional[ItemType]   = None,
    category:  Optional[str]        = None,
    q:         Optional[str]        = None,
    status:    Optional[ItemStatus] = None,  # None = show all statuses
    page:      int = 1,
    page_size: int = 20,

    _admin: User = Depends(get_admin_user),
    db:    Session = Depends(get_db),
):
    """
    Returns all items regardless of status, with optional filters.
    Useful for moderation — admins can see resolved/hidden items too.
    Admin only.
    """
    # Clamp pagination values
    page      = max(1, page)
    page_size = max(1, min(100, page_size))

    # Start with all items — no default status filter unlike the public endpoint
    query = db.query(Item)

    # Apply optional filters
    if status is not None:
        query = query.filter(Item.status == status)
    if type is not None:
        query = query.filter(Item.type == type)
    if category:
        query = query.filter(Item.category.ilike(f"%{category}%"))
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            Item.title.ilike(pattern) | Item.description.ilike(pattern)
        )

    total  = query.count()
    pages  = max(1, math.ceil(total / page_size))
    offset = (page - 1) * page_size

    items = (
        query
        .order_by(Item.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return ItemListOut(items=items, total=total, page=page, pages=pages)
