"""
ReadMark — Database Setup
Async SQLAlchemy engine with SQLite.
"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False},  # Required for SQLite
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables, then apply lightweight additive migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_columns)


def _ensure_columns(conn):
    """Idempotently add columns introduced after a table was first created.

    create_all() never ALTERs existing tables, so a new column on an existing
    DB needs this. Dialect-agnostic (works on SQLite and Postgres).
    """
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    if "reading_items" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("reading_items")}
    if "summary" not in cols:
        conn.execute(text("ALTER TABLE reading_items ADD COLUMN summary TEXT"))


async def check_db() -> bool:
    """Readiness probe — returns True if the database answers a trivial query."""
    from sqlalchemy import text
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def get_db():
    """Dependency that yields a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
