"""
tests/test_webhook.py
──────────────────────
Tests for the WhatsApp webhook handler.
"""

import pytest
from httpx import AsyncClient

from app.config import settings
from tests.conftest import make_status_payload, make_text_payload


@pytest.mark.asyncio
async def test_webhook_verification_success(client: AsyncClient):
    """GET /webhook with correct verify token should echo the challenge."""
    response = await client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.whatsapp_verify_token,
            "hub.challenge": "12345",
        },
    )
    assert response.status_code == 200
    assert response.text == "12345"


@pytest.mark.asyncio
async def test_webhook_verification_wrong_token(client: AsyncClient):
    """GET /webhook with wrong verify token should return 403."""
    response = await client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "12345",
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_webhook_status_update_ignored(client: AsyncClient):
    """POST /webhook with a status update (not a message) should return 200."""
    response = await client.post("/webhook", json=make_status_payload())
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_webhook_text_message_accepted(client: AsyncClient):
    """POST /webhook with a valid text message should return 200."""
    payload = make_text_payload("919876543210", "my compressor is making noise")
    response = await client.post("/webhook", json=payload)
    # Should always return 200 immediately (background processing)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """GET /health should return 200 with healthy status."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
