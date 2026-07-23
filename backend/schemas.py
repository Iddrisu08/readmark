"""
ReadMark — Pydantic Schemas
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


# ── Auth ──────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    credential: str  # Google ID token from frontend


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class UserResponse(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    auth_provider: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Reading Items ─────────────────────────────────────

class ItemCreate(BaseModel):
    url: Optional[str] = None
    title: str = Field(max_length=500, default="Untitled")
    category: str = Field(max_length=50, default="Article")
    notes: Optional[str] = None
    status: str = Field(default="unread", pattern="^(unread|reading|done)$")
    scroll_position: int = Field(default=0, ge=0, le=100)
    estimated_read_time: int = Field(default=0, ge=0)
    favicon: Optional[str] = None


class ItemUpdate(BaseModel):
    url: Optional[str] = None
    title: Optional[str] = Field(max_length=500, default=None)
    category: Optional[str] = Field(max_length=50, default=None)
    notes: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(unread|reading|done)$")
    scroll_position: Optional[int] = Field(default=None, ge=0, le=100)
    estimated_read_time: Optional[int] = Field(default=None, ge=0)
    favicon: Optional[str] = None


class ItemResponse(BaseModel):
    id: str
    url: Optional[str] = None
    title: str
    category: str
    notes: Optional[str] = None
    status: str
    scroll_position: int
    estimated_read_time: int
    favicon: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ItemListResponse(BaseModel):
    items: List[ItemResponse]
    total: int


class ScrollUpdate(BaseModel):
    url: str
    scroll_position: int = Field(ge=0, le=100)


# ── Sync ──────────────────────────────────────────────

class SyncRequest(BaseModel):
    """Extension sends its local items for full sync."""
    items: List[ItemCreate]
    last_sync: Optional[datetime] = None


class SyncResponse(BaseModel):
    """Server responds with the merged state."""
    items: List[ItemResponse]
    synced_at: datetime
