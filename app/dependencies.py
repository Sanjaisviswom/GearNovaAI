"""
app/dependencies.py
───────────────────
Reusable FastAPI dependencies shared across routers.
"""

import logging

from fastapi import Header, HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)


async def verify_api_key(x_api_key: str = Header(..., description="Admin API key")) -> None:
    """
    Validate the X-API-Key request header against the configured ADMIN_API_KEY.
    Raises HTTP 401 if the key is missing or incorrect.
    """
    if x_api_key != settings.admin_api_key:
        logger.warning("Rejected request with invalid API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
