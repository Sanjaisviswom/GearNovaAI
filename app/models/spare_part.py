"""
app/models/spare_part.py
────────────────────────
Spare parts catalog and YouTube video cache.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SparePart(Base):
    """
    Catalogue of known spare parts.
    Populated from a CSV seed or manually via admin API.
    The AI engine queries this table to enrich its suggestions.
    """

    __tablename__ = "spare_parts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    part_number: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Machine / equipment types this part is compatible with
    compatible_with: Mapped[list | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    # Common fault keywords associated with this part
    fault_keywords: Mapped[list | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    price_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    stock_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_spare_parts_name_search", "name"),
    )

    def __repr__(self) -> str:
        return f"<SparePart {self.part_number} — {self.name}>"


class YouTubeCache(Base):
    """
    Cached YouTube search results keyed by the search query.
    Reduces API quota consumption for repeated/similar queries.
    """

    __tablename__ = "youtube_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    query: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)
    # JSON list of {title, url, thumbnail, channel} dicts
    results: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    hit_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Cache TTL: entries older than 7 days are refreshed
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<YouTubeCache query={self.query!r} hits={self.hit_count}>"
