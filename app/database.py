"""
app/database.py
───────────────
Async SQLAlchemy engine + session factory.
Use `get_db` as a FastAPI dependency in routers.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# ── Engine ────────────────────────────────────────────────────
engine = create_async_engine(
    settings.database_url,
    echo=not settings.is_production,  # Log SQL in dev
    pool_pre_ping=True,
)

# ── Session factory ───────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ── Base class for all ORM models ─────────────────────────────
class Base(DeclarativeBase):
    pass


# ── FastAPI Dependency ────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields a DB session per request and ensures it is closed afterwards.

    Usage in a router:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
