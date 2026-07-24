"""
ReadMark — AI Routes
Claude-powered article summarization + per-user usage/cost reporting.
"""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User, ReadingItem, AIUsage
from schemas import SummarizeRequest, SummarizeResponse, UsageSummaryResponse
from auth import get_current_user
from config import settings
from ai import summarize_text, html_to_text, AIError
from observability import record_ai_usage

router = APIRouter(prefix="/ai", tags=["ai"])
log = logging.getLogger("readmark.ai")


async def _fetch_article_text(url: str) -> str:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url, headers={"User-Agent": "ReadMarkBot/1.0"})
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch the article (HTTP {e.response.status_code})")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not fetch the article to summarize")
    return html_to_text(resp.text)


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize(
    req: SummarizeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Summarize a saved item, a URL, or raw text using Claude."""
    if not settings.ai_enabled:
        raise HTTPException(status_code=503, detail="AI summarization is not enabled")

    item = None
    content = req.text

    # Resolve content: prefer explicit text, then a saved item, then a URL.
    if not content and req.item_id:
        item = (await db.execute(
            select(ReadingItem).where(
                ReadingItem.id == req.item_id, ReadingItem.user_id == user.id
            )
        )).scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        if not item.url:
            raise HTTPException(status_code=400, detail="Item has no URL to summarize")
        content = await _fetch_article_text(item.url)
    elif not content and req.url:
        content = await _fetch_article_text(req.url)

    if not content:
        raise HTTPException(status_code=400, detail="Provide item_id, url, or text")

    try:
        result = await summarize_text(content)
    except AIError as e:
        record_ai_usage(settings.AI_PROVIDER, settings.AI_MODEL, 0, 0, 0, status="error")
        log.error("summarize failed", extra={"extra_fields": {"user_id": user.id, "error": str(e)}})
        raise HTTPException(status_code=502, detail=str(e))

    # Persist summary on the item (if any) and log usage for cost tracking.
    if item:
        item.summary = result.summary
    db.add(AIUsage(
        user_id=user.id, item_id=(item.id if item else None),
        provider=result.provider, model=result.model, operation="summarize",
        input_tokens=result.input_tokens, output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
    ))
    await db.commit()

    record_ai_usage(result.provider, result.model,
                    result.input_tokens, result.output_tokens, result.cost_usd)
    log.info("summarize ok", extra={"extra_fields": {
        "user_id": user.id, "model": result.model,
        "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
        "cost_usd": result.cost_usd,
    }})

    return SummarizeResponse(
        item_id=(item.id if item else None),
        summary=result.summary, provider=result.provider, model=result.model,
        input_tokens=result.input_tokens, output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
    )


@router.get("/usage", response_model=UsageSummaryResponse)
async def usage(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate the current user's AI usage and estimated spend."""
    row = (await db.execute(
        select(
            func.count(AIUsage.id),
            func.coalesce(func.sum(AIUsage.input_tokens), 0),
            func.coalesce(func.sum(AIUsage.output_tokens), 0),
            func.coalesce(func.sum(AIUsage.cost_usd), 0.0),
        ).where(AIUsage.user_id == user.id)
    )).one()
    return UsageSummaryResponse(
        total_requests=row[0], total_input_tokens=row[1],
        total_output_tokens=row[2], total_cost_usd=round(row[3], 6),
    )
