"""
app/routers/web_api.py
──────────────────────
Interactive Web API endpoints for the browser dashboard & AI fault simulator.
"""

import base64
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.spare_part import SparePart
from app.services import ai_engine, parts_lookup, youtube

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["web-ui"])


class DiagnoseRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    language: str | None = "english"
    image_base64: str | None = None
    mime_type: str | None = None


@router.post("/diagnose")
async def web_diagnose(
    payload: DiagnoseRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Run the full AI fault diagnosis pipeline from the web UI:
    Gemini analysis -> PostgreSQL parts enrichment -> YouTube video search.
    """
    if not payload.message and not payload.image_base64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either message text or an image is required.",
        )

    conv_id = payload.conversation_id or f"web_{uuid.uuid4().hex[:8]}"

    # Decode image if provided
    img_bytes: bytes | None = None
    if payload.image_base64:
        try:
            # Strip data URL prefix if present (e.g. data:image/jpeg;base64,...)
            raw_b64 = payload.image_base64
            if "," in raw_b64:
                raw_b64 = raw_b64.split(",", 1)[1]
            img_bytes = base64.b64decode(raw_b64)
        except Exception as e:
            logger.warning("Failed to decode image_base64: %s", e)

    # 1. AI Analysis via Gemini
    try:
        analysis = await ai_engine.analyse_fault(
            conversation_id=conv_id,
            user_message=payload.message or "Identify this machine/vehicle part fault.",
            image_bytes=img_bytes,
            mime_type=payload.mime_type or "image/jpeg",
        )
    except Exception as exc:
        logger.error("AI fault analysis failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI Engine error: {exc}",
        )

    # 2. Enrich parts from PostgreSQL catalogue
    enriched_parts: list[dict] = []
    if analysis.spare_parts:
        try:
            enriched_parts = await parts_lookup.enrich_parts(analysis.spare_parts, db)
        except Exception as exc:
            logger.warning("Parts enrichment failed: %s", exc)
            enriched_parts = analysis.spare_parts

    # 3. Search YouTube repair tutorials
    videos: list[dict] = []
    search_queries = analysis.search_queries or []
    if search_queries:
        try:
            videos = await youtube.search_multiple_queries(
                search_queries,
                db,
                videos_per_query=2,
                language=payload.language or "english",
            )
        except Exception as exc:
            logger.warning("YouTube search failed: %s", exc)

    return {
        "conversation_id": conv_id,
        "detected_language": analysis.detected_language,
        "fault_summary": analysis.fault_summary,
        "root_causes": analysis.root_causes,
        "severity": analysis.severity,
        "safety_warning": analysis.safety_warning,
        "needs_clarification": analysis.needs_clarification,
        "clarification_question": analysis.clarification_question,
        "spare_parts": enriched_parts,
        "youtube_tutorials": videos,
        "search_queries": search_queries,
    }


@router.get("/catalog")
async def get_catalog(
    search: str | None = Query(None, description="Search keyword"),
    category: str | None = Query(None, description="Filter category"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve spare parts from the database with search and filtering."""
    query = select(SparePart)

    if category and category.lower() != "all":
        query = query.where(func.lower(SparePart.category) == category.lower())

    if search:
        search_pattern = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(SparePart.name).contains(search_pattern),
                func.lower(SparePart.part_number).contains(search_pattern),
                func.lower(SparePart.brand).contains(search_pattern),
                func.lower(SparePart.description).contains(search_pattern),
            )
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_count = (await db.execute(count_query)).scalar() or 0

    # Paginate
    query = query.order_by(SparePart.category, SparePart.name).limit(limit).offset(offset)
    result = await db.execute(query)
    parts = result.scalars().all()

    # Get distinct categories
    cats_query = select(SparePart.category).distinct().where(SparePart.category.is_not(None))
    cats_res = await db.execute(cats_query)
    categories = sorted([c for c in cats_res.scalars().all() if c])

    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "categories": categories,
        "parts": [
            {
                "id": str(p.id),
                "part_number": p.part_number,
                "name": p.name,
                "description": p.description,
                "category": p.category,
                "brand": p.brand,
                "compatible_with": p.compatible_with or [],
                "price_min": p.price_min,
                "price_max": p.price_max,
                "currency": p.currency,
                "in_stock": p.in_stock,
                "stock_qty": p.stock_qty,
            }
            for p in parts
        ],
    }


@router.get("/parts/semantic-search")
async def semantic_search_parts(
    q: str = Query(..., min_length=2, description="Natural symptom, fault description, or part name"),
    limit: int = Query(5, ge=1, le=20),
    min_score: float = Query(0.20, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Search spare parts catalogue using Sentence-BERT dense semantic embeddings.
    Matches user problem descriptions (e.g. 'screeching noise when braking')
    to relevant spare parts with cosine similarity scores.
    """
    results = await parts_lookup.search_parts_semantic(
        query=q,
        db=db,
        top_k=limit,
        min_score=min_score,
    )
    return {
        "query": q,
        "engine": "Sentence-BERT (all-MiniLM-L6-v2)",
        "total": len(results),
        "results": results,
    }


@router.get("/system-status")
async def get_system_status(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Check connectivity and configuration status for all integrations."""
    db_ok = False
    part_count = 0
    try:
        count_res = await db.execute(select(func.count(SparePart.id)))
        part_count = count_res.scalar() or 0
        db_ok = True
    except Exception as e:
        logger.warning("DB check failed: %s", e)

    return {
        "status": "online",
        "app_env": settings.app_env,
        "port": settings.app_port,
        "database": {
            "connected": db_ok,
            "engine": "PostgreSQL (Neon Cloud)",
            "parts_in_db": part_count,
        },
        "sbert": {
            "model": "all-MiniLM-L6-v2",
            "type": "Dense Sentence Transformers (Cosine Similarity)",
            "status": "active",
        },
        "gemini": {
            "configured": bool(settings.gemini_api_key),
            "model": settings.gemini_model,
        },
        "youtube": {
            "configured": bool(settings.youtube_api_key),
        },
        "whatsapp": {
            "configured": bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id),
            "verify_token": settings.whatsapp_verify_token,
            "phone_number_id": settings.whatsapp_phone_number_id,
            "api_version": settings.whatsapp_api_version,
            "webhook_endpoint": "/webhook",
        },
    }

