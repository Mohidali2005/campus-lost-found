from datetime import datetime
from sqlalchemy import (
    Integer, String, Text, Float, Boolean,
    DateTime, ForeignKey, Enum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base
import enum


class ItemType(str, enum.Enum):
    lost = "lost"
    found = "found"


class ItemStatus(str, enum.Enum):
    open = "open"
    resolved = "resolved"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    student_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    items: Mapped[list["Item"]] = relationship("Item", back_populates="user")
    messages: Mapped[list["Message"]] = relationship("Message", back_populates="user")


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # poster — either a registered user or a guest (one of these is always set)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    poster_name: Mapped[str] = mapped_column(String(100))
    poster_contact: Mapped[str] = mapped_column(String(200))  # phone or email, their choice

    type: Mapped[ItemType] = mapped_column(Enum(ItemType))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50))
    location: Mapped[str] = mapped_column(String(200))
    date_occurred: Mapped[str] = mapped_column(String(20))  # stored as YYYY-MM-DD string
    drop_off_location: Mapped[str | None] = mapped_column(String(200), nullable=True)  # found items only

    image_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON-encoded float list

    status: Mapped[ItemStatus] = mapped_column(Enum(ItemStatus), default=ItemStatus.open)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User | None"] = relationship("User", back_populates="items")
    messages: Mapped[list["Message"]] = relationship("Message", back_populates="item", cascade="all, delete-orphan")
    lost_matches: Mapped[list["Match"]] = relationship("Match", foreign_keys="Match.lost_item_id", back_populates="lost_item")
    found_matches: Mapped[list["Match"]] = relationship("Match", foreign_keys="Match.found_item_id", back_populates="found_item")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id"))

    # sender — either a registered user or a guest
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    sender_name: Mapped[str] = mapped_column(String(100))

    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    item: Mapped["Item"] = relationship("Item", back_populates="messages")
    user: Mapped["User | None"] = relationship("User", back_populates="messages")


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lost_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id"))
    found_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id"))
    similarity_score: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lost_item: Mapped["Item"] = relationship("Item", foreign_keys=[lost_item_id], back_populates="lost_matches")
    found_item: Mapped["Item"] = relationship("Item", foreign_keys=[found_item_id], back_populates="found_matches")
