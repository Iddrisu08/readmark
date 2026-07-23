"""
ReadMark — Items Routes
CRUD operations, scroll tracking, bulk sync for extension.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User, ReadingItem
from schemas import (
    ItemCreate, ItemUpdate, ItemResponse, ItemListResponse,
    ScrollUpdate, SyncRequest, SyncResponse,
)
from auth import get_current_user
from url_utils import normalize_url

router = APIRouter(prefix="/items", tags=["items"])


# ── List Items ────────────────────────────────────────

@router.get("", response_model=ItemListResponse)
async def list_items(
    status_filter: Optional[str] = Query(None, alias="status", pattern="^(unread|reading|done)$"),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort: str = Query("newest", pattern="^(newest|oldest|updated|alpha)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List reading items with filters, search, and sorting."""
    query = select(ReadingItem).where(ReadingItem.user_id == user.id)

    if status_filter:
        query = query.where(ReadingItem.status == status_filter)
    if category:
        query = query.where(ReadingItem.category == category)
    if search:
        search_term = f"%{search}%"
        query = query.where(
            ReadingItem.title.ilike(search_term)
            | ReadingItem.url.ilike(search_term)
            | ReadingItem.notes.ilike(search_term)
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Sort
    if sort == "newest":
        query = query.order_by(ReadingItem.created_at.desc())
    elif sort == "oldest":
        query = query.order_by(ReadingItem.created_at.asc())
    elif sort == "updated":
        query = query.order_by(ReadingItem.updated_at.desc())
    elif sort == "alpha":
        query = query.order_by(ReadingItem.title.asc())

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()

    return ItemListResponse(
        items=[ItemResponse.model_validate(i) for i in items],
        total=total,
    )


# ── Create Item ───────────────────────────────────────

@router.post("", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    req: ItemCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save a new reading item."""
    normalized = normalize_url(req.url) if req.url else None

    # Check for duplicates by normalized URL
    if normalized:
        result = await db.execute(
            select(ReadingItem).where(
                and_(
                    ReadingItem.user_id == user.id,
                    ReadingItem.normalized_url == normalized,
                )
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This URL is already in your library",
            )

    item = ReadingItem(
        user_id=user.id,
        url=req.url,
        normalized_url=normalized,
        title=req.title,
        category=req.category,
        notes=req.notes,
        status=req.status,
        scroll_position=req.scroll_position,
        estimated_read_time=req.estimated_read_time,
        favicon=req.favicon,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    return ItemResponse.model_validate(item)


# ── Scroll Position Update (by URL) ──────────────────

@router.post("/scroll", response_model=ItemResponse)
async def update_scroll_position(
    req: ScrollUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update scroll position for a URL.
    Used by the extension to continuously sync reading progress.
    """
    normalized = normalize_url(req.url)

    result = await db.execute(
        select(ReadingItem).where(
            and_(
                ReadingItem.user_id == user.id,
                ReadingItem.normalized_url == normalized,
            )
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    item.scroll_position = req.scroll_position
    item.updated_at = datetime.now(timezone.utc)

    # Auto-advance status
    if req.scroll_position > 10 and item.status == "unread":
        item.status = "reading"
    if req.scroll_position >= 95 and item.status == "reading":
        item.status = "done"

    await db.commit()
    await db.refresh(item)

    return ItemResponse.model_validate(item)


# ── Lookup by URL ─────────────────────────────────────

@router.get("/lookup/url", response_model=Optional[ItemResponse])
async def lookup_by_url(
    url: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Look up an item by URL. Used by extension to check if a page is saved."""
    normalized = normalize_url(url)

    result = await db.execute(
        select(ReadingItem).where(
            and_(
                ReadingItem.user_id == user.id,
                ReadingItem.normalized_url == normalized,
            )
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        return None
    return ItemResponse.model_validate(item)


# ── Get Single Item ───────────────────────────────────

@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single reading item by ID."""
    result = await db.execute(
        select(ReadingItem).where(
            and_(ReadingItem.id == item_id, ReadingItem.user_id == user.id)
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return ItemResponse.model_validate(item)


# ── Update Item ───────────────────────────────────────

@router.patch("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: str,
    req: ItemUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a reading item (partial update)."""
    result = await db.execute(
        select(ReadingItem).where(
            and_(ReadingItem.id == item_id, ReadingItem.user_id == user.id)
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    update_data = req.model_dump(exclude_unset=True)

    # ── Status transition rules ───────────────────────────
    if "status" in update_data:
        new_status = update_data["status"]
        # Once reading or done, cannot go back to unread
        if new_status == "unread" and item.status in ("reading", "done"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot move a started item back to unread",
            )
        # Cannot mark as done unless at least 95% read
        effective_scroll = update_data.get("scroll_position", item.scroll_position)
        if new_status == "done" and item.status in ("unread", "reading") and effective_scroll < 95:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Finish reading the article before marking it as done",
            )

    for field, value in update_data.items():
        setattr(item, field, value)

    # Re-normalize URL if it changed
    if "url" in update_data:
        item.normalized_url = normalize_url(item.url) if item.url else None

    item.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)

    return ItemResponse.model_validate(item)


# ── Delete Item ───────────────────────────────────────

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a reading item."""
    result = await db.execute(
        select(ReadingItem).where(
            and_(ReadingItem.id == item_id, ReadingItem.user_id == user.id)
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    await db.delete(item)
    await db.commit()


# ── Bulk Sync (Extension ↔ Server) ───────────────────

@router.post("/sync", response_model=SyncResponse)
async def sync_items(
    req: SyncRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Full sync endpoint for the extension.
    Receives local items, merges with server state, returns the canonical list.
    Strategy: server wins on conflicts, new items from extension get added.
    """
    # Get all server items
    result = await db.execute(
        select(ReadingItem).where(ReadingItem.user_id == user.id)
    )
    server_items = {i.normalized_url: i for i in result.scalars().all() if i.normalized_url}

    # Process extension items
    for ext_item in req.items:
        normalized = normalize_url(ext_item.url) if ext_item.url else None
        if not normalized:
            continue

        if normalized in server_items:
            # Item exists on server — update scroll position if extension has higher progress
            server_item = server_items[normalized]
            if ext_item.scroll_position > server_item.scroll_position:
                server_item.scroll_position = ext_item.scroll_position
                server_item.updated_at = datetime.now(timezone.utc)
                # Auto-advance status
                if ext_item.scroll_position > 10 and server_item.status == "unread":
                    server_item.status = "reading"
                if ext_item.scroll_position >= 95 and server_item.status == "reading":
                    server_item.status = "done"
            # Keep notes from extension if server has none
            if ext_item.notes and not server_item.notes:
                server_item.notes = ext_item.notes
        else:
            # New item from extension — add to server
            new_item = ReadingItem(
                user_id=user.id,
                url=ext_item.url,
                normalized_url=normalized,
                title=ext_item.title,
                category=ext_item.category,
                notes=ext_item.notes,
                status=ext_item.status,
                scroll_position=ext_item.scroll_position,
                estimated_read_time=ext_item.estimated_read_time,
                favicon=ext_item.favicon,
            )
            db.add(new_item)

    await db.commit()

    # Return all items
    result = await db.execute(
        select(ReadingItem)
        .where(ReadingItem.user_id == user.id)
        .order_by(ReadingItem.created_at.desc())
    )
    all_items = result.scalars().all()

    return SyncResponse(
        items=[ItemResponse.model_validate(i) for i in all_items],
        synced_at=datetime.now(timezone.utc),
    )
