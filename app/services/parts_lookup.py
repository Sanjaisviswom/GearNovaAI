"""
app/services/parts_lookup.py
─────────────────────────────
Spare parts database lookup service.

Enriches AI-suggested parts with structured data from the PostgreSQL catalogue.
Falls back gracefully to the AI's raw suggestions if no DB match is found.
"""

import logging

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spare_part import SparePart

logger = logging.getLogger(__name__)


async def enrich_parts(
    ai_parts: list[dict],
    db: AsyncSession,
) -> list[dict]:
    """
    Attempt to match AI-suggested parts against the spare parts catalogue.

    For each AI suggestion:
      1. Try exact part-number match
      2. Try SBERT dense semantic similarity match (handles synonyms, typos, paraphrasing)
      3. Try keyword substring match fallback
      4. If no match, return the AI suggestion as-is (with a flag)

    Returns the enriched list (always same length as input).
    """
    enriched: list[dict] = []

    for part in ai_parts:
        ai_name: str = part.get("name", "")
        ai_pn: str | None = part.get("part_number")

        db_part: SparePart | None = None
        match_type: str = "ai_suggestion"
        similarity_score: float | None = None

        # ── 1. Exact part number match ────────────────────────
        if ai_pn:
            stmt = select(SparePart).where(
                func.lower(SparePart.part_number) == ai_pn.lower().strip()
            )
            result = await db.execute(stmt)
            db_part = result.scalar_one_or_none()
            if db_part:
                match_type = "exact_part_number"

        # ── 2. SBERT Semantic Match ───────────────────────────
        if db_part is None and ai_name:
            try:
                from app.services.sbert_matcher import sbert_engine

                matched_part, score = await sbert_engine.match_ai_part(
                    ai_part_name=ai_name,
                    db=db,
                    min_score=0.45,
                )
                if matched_part:
                    db_part = matched_part
                    match_type = "sbert_semantic"
                    similarity_score = score
                    logger.info(
                        "SBERT matched '%s' -> '%s' (similarity: %.3f)",
                        ai_name,
                        db_part.name,
                        similarity_score,
                    )
            except Exception as sbert_err:
                logger.warning("SBERT semantic match skipped: %s", sbert_err)

        # ── 3. Name substring match fallback ──────────────────
        if db_part is None and ai_name:
            words = [w for w in ai_name.split() if len(w) > 3]
            if words:
                conditions = [
                    func.lower(SparePart.name).contains(w.lower()) for w in words[:3]
                ]
                stmt = select(SparePart).where(or_(*conditions)).limit(1)
                result = await db.execute(stmt)
                db_part = result.scalar_one_or_none()
                if db_part:
                    match_type = "keyword_substring"

        if db_part:
            enriched.append(
                {
                    **part,
                    "db_id": str(db_part.id),
                    "part_number": db_part.part_number or ai_pn,
                    "name": db_part.name,
                    "brand": db_part.brand,
                    "price_min": db_part.price_min,
                    "price_max": db_part.price_max,
                    "currency": db_part.currency,
                    "in_stock": db_part.in_stock,
                    "source": "catalogue",
                    "match_type": match_type,
                    "similarity_score": similarity_score,
                }
            )
            logger.debug("DB match found for part: %s → %s (%s)", ai_name, db_part.name, match_type)
        else:
            enriched.append(
                {
                    **part,
                    "source": "ai_suggestion",  # No catalogue entry
                    "match_type": "ai_suggestion",
                }
            )
            logger.debug("No DB match for part: %s (using AI suggestion)", ai_name)

    return enriched


async def search_parts_semantic(
    query: str,
    db: AsyncSession,
    top_k: int = 5,
    min_score: float = 0.25,
) -> list[dict]:
    """
    Dense semantic search across the spare parts catalogue using Sentence-BERT.
    Matches queries by natural symptoms, colloquial phrasing, or brand/category.
    """
    try:
        from app.services.sbert_matcher import sbert_engine

        return await sbert_engine.semantic_search(
            query=query,
            db=db,
            top_k=top_k,
            min_score=min_score,
        )
    except Exception as exc:
        logger.error("Semantic search failed, falling back to keyword search: %s", exc)
        keyword_parts = await search_parts_by_keyword(query, db, limit=top_k)
        return [
            {
                "id": str(p.id),
                "part_number": p.part_number,
                "name": p.name,
                "category": p.category,
                "brand": p.brand,
                "compatible_with": p.compatible_with,
                "fault_keywords": p.fault_keywords,
                "price_min": p.price_min,
                "price_max": p.price_max,
                "currency": p.currency,
                "in_stock": p.in_stock,
                "similarity_score": None,
                "match_type": "keyword_fallback",
            }
            for p in keyword_parts
        ]



async def search_parts_by_keyword(
    keyword: str,
    db: AsyncSession,
    limit: int = 10,
) -> list[SparePart]:
    """
    Full-text keyword search across part names, descriptions and categories.
    Used by the admin API for manual part browsing.
    """
    stmt = (
        select(SparePart)
        .where(
            or_(
                func.lower(SparePart.name).contains(keyword.lower()),
                func.lower(SparePart.description).contains(keyword.lower()),
                func.lower(SparePart.category).contains(keyword.lower()),
                func.lower(SparePart.part_number).contains(keyword.lower()),
            )
        )
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def format_price_range(part: dict) -> str:
    """Return a human-readable price range string for a part dict."""
    pmin = part.get("price_min")
    pmax = part.get("price_max")
    currency = part.get("currency", "INR")
    if pmin and pmax:
        return f"{currency} {pmin:,.0f} – {pmax:,.0f}"
    if pmin:
        return f"From {currency} {pmin:,.0f}"
    return "Price on request"
