"""
ReadMark — Auth Routes
Register, login, Google OAuth, profile.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from schemas import RegisterRequest, LoginRequest, GoogleAuthRequest, TokenResponse, UserResponse
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, verify_google_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new account with email and password."""
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == req.email.lower()))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        email=req.email.lower(),
        password_hash=hash_password(req.password),
        name=req.name,
        auth_provider="email",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with email and password."""
    result = await db.execute(select(User).where(User.email == req.email.lower()))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/google", response_model=TokenResponse)
async def google_auth(req: GoogleAuthRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with Google. Creates account if first time."""
    google_info = await verify_google_token(req.credential)

    # Check if user exists by google_id
    result = await db.execute(
        select(User).where(User.google_id == google_info["google_id"])
    )
    user = result.scalar_one_or_none()

    if not user:
        # Check if email already exists (link accounts)
        result = await db.execute(
            select(User).where(User.email == google_info["email"].lower())
        )
        user = result.scalar_one_or_none()

        if user:
            # Link Google to existing email account
            user.google_id = google_info["google_id"]
            if not user.avatar_url:
                user.avatar_url = google_info.get("avatar_url")
            if not user.name:
                user.name = google_info.get("name")
        else:
            # Create new user
            user = User(
                email=google_info["email"].lower(),
                name=google_info.get("name"),
                avatar_url=google_info.get("avatar_url"),
                auth_provider="google",
                google_id=google_info["google_id"],
            )
            db.add(user)

    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_profile(user: User = Depends(get_current_user)):
    """Get the current user's profile."""
    return UserResponse.model_validate(user)
