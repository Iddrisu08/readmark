"""
ReadMark — Configuration
Loads settings from environment variables / .env file.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "ReadMark"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ALLOWED_ORIGINS: str = "*"  # Comma-separated origins for CORS

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./readmark.db"

    # JWT Auth
    SECRET_KEY: str = "change-me-to-a-random-secret-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None

    # AI (article summarization). Feature is disabled if no API key is set.
    AI_PROVIDER: str = "anthropic"
    ANTHROPIC_API_KEY: Optional[str] = None
    AI_MODEL: str = "claude-haiku-4-5-20251001"  # cheap + fast for summaries
    AI_MAX_TOKENS: int = 400

    @property
    def ai_enabled(self) -> bool:
        return bool(self.ANTHROPIC_API_KEY)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
