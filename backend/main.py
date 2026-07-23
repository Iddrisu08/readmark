"""
ReadMark — Main Application
FastAPI server with REST API + static web dashboard.
"""

import re
from contextlib import asynccontextmanager
from urllib.parse import urlparse as _urlparse

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse

from config import settings
from database import init_db, get_db
from models import User
from auth import get_current_user
from routes.auth_routes import router as auth_router
from routes.items_routes import router as items_router
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create database tables."""
    await init_db()
    print(f"✦ {settings.APP_NAME} v{settings.APP_VERSION} ready")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────

origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routes ────────────────────────────────────────

app.include_router(auth_router, prefix="/api")
app.include_router(items_router, prefix="/api")


# ── Health Check ──────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


# ── Static Web Dashboard ─────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def serve_dashboard():
    return FileResponse("static/index.html")


@app.get("/manifest.json")
async def serve_manifest():
    return FileResponse("static/manifest.json", media_type="application/manifest+json")


@app.get("/sw.js")
async def serve_sw():
    return FileResponse("static/sw.js", media_type="application/javascript")


@app.get("/read")
async def serve_reader():
    return FileResponse("static/read.html")


# ── Article Proxy ─────────────────────────────────────

@app.get("/api/proxy")
async def proxy_article(
    url: str = Query(...),
    user: User = Depends(get_current_user),
):
    """
    Fetch article HTML server-side and return it with a <base> tag injected
    so the in-app reader can render it on our domain with full scroll tracking.
    """
    try:
        parsed = _urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise HTTPException(status_code=400, detail="Invalid URL scheme")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL")

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url, headers={
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/17.0 Mobile/15E148 Safari/604.1"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            })
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Article fetch timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch article: {e}")

    if "text/html" not in resp.headers.get("content-type", ""):
        raise HTTPException(status_code=400, detail="URL does not return HTML content")

    html = resp.text
    final_url = str(resp.url)

    # Detect bot-protection / JS challenge pages (Cloudflare, DDoS-Guard, etc.)
    # These pages require a real browser to solve — the proxy can never render them.
    _lower = html.lower()
    _bot_markers = [
        "just a moment",
        "enable javascript and cookies",
        "checking your browser",
        "cf-browser-verification",
        "ddos-guard",
        "please wait while we verify",
        "ray id",          # Cloudflare error pages
        "_cf_chl_opt",     # Cloudflare challenge JS variable
    ]
    if any(m in _lower for m in _bot_markers) and len(html) < 100_000:
        raise HTTPException(status_code=403, detail="bot_protection")

    # Detect login / paywall walls (page returned but has no real content)
    _wall_markers = [
        "sign in to read",
        "become a member to read",
        "subscribe to continue",
        "create a free account",
        "log in to continue",
    ]
    if any(m in _lower for m in _wall_markers) and len(html) < 80_000:
        raise HTTPException(status_code=451, detail="paywall")

    # Remove CSP meta tags so the page can load resources from the original domain
    html = re.sub(
        r'<meta[^>]+http-equiv=["\']Content-Security-Policy["\'][^>]*/?>',
        '', html, flags=re.IGNORECASE
    )

    # Inject <base> tag so relative URLs (images, CSS, links) resolve correctly
    base_tag = f'<base href="{final_url}">'
    if re.search(r'<head[^>]*>', html, re.IGNORECASE):
        html = re.sub(r'(<head[^>]*>)', rf'\1{base_tag}', html, count=1, flags=re.IGNORECASE)
    else:
        html = f'<html><head>{base_tag}</head><body>{html}</body></html>'

    return HTMLResponse(content=html)
