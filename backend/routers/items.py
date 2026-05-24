# backend/routers/items.py
# ─────────────────────────────────────────────────────────────────────────────
# Items router — handles posting, browsing, searching, and retrieving items.
#
# Phase 3 endpoints:
#   POST /items                — post a new lost or found item (guest or registered)
#   GET  /items/{id}           — get a single item by its ID
#
# Phase 4 endpoints:
#   GET  /items                — browse all items with optional filters + pagination
#
# Phase 7 endpoints:
#   GET  /items/{id}/matches   — list AI-matched items for a given item
#
# Phase 9 endpoints:
#   DELETE /items/{id}         — delete an item (owner or admin only)
#   PATCH  /items/{id}/resolve — mark an item as resolved (owner or admin only)
#
# IMPORTANT — why we use Form(...) instead of a Pydantic model:
#   When a request includes a file upload, it must be sent as multipart/form-data
#   (not JSON). FastAPI does NOT allow mixing a Pydantic request body with an
#   UploadFile in the same endpoint — you have to declare every field individually
#   using Form(...). The ItemCreate schema in schemas.py is still useful as a
#   reference for what fields exist, but it can't be used directly here.
# ─────────────────────────────────────────────────────────────────────────────

import math                          # for math.ceil() when calculating total pages
import os
import uuid                          # for generating unique filenames
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.config import settings
from backend.dependencies import get_db, get_optional_user, get_current_user
from backend.models import Item, ItemType, ItemStatus, Match, User
from backend.schemas import ItemOut, ItemListOut, MatchOut

# Import the Phase 7 matching service.
# We import the functions directly so we can call them after saving a new item.
# The matching service lazy-loads the CLIP model on first use — the import
# itself is fast even if torch is installed.
from backend.services import matching_service


# ── Router setup ──────────────────────────────────────────────────────────────

# All routes in this file are prefixed with /items.
# tag="items" groups them together in the /docs Swagger UI.
router = APIRouter(prefix="/items", tags=["items"])


# ── Allowed image types ───────────────────────────────────────────────────────

# We only accept common web image formats.
# The key is the MIME type sent by the browser; the value is the file extension
# we'll use when saving the file on disk.
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

# Maximum photo size: 5 MB (in bytes).
# 1 MB = 1024 * 1024 bytes, so 5 MB = 5 * 1024 * 1024
MAX_PHOTO_SIZE = 5 * 1024 * 1024


# ── Helper: save uploaded photo to disk ──────────────────────────────────────

async def _save_photo(photo: UploadFile) -> str:
    """
    Validates and saves an uploaded photo file to backend/uploads/.

    Steps:
      1. Check the file's MIME type is an allowed image format.
      2. Read all the bytes and check the file size is under 5 MB.
      3. Generate a unique filename using UUID so two uploads never collide.
      4. Write the bytes to disk in the uploads directory.
      5. Return the URL-friendly path "/uploads/<filename>" for storing in the DB.

    Why UUID for filenames?
      If we kept the original filename ("photo.jpg"), two students uploading
      "photo.jpg" would overwrite each other's files. UUID4 generates a random
      128-bit identifier like "a3f2c1d4-..." — the chance of collision is
      astronomically small, so every file gets its own unique name.
    """

    # ── Step 1: Validate the file type ────────────────────────────────────────
    # `photo.content_type` is the MIME type the browser sent, e.g. "image/jpeg".
    # If it's not in our allowed types, we reject it immediately.
    if photo.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid file type '{photo.content_type}'. "
                f"Only JPEG, PNG, GIF, and WebP images are allowed."
            ),
        )

    # Get the correct file extension for this MIME type (e.g. ".jpg" for "image/jpeg")
    extension = ALLOWED_IMAGE_TYPES[photo.content_type]

    # ── Step 2: Read file bytes and check size ────────────────────────────────
    # `await photo.read()` reads the entire file into memory as bytes.
    # We do this BEFORE writing to disk so we can check the size first.
    file_bytes = await photo.read()

    if len(file_bytes) > MAX_PHOTO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Photo is too large. Maximum allowed size is 5 MB.",
        )

    # ── Step 3: Generate a unique filename ────────────────────────────────────
    # uuid.uuid4() generates a random unique ID like "3d6f45a5-b3e4-..."
    # We combine it with the correct extension to get e.g. "3d6f45a5.jpg"
    unique_filename = f"{uuid.uuid4()}{extension}"

    # Build the full path on disk where we'll save the file.
    # settings.upload_dir is "backend/uploads" (from config.py).
    # os.path.join combines them safely: "backend/uploads/3d6f45a5.jpg"
    file_path_on_disk = os.path.join(settings.upload_dir, unique_filename)

    # ── Step 4: Write bytes to disk ───────────────────────────────────────────
    # "wb" = write binary mode (photos are binary data, not text)
    with open(file_path_on_disk, "wb") as f:
        f.write(file_bytes)

    # ── Step 5: Return the URL path ───────────────────────────────────────────
    # We store "/uploads/3d6f45a5.jpg" in the DB.
    # The frontend can then build the full URL: http://localhost:8000/uploads/3d6f45a5.jpg
    return f"/uploads/{unique_filename}"


# ── Endpoint 1: POST /items — create a new item ───────────────────────────────

@router.post(
    "",                                     # path is just "" because router prefix is "/items"
    response_model=ItemOut,                 # return shape
    status_code=status.HTTP_201_CREATED,    # 201 = new resource created
    summary="Post a new lost or found item",
)
async def create_item(
    # ── Text fields from the multipart form ──────────────────────────────────
    # Each field is declared with Form(...) — the ... means it is required.
    # Form(None) means the field is optional (can be left blank).
    #
    # FastAPI automatically reads these from the multipart form body,
    # validates their types, and injects them as arguments.

    poster_name: str = Form(..., description="Your name, e.g. 'Ali Hassan'"),
    poster_contact: str = Form(..., description="Your phone or email so people can reach you"),
    type: ItemType = Form(..., description="'lost' if you lost something, 'found' if you found something"),
    title: str = Form(..., description="Short title, e.g. 'Blue HP Laptop'"),
    description: str = Form(..., description="Detailed description of the item"),
    category: str = Form(..., description="Category, e.g. 'Electronics', 'ID Card', 'Keys'"),
    location: str = Form(..., description="Where it was lost/found, e.g. 'LUMS Library, 2nd floor'"),
    date_occurred: str = Form(..., description="Date it was lost/found in YYYY-MM-DD format"),
    drop_off_location: Optional[str] = Form(None, description="Where the found item is being kept (found items only)"),

    # ── Optional photo upload ─────────────────────────────────────────────────
    # UploadFile is FastAPI's type for file uploads.
    # File(None) means the photo is optional — the item can be posted without a photo.
    photo: Optional[UploadFile] = File(None, description="Optional photo of the item (JPEG/PNG/GIF/WebP, max 5 MB)"),

    # ── Dependencies ──────────────────────────────────────────────────────────
    # get_optional_user returns the logged-in User OR None for guests.
    # Guests can post items — we just won't have a user_id to link.
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """
    Creates a new lost or found item posting.

    This endpoint works for BOTH guests and registered LUMS students:
      - Guests: provide poster_name and poster_contact manually. No user_id is stored.
      - Registered users: same fields, but user_id is also stored so the item
        appears in their dashboard and can be managed by them.

    The request must be sent as multipart/form-data (not JSON) because it
    may include a photo file. In the Swagger /docs UI, click "Try it out" and
    fill in the form fields — it handles the multipart encoding automatically.

    Returns the created item as ItemOut (201 Created).
    """

    # ── Step 1: Handle photo upload (if one was provided) ─────────────────────
    image_path = None  # default: no photo

    # Check if a photo was actually uploaded.
    # FastAPI sets photo.filename to "" if the user submitted the field but
    # left it empty, so we check both for None AND for an empty filename.
    if photo and photo.filename:
        # Save the photo to disk and get back the URL path to store in the DB
        image_path = await _save_photo(photo)

    # ── Step 2: Create the Item ORM object ────────────────────────────────────
    # We build the Item object with all the form fields.
    # user_id is set only if a logged-in user made the request.
    new_item = Item(
        # Link to registered user account (None for guests)
        user_id=current_user.id if current_user else None,

        # Poster identity — required for both guests and registered users
        # so there's always a human-readable name visible on the listing
        poster_name=poster_name,
        poster_contact=poster_contact,

        # Item details
        type=type,                           # ItemType.lost or ItemType.found
        title=title,
        description=description,
        category=category,
        location=location,
        date_occurred=date_occurred,         # stored as plain "YYYY-MM-DD" string
        drop_off_location=drop_off_location, # only relevant for "found" items

        # Photo — either a "/uploads/<uuid>.jpg" path or None
        image_path=image_path,

        # embedding starts as None; Step 4 below will compute and store it
        embedding=None,

        # status defaults to "open" (defined as default in the model)
    )

    # ── Step 3: Save to the database ──────────────────────────────────────────
    db.add(new_item)     # stage the INSERT
    db.commit()          # execute the SQL and commit the transaction
    db.refresh(new_item) # reload from DB so new_item.id and created_at are set

    # ── Step 4: Compute CLIP embedding and run AI matching (Phase 7) ──────────
    # This happens AFTER the item is saved so the item definitely has an ID.
    #
    # compute_and_store_embedding():
    #   - If the item has a photo → encodes the image into a 512-dim vector
    #   - If no photo → encodes the title + description as text instead
    #   - Saves the vector as JSON in Item.embedding and commits to DB
    #
    # find_and_save_matches():
    #   - Compares the new item's embedding against all items of the opposite type
    #   - Saves Match rows for any pair whose cosine similarity >= clip_threshold
    #
    # Both calls are wrapped in try/except so that if CLIP isn't installed or
    # the model download fails, the item still gets posted successfully —
    # matching just won't work until the model is available.
    try:
        matching_service.compute_and_store_embedding(new_item, db)
        matching_service.find_and_save_matches(new_item, db)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            f"CLIP matching failed for item {new_item.id} (non-fatal): {exc}"
        )

    return new_item  # Pydantic serializes this into ItemOut format


# ── Endpoint 2: GET /items — browse & search all items ───────────────────────

@router.get(
    "",                          # GET /items  (no extra path segment)
    response_model=ItemListOut,  # returns paginated list wrapper
    summary="Browse and search lost/found items",
)
def list_items(
    # ── Optional filter parameters (all come from the URL query string) ───────
    # Example URL: GET /items?type=lost&category=Electronics&q=laptop&page=1
    #
    # Query params are declared just like function arguments with a default value.
    # FastAPI reads them from the URL automatically — no extra decoration needed.

    type: Optional[ItemType] = None,
    # Filter by item type: "lost" or "found".
    # If not provided (None), both types are returned.

    category: Optional[str] = None,
    # Filter by category string, e.g. "Electronics".
    # Case-insensitive match — "electronics" matches "Electronics".

    q: Optional[str] = None,
    # Keyword search query, e.g. "blue laptop".
    # Searches inside both `title` and `description` fields.
    # Case-insensitive — "laptop" matches "Blue Laptop".

    status: Optional[ItemStatus] = ItemStatus.open,
    # Filter by item status. Defaults to "open" so resolved items
    # don't clutter the main feed. Pass status=resolved to see closed items.

    page: int = 1,
    # Which page of results to return. Page 1 = first page.
    # Must be 1 or greater.

    page_size: int = 20,
    # How many items per page. Defaults to 20.
    # Capped at 100 to prevent huge responses.

    db: Session = Depends(get_db),
):
    """
    Returns a paginated, filterable list of lost/found items. Public endpoint.

    How pagination works:
      - `page=1&page_size=20` returns items 1–20
      - `page=2&page_size=20` returns items 21–40
      - The response includes `total` (total matches) and `pages` (total page count)
        so the frontend can build a "Page 1 of 5" UI.

    How search works:
      - `q=blue laptop` searches for the string "blue laptop" inside title OR description.
      - Uses SQL LIKE with wildcards: WHERE title LIKE '%blue laptop%'
      - Case-insensitive thanks to SQLAlchemy's `.ilike()` (i = insensitive).

    Example requests:
      GET /items                          → all open items, page 1
      GET /items?type=lost                → only lost items
      GET /items?q=laptop                 → items mentioning "laptop"
      GET /items?type=found&category=Keys → found keys
      GET /items?page=2&page_size=10      → second page, 10 per page
    """

    # ── Input validation ──────────────────────────────────────────────────────
    # Clamp page to minimum 1 (page 0 or negative makes no sense)
    if page < 1:
        page = 1

    # Clamp page_size between 1 and 100 to prevent abuse
    if page_size < 1:
        page_size = 1
    if page_size > 100:
        page_size = 100

    # ── Build the base query ──────────────────────────────────────────────────
    # Start with ALL items, then chain `.filter()` calls to narrow it down.
    # SQLAlchemy doesn't hit the database until we call `.all()` or `.count()` —
    # it just builds up the SQL query object as we add filters.
    query = db.query(Item)

    # ── Apply filters one by one ──────────────────────────────────────────────

    # Filter by status (default: only "open" items)
    if status is not None:
        # Generates: WHERE items.status = 'open'
        query = query.filter(Item.status == status)

    # Filter by type (lost / found)
    if type is not None:
        # Generates: WHERE items.type = 'lost'  (or 'found')
        query = query.filter(Item.type == type)

    # Filter by category (case-insensitive)
    if category:
        # .ilike() = case-insensitive LIKE.
        # f"%{category}%" adds wildcards on both sides, so "elec" matches "Electronics".
        query = query.filter(Item.category.ilike(f"%{category}%"))

    # Keyword search across title AND description
    if q:
        # We use `|` (bitwise OR) to combine two conditions:
        # match if the search term appears in title OR in description.
        # This generates: WHERE (title LIKE '%laptop%' OR description LIKE '%laptop%')
        search_pattern = f"%{q}%"
        query = query.filter(
            Item.title.ilike(search_pattern) | Item.description.ilike(search_pattern)
        )

    # ── Count total results (before pagination) ───────────────────────────────
    # We need the total count to calculate how many pages exist.
    # `.count()` runs a SELECT COUNT(*) — fast and doesn't load all rows into memory.
    total = query.count()

    # ── Calculate pagination values ───────────────────────────────────────────
    # math.ceil(7 / 2) = 4  — always round UP so we don't lose the last partial page
    # If total is 0, pages should be 1 (not 0) so frontend shows "Page 1 of 1"
    pages = max(1, math.ceil(total / page_size))

    # Calculate how many rows to skip.
    # Page 1: skip 0.  Page 2: skip 20.  Page 3: skip 40.  etc.
    offset = (page - 1) * page_size

    # ── Fetch the actual page of items ────────────────────────────────────────
    # .order_by(Item.created_at.desc()) — newest items appear first
    # .offset(offset)                   — skip rows for previous pages
    # .limit(page_size)                 — take only this page's rows
    # .all()                            — execute the SQL and return a list
    items = (
        query
        .order_by(Item.created_at.desc())  # newest first
        .offset(offset)
        .limit(page_size)
        .all()
    )

    # ── Return the paginated response ─────────────────────────────────────────
    # ItemListOut wraps the items list with pagination metadata so the
    # frontend knows how to build "Previous / Next" or page number buttons.
    return ItemListOut(
        items=items,   # list of Item ORM objects — Pydantic converts each to ItemOut
        total=total,   # total number of matching items (across ALL pages)
        page=page,     # current page number
        pages=pages,   # total number of pages
    )


# ── Endpoint 3: GET /items/{id} — get a single item ──────────────────────────

@router.get(
    "/{item_id}",          # {item_id} is a path parameter — e.g. GET /items/42
    response_model=ItemOut,
    summary="Get a single item by ID",
)
def get_item(
    item_id: int,          # FastAPI extracts this from the URL and validates it's an int
    db: Session = Depends(get_db),
):
    """
    Returns a single lost/found item by its numeric ID.

    This is a public endpoint — no login required.
    Anyone (guest or registered student) can view any item.

    Returns 404 if no item with that ID exists.
    """

    # Query the items table for the row with this id
    item = db.query(Item).filter(Item.id == item_id).first()

    if item is None:
        # 404 Not Found — standard response when a resource doesn't exist
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found.",
        )

    return item  # Pydantic serializes this into ItemOut format


# ── Endpoint 4: GET /items/{id}/matches — AI-matched items (Phase 7) ─────────

@router.get(
    "/{item_id}/matches",           # e.g. GET /items/42/matches
    response_model=list[MatchOut],  # returns a list of MatchOut objects
    summary="Get AI-matched items for a given item",
)
def get_item_matches(
    item_id: int,
    db: Session = Depends(get_db),
):
    """
    Returns all AI-matched items for a given item ID.

    How it works:
      - When an item is posted, CLIP computes a 512-dim embedding for it.
      - That embedding is compared against all items of the OPPOSITE type
        (lost vs found). Pairs above the similarity threshold are stored
        in the matches table.
      - This endpoint fetches those stored matches and returns them with
        the matched item's full details so the frontend can display them.

    Each result includes:
      - The match record (id, scores, which items are involved)
      - matched_item: the OTHER item in the pair (not the one you requested)

    Returns an empty list if the item exists but has no matches yet.
    Returns 404 if the item does not exist at all.

    Example:
      GET /items/5/matches
      → returns all found items that are a strong CLIP match for lost item #5
    """

    # ── Verify the item exists ─────────────────────────────────────────────────
    item = db.query(Item).filter(Item.id == item_id).first()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found.",
        )

    # ── Fetch all matches involving this item ──────────────────────────────────
    # An item can appear as either the lost_item or the found_item in a match.
    # We use OR to get both cases.
    matches = (
        db.query(Match)
        .filter(
            (Match.lost_item_id == item_id) | (Match.found_item_id == item_id)
        )
        .order_by(Match.similarity_score.desc())  # best match first
        .all()
    )

    # ── Build the response list ────────────────────────────────────────────────
    # MatchOut requires a `matched_item` field — the OTHER item in the pair.
    # We can't just return the ORM objects directly because `matched_item`
    # is a computed field (not a DB column), so we build each MatchOut manually.
    result = []
    for match in matches:
        # If this item is the lost item, the "other" item is the found item
        # and vice versa. This is the item we show as "possible match".
        if match.lost_item_id == item_id:
            other_item = match.found_item   # SQLAlchemy loads via relationship
        else:
            other_item = match.lost_item    # SQLAlchemy loads via relationship

        result.append(
            MatchOut(
                id=match.id,
                lost_item_id=match.lost_item_id,
                found_item_id=match.found_item_id,
                similarity_score=match.similarity_score,
                created_at=match.created_at,
                matched_item=other_item,    # Pydantic converts this to ItemOut
            )
        )

    return result


# ── Endpoint 5: DELETE /items/{id} — delete an item (Phase 9) ────────────────

@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,  # 204 = success, no body returned
    summary="Delete an item (owner or admin only)",
)
def delete_item(
    item_id: int,
    current_user: User = Depends(get_current_user),  # must be logged in
    db: Session = Depends(get_db),
):
    """
    Permanently deletes a lost/found item and all related data.

    Who can delete:
      - The registered user who originally posted the item (owner)
      - Any admin user (is_admin=True)

    Guests cannot delete items — they have no account to verify ownership.

    What gets deleted:
      - The item itself
      - All messages on that item (cascade="all, delete-orphan" on the model)
      - All AI match records that reference this item (deleted manually below,
        since the Match model doesn't have cascade set up)

    Returns 204 No Content on success (no response body — standard for DELETE).
    Returns 404 if the item doesn't exist.
    Returns 403 if the requester is not the owner or an admin.
    """
    # ── Find the item ──────────────────────────────────────────────────────────
    item = db.query(Item).filter(Item.id == item_id).first()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found.",
        )

    # ── Check ownership or admin ───────────────────────────────────────────────
    # item.user_id is None for guest-posted items — guests can't delete via API
    # since they have no account. Only the owner or an admin can delete.
    is_owner = (item.user_id == current_user.id)
    if not is_owner and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own items.",
        )

    # ── Delete related Match rows first ───────────────────────────────────────
    # The Match model has no cascade delete, so SQLite would leave orphan rows.
    # We manually delete any match that involves this item on either side.
    db.query(Match).filter(
        (Match.lost_item_id == item_id) | (Match.found_item_id == item_id)
    ).delete(synchronize_session=False)

    # ── Delete the item (messages cascade automatically) ──────────────────────
    db.delete(item)
    db.commit()
    # Return None — FastAPI sends 204 No Content automatically


# ── Endpoint 6: PATCH /items/{id}/resolve — mark resolved (Phase 9) ──────────

@router.patch(
    "/{item_id}/resolve",
    response_model=ItemOut,
    summary="Mark an item as resolved (owner or admin only)",
)
def resolve_item(
    item_id: int,
    current_user: User = Depends(get_current_user),  # must be logged in
    db: Session = Depends(get_db),
):
    """
    Marks a lost/found item as resolved (i.e. the item was returned or claimed).

    Who can resolve:
      - The registered user who originally posted the item (owner)
      - Any admin user

    Once resolved, the item is hidden from the default browse feed (which
    filters to status=open by default) but can still be viewed directly.

    Returns the updated item with status="resolved".
    Returns 404 if the item doesn't exist.
    Returns 403 if the requester is not the owner or an admin.
    """
    # ── Find the item ──────────────────────────────────────────────────────────
    item = db.query(Item).filter(Item.id == item_id).first()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found.",
        )

    # ── Check ownership or admin ───────────────────────────────────────────────
    is_owner = (item.user_id == current_user.id)
    if not is_owner and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only resolve your own items.",
        )

    # ── Update status to resolved ──────────────────────────────────────────────
    item.status = ItemStatus.resolved
    db.commit()
    db.refresh(item)  # reload from DB so the returned object is up to date

    return item
