from datetime import datetime
from pydantic import BaseModel, EmailStr
from typing import Optional
from backend.models import ItemType, ItemStatus


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    student_id: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    student_id: Optional[str]
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── Items ─────────────────────────────────────────────────────────────────────

class ItemCreate(BaseModel):
    poster_name: str
    poster_contact: str
    type: ItemType
    title: str
    description: str
    category: str
    location: str
    date_occurred: str
    drop_off_location: Optional[str] = None


class ItemOut(BaseModel):
    id: int
    user_id: Optional[int]
    poster_name: str
    poster_contact: str
    type: ItemType
    title: str
    description: str
    category: str
    location: str
    date_occurred: str
    drop_off_location: Optional[str]
    image_path: Optional[str]
    status: ItemStatus
    created_at: datetime

    class Config:
        from_attributes = True


class ItemListOut(BaseModel):
    items: list[ItemOut]
    total: int
    page: int
    pages: int


# ── Messages ──────────────────────────────────────────────────────────────────

class MessageCreate(BaseModel):
    sender_name: str
    body: str


class MessageOut(BaseModel):
    id: int
    item_id: int
    user_id: Optional[int]
    sender_name: str
    body: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Matches ───────────────────────────────────────────────────────────────────

class MatchOut(BaseModel):
    id: int
    lost_item_id: int
    found_item_id: int
    similarity_score: float
    created_at: datetime
    matched_item: ItemOut  # the "other" item in the pair

    class Config:
        from_attributes = True


# ── Dashboard (Phase 8) ───────────────────────────────────────────────────────

class DashboardItemOut(BaseModel):
    """
    One of the logged-in user's own items bundled with its AI matches.

    This is a nested structure:
      item    → the user's posting (full ItemOut)
      matches → list of MatchOut, each containing the matched opposite-type item

    For example: a lost laptop the user posted, plus any found laptops
    that CLIP thinks are similar.
    """
    item: ItemOut
    matches: list[MatchOut]  # sorted by similarity_score descending


class DashboardOut(BaseModel):
    """
    Full response for GET /dashboard.

    Contains the logged-in user's profile, all their items (each with
    AI matches), and summary counts for the UI header.
    """
    user: UserOut
    items: list[DashboardItemOut]  # all user's items, newest first
    total_items: int               # total items the user has posted
    total_matches: int             # total AI matches found across all their items
