"""
tests/conftest.py
──────────────────
Shared pytest fixtures: test client, async DB session, mock services.
"""

import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.dependencies import verify_api_key
from app.main import app

# ── In-memory SQLite for tests ────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_spare_parts.db"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(scope="session")
async def create_tables():
    """Create all DB tables once per test session."""
    async with test_engine.begin() as conn:
        import app.models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db(create_tables) -> AsyncGenerator[AsyncSession, None]:
    """Fresh DB session per test, rolled back after each test."""
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db: AsyncSession):
    """Async test client with DB dependency overridden and API key auth bypassed."""
    async def override_get_db():
        yield db

    async def override_verify_api_key():
        """Skip API key validation in tests."""
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_api_key] = override_verify_api_key

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Sample WhatsApp webhook payload ──────────────────────────

def make_text_payload(from_number: str, text: str, msg_id: str = "msg_001") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_id",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "contacts": [
                                {"profile": {"name": "Test User"}, "wa_id": from_number}
                            ],
                            "messages": [
                                {
                                    "id": msg_id,
                                    "from": from_number,
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def make_status_payload() -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_id",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "statuses": [
                                {
                                    "id": "msg_001",
                                    "status": "delivered",
                                    "timestamp": "1700000001",
                                    "recipient_id": "919876543210",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
