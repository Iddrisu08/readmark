"""
ReadMark — Database Models
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Text, Boolean, DateTime, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from database import Base


def generate_uuid():
    return str(uuid.uuid4())


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)  # Null for OAuth-only users
    name = Column(String(255), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    auth_provider = Column(String(50), default="email")  # "email" or "google"
    google_id = Column(String(255), unique=True, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    items = relationship("ReadingItem", back_populates="user", cascade="all, delete-orphan")


class ReadingItem(Base):
    __tablename__ = "reading_items"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    url = Column(String(2000), nullable=True)
    normalized_url = Column(String(2000), nullable=True, index=True)
    title = Column(String(500), nullable=False, default="Untitled")
    category = Column(String(50), default="Article")
    notes = Column(Text, nullable=True)
    status = Column(String(20), default="unread", index=True)  # unread, reading, done
    scroll_position = Column(Integer, default=0)  # 0-100 percentage
    estimated_read_time = Column(Integer, default=0)  # minutes
    favicon = Column(String(500), nullable=True)
    summary = Column(Text, nullable=True)  # AI-generated summary (Claude)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="items")

    __table_args__ = (
        Index("ix_user_normalized_url", "user_id", "normalized_url"),
        Index("ix_user_status", "user_id", "status"),
    )


class AIUsage(Base):
    """One row per AI call — powers usage/cost monitoring (FinOps)."""
    __tablename__ = "ai_usage"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(String(36), nullable=True)
    provider = Column(String(50), nullable=False)   # e.g. "anthropic"
    model = Column(String(100), nullable=False)
    operation = Column(String(50), default="summarize")
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)
