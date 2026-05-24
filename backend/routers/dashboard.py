# backend/routers/dashboard.py
# ─────────────────────────────────────────────────────────────────────────────
# Dashboard router — Phase 8.
#
# Endpoint:
#   GET /dashboard — returns the logged-in user's items and AI matches for each
#
# This is a protected endpoint — it requires a valid JWT token.
# Guests cannot access the dashboard (they have no account to associate items with).
#
# Response shape (DashboardOut):
#   user         → the logged-in user's profile
#   items        → list of DashboardItemOut, each containing:
#                    item    → the user's own posting (ItemOut)
#                    matches → CLIP-matched opposite-type items (list[MatchOut])
#   total_items  → count of all items the user has posted
#   total_matches → count of all AI matches across all their items
# ─────────────────────────────────────────────────────────────────────────────

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.dependencies import get_current_user, get_db
from backend.models import Item, Match, User
from backend.schemas import DashboardItemOut, DashboardOut, MatchOut

# ── Router setup ──────────────────────────────────────────────────────────────

# prefix="/dashboard" means all routes here are at /dashboard/...
# tags=["dashboard"] groups them in the /docs Swagger UI
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ── GET /dashboard ─────────────────────────────────────────────────────────────

@router.get(
    "",                          # GET /dashboard  (prefix already has /dashboard)
    response_model=DashboardOut, # full response shape with nested items + matches
    summary="Get the logged-in user's dashboard — their items and AI matches",
)
def get_dashboard(
    # get_current_user raises 401 automatically if no valid token is present.
    # This makes the dashboard a protected route — only registered users can see it.
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the dashboard for the currently logged-in user.

    Protected — requires a valid JWT in the Authorization header.
    Guests (no token) receive 401 Unauthorized.

    The response contains:
      - The user's own profile
      - All items they have posted (lost or found), newest first
      - For each item: a list of AI-matched opposite-type items from Phase 7
      - Summary counts (total items, total matches) for the dashboard header

    How AI matches appear here:
      Phase 7 stored Match records in the matches table when items were posted.
      This endpoint reads those pre-computed matches — it does NOT re-run CLIP.
      So this endpoint is fast even if the user has many items.
    """

    # ── Step 1: Fetch all items posted by this user ───────────────────────────
    # Filter by user_id — only this user's own postings.
    # Order newest first so the most recent items appear at the top.
    user_items = (
        db.query(Item)
        .filter(Item.user_id == current_user.id)
        .order_by(Item.created_at.desc())
        .all()
    )

    # ── Step 2: For each item, fetch its AI matches ───────────────────────────
    # We build a list of DashboardItemOut — each wraps one item + its matches.

    dashboard_items = []   # will hold DashboardItemOut objects
    total_matches = 0      # running count across all items

    for item in user_items:
        # Query the matches table for rows where this item is either the
        # lost_item or the found_item (it can appear on either side).
        # Sort by score descending so the best match is first.
        raw_matches = (
            db.query(Match)
            .filter(
                (Match.lost_item_id == item.id) | (Match.found_item_id == item.id)
            )
            .order_by(Match.similarity_score.desc())
            .all()
        )

        # ── Build MatchOut list for this item ─────────────────────────────────
        # MatchOut requires `matched_item` — the OTHER item in the pair.
        # We determine which side our item is on, then take the other side.
        match_outs = []
        for match in raw_matches:
            # If our item is the lost item, the match is the found item, and vice versa
            if match.lost_item_id == item.id:
                other_item = match.found_item   # loaded via SQLAlchemy relationship
            else:
                other_item = match.lost_item

            match_outs.append(
                MatchOut(
                    id=match.id,
                    lost_item_id=match.lost_item_id,
                    found_item_id=match.found_item_id,
                    similarity_score=match.similarity_score,
                    created_at=match.created_at,
                    matched_item=other_item,  # Pydantic converts this to ItemOut
                )
            )

        # Wrap this item + its matches into one DashboardItemOut
        dashboard_items.append(
            DashboardItemOut(
                item=item,          # Pydantic converts Item ORM → ItemOut
                matches=match_outs,
            )
        )

        total_matches += len(match_outs)

    # ── Step 3: Return the full dashboard response ────────────────────────────
    return DashboardOut(
        user=current_user,               # Pydantic converts User ORM → UserOut
        items=dashboard_items,
        total_items=len(user_items),
        total_matches=total_matches,
    )
