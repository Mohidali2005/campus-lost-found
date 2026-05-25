# backend/routers/messages.py
# ─────────────────────────────────────────────────────────────────────────────
# Messages router — public comment threads on lost/found item listings.
#
# Phase 5 endpoints:
#   POST /items/{item_id}/messages  — post a message on an item (guest or registered)
#   GET  /items/{item_id}/messages  — get all messages on an item (public)
#
# Design:
#   Messages are public — anyone can read them without logging in.
#   Anyone can post — guests supply a name manually, registered users get their
#   name pulled from their account automatically.
#   Messages are ordered oldest-first so the thread reads top-to-bottom like a chat.
# ─────────────────────────────────────────────────────────────────────────────

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.dependencies import get_db, get_optional_user
from backend.models import Item, Message, User
from backend.schemas import MessageCreate, MessageOut
from backend.services.email_service import send_message_notification


# ── Router setup ──────────────────────────────────────────────────────────────

# Notice the prefix includes {item_id} — this is a nested resource pattern.
# Every route in this file automatically has /items/{item_id} in its URL.
# FastAPI extracts item_id from the URL and passes it to each function.
router = APIRouter(prefix="/items/{item_id}/messages", tags=["messages"])


# ── Helper: verify item exists ────────────────────────────────────────────────

def _get_item_or_404(item_id: int, db: Session) -> Item:
    """
    Fetches an item by ID or raises HTTP 404 if it doesn't exist.

    We reuse this in both endpoints so we don't repeat the same
    query + error check twice. DRY — Don't Repeat Yourself.
    """
    item = db.query(Item).filter(Item.id == item_id).first()

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found.",
        )

    return item


# ── Endpoint 1: POST /items/{item_id}/messages — post a message ───────────────

@router.post(
    "",                                    # "" = /items/{item_id}/messages  (prefix covers the rest)
    response_model=MessageOut,             # return shape
    status_code=status.HTTP_201_CREATED,   # 201 = new resource created
    summary="Post a message on a lost/found item",
)
def create_message(
    item_id: int,                          # extracted from the URL path automatically by FastAPI
    body: MessageCreate,                   # JSON body: { "sender_name": "...", "body": "..." }
    background_tasks: BackgroundTasks,     # FastAPI injects this — used to fire email after response
    current_user: Optional[User] = Depends(get_optional_user),  # None if guest
    db: Session = Depends(get_db),
):
    """
    Posts a new message on a lost/found item listing.

    Works for both guests and registered LUMS students:

    Guest flow:
      - Must provide `sender_name` in the request body (e.g. "Ali Hassan")
      - `user_id` is stored as None in the DB
      - `sender_name` is stored exactly as provided

    Registered user flow:
      - `sender_name` in the request body is IGNORED — we use their real
        account name instead so it can't be spoofed
      - `user_id` is stored so the message is linked to their account

    Why allow guests to message?
      The whole point of Lost & Found is speed. Requiring registration before
      someone can say "I saw your wallet at the library" kills the usefulness
      of the app. Guests are first-class citizens here.

    Returns: the created MessageOut (201 Created)
    """

    # ── Step 1: Make sure the item exists ─────────────────────────────────────
    # We store the returned item object (not just check for 404) because we need
    # item.title, item.type, item.user_id, and item.user later for the email notification.
    item = _get_item_or_404(item_id, db)

    # ── Step 2: Determine the sender name ─────────────────────────────────────
    if current_user:
        # Registered user — use their real name from the database.
        # We ignore body.sender_name to prevent impersonation
        # (e.g. a student pretending to be "Admin" or someone else).
        sender_name = current_user.name
    else:
        # Guest — use the name they provided in the request body.
        # Strip whitespace so " " doesn't count as a valid name.
        sender_name = body.sender_name.strip()

        if not sender_name:
            # Guests must provide at least some name so messages aren't anonymous.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="sender_name is required for guests. Please provide your name.",
            )

    # ── Step 3: Create and save the message ───────────────────────────────────
    new_message = Message(
        item_id=item_id,                                    # link to the item being discussed
        user_id=current_user.id if current_user else None,  # None for guests
        sender_name=sender_name,                            # real name (registered) or provided name (guest)
        body=body.body.strip(),                             # the actual message text, whitespace stripped
    )

    db.add(new_message)      # stage the INSERT
    db.commit()              # execute the SQL and commit
    db.refresh(new_message)  # reload so new_message.id and created_at are populated

    # ── Step 4: Schedule email notification ───────────────────────────────────
    # We collect the owner's email NOW while the DB session is still open.
    # SQLAlchemy can lazy-load item.user within this session safely.
    # We pass only plain values to the background task — no ORM objects —
    # because the session will be closed by the time the task runs.
    owner_email = None
    if item.user_id and item.user:
        # Only notify if the sender is NOT the item's own poster.
        # (Posters sometimes message their own item to add info — no need to email themselves.)
        sender_id = current_user.id if current_user else None
        if sender_id != item.user_id:
            owner_email = item.user.email   # the poster's @lums.edu.pk address

    if owner_email:
        # add_task() queues this function to run AFTER the HTTP response is sent.
        # The student gets their 201 Created instantly; the email goes out in the background.
        background_tasks.add_task(
            send_message_notification,
            to_email=owner_email,
            item_title=item.title,
            item_id=item.id,
            item_type=item.type,
            sender_name=new_message.sender_name,
            message_preview=body.body,
        )

    return new_message  # Pydantic serializes this into MessageOut format


# ── Endpoint 2: GET /items/{item_id}/messages — get all messages ──────────────

@router.get(
    "",                        # GET /items/{item_id}/messages
    response_model=list[MessageOut],  # returns a plain list (no pagination — threads are short)
    summary="Get all messages on a lost/found item",
)
def get_messages(
    item_id: int,              # extracted from URL path
    db: Session = Depends(get_db),
):
    """
    Returns all messages posted on a specific lost/found item.

    Public endpoint — no login required. Anyone can read the message thread.

    Messages are returned oldest-first (ascending created_at) so the thread
    reads naturally top-to-bottom, like a chat or comment section.

    Returns 404 if the item doesn't exist.
    Returns an empty list [] if the item exists but has no messages yet.
    """

    # ── Step 1: Confirm the item exists ───────────────────────────────────────
    # We don't want GET /items/9999/messages to silently return []
    # when item 9999 doesn't exist — that would be misleading.
    _get_item_or_404(item_id, db)

    # ── Step 2: Fetch messages for this item ──────────────────────────────────
    # Filter by item_id, order by created_at ascending (oldest first = top of thread).
    messages = (
        db.query(Message)
        .filter(Message.item_id == item_id)       # only messages for this item
        .order_by(Message.created_at.asc())        # oldest first so thread reads top→bottom
        .all()                                     # execute and return list
    )

    return messages  # Pydantic converts each Message ORM object to MessageOut
