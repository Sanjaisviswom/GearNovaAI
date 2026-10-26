"""
app/routers/admin.py
─────────────────────
Admin REST API for managing the spare parts catalogue and viewing conversation history.

Endpoints:
  GET  /admin/parts             → List all spare parts (paginated)
  POST /admin/parts             → Add a new spare part
  GET  /admin/parts/{id}        → Get a single spare part
  PUT  /admin/parts/{id}        → Update a spare part
  DELETE /admin/parts/{id}      → Delete a spare part
  GET  /admin/parts/search      → Keyword search
  POST /admin/parts/bulk-import → Import CSV of parts

  GET  /admin/conversations      → List recent conversations
  GET  /admin/conversations/{id} → Get conversation + messages
  GET  /admin/stats              → Usage statistics
"""

import csv
import io
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import verify_api_key
from app.models.conversation import Conversation, Message
from app.models.spare_part import SparePart
from app.models.user import User
from app.services.parts_lookup import search_parts_by_keyword

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(verify_api_key)],
)


# ── Pydantic schemas ──────────────────────────────────────────

class SparePartCreate(BaseModel):
    part_number: str | None = None
    name: str
    description: str | None = None
    category: str | None = None
    brand: str | None = None
    compatible_with: list[str] | None = None
    fault_keywords: list[str] | None = None
    price_min: float | None = None
    price_max: float | None = None
    currency: str = "INR"
    in_stock: bool = True
    stock_qty: int | None = None


class SparePartUpdate(SparePartCreate):
    name: str | None = None  # All fields optional for update


class SparePartResponse(SparePartCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ── Parts CRUD ────────────────────────────────────────────────

@router.get("/parts", response_model=list[SparePartResponse])
async def list_parts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    category: str | None = None,
    in_stock: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List spare parts with optional filtering."""
    stmt = select(SparePart).offset(skip).limit(limit)
    if category:
        stmt = stmt.where(func.lower(SparePart.category) == category.lower())
    if in_stock is not None:
        stmt = stmt.where(SparePart.in_stock == in_stock)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/parts", response_model=SparePartResponse, status_code=status.HTTP_201_CREATED)
async def create_part(
    part_data: SparePartCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a new spare part to the catalogue."""
    part = SparePart(**part_data.model_dump())
    db.add(part)
    await db.flush()
    return part


@router.get("/parts/search", response_model=list[SparePartResponse])
async def search_parts(
    q: str = Query(..., min_length=2, description="Keyword to search"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Keyword search across part names, descriptions, categories."""
    return await search_parts_by_keyword(q, db, limit=limit)


@router.get("/parts/{part_id}", response_model=SparePartResponse)
async def get_part(part_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get a single spare part by ID."""
    result = await db.execute(select(SparePart).where(SparePart.id == part_id))
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(status_code=404, detail="Spare part not found")
    return part


@router.put("/parts/{part_id}", response_model=SparePartResponse)
async def update_part(
    part_id: uuid.UUID,
    updates: SparePartUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a spare part."""
    result = await db.execute(select(SparePart).where(SparePart.id == part_id))
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(status_code=404, detail="Spare part not found")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(part, field, value)
    await db.flush()
    return part


@router.delete("/parts/{part_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_part(part_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Delete a spare part from the catalogue."""
    result = await db.execute(select(SparePart).where(SparePart.id == part_id))
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(status_code=404, detail="Spare part not found")
    await db.delete(part)


@router.post("/parts/bulk-import", status_code=status.HTTP_201_CREATED)
async def bulk_import_parts(
    file: UploadFile = File(..., description="CSV file with spare parts"),
    db: AsyncSession = Depends(get_db),
):
    """
    Import spare parts from a CSV file.

    Expected CSV columns (all optional except 'name'):
    part_number, name, description, category, brand, price_min, price_max, currency, in_stock
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")

    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))

    created = 0
    errors: list[str] = []

    for row_num, row in enumerate(reader, start=2):  # Row 1 = header
        name = row.get("name", "").strip()
        if not name:
            errors.append(f"Row {row_num}: 'name' is required")
            continue
        try:
            part = SparePart(
                part_number=row.get("part_number") or None,
                name=name,
                description=row.get("description") or None,
                category=row.get("category") or None,
                brand=row.get("brand") or None,
                price_min=float(row["price_min"]) if row.get("price_min") else None,
                price_max=float(row["price_max"]) if row.get("price_max") else None,
                currency=row.get("currency", "INR"),
                in_stock=row.get("in_stock", "true").lower() in ("true", "1", "yes"),
            )
            db.add(part)
            created += 1
        except (ValueError, KeyError) as exc:
            errors.append(f"Row {row_num}: {exc}")

    await db.flush()
    return {"created": created, "errors": errors}


# ── Conversations ─────────────────────────────────────────────

@router.get("/conversations")
async def list_conversations(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List recent conversations with user info."""
    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.user))
        .order_by(Conversation.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    convs = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "user_phone": c.user.phone_number if c.user else None,
            "user_name": c.user.name if c.user else None,
            "status": c.status,
            "fault_summary": c.fault_summary,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        for c in convs
    ]


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get full conversation with all messages."""
    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.messages), selectinload(Conversation.user))
        .where(Conversation.id == conv_id)
    )
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "id": str(conv.id),
        "status": conv.status,
        "fault_summary": conv.fault_summary,
        "user": {"phone": conv.user.phone_number, "name": conv.user.name} if conv.user else None,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "metadata": m.metadata_,
                "created_at": m.created_at,
            }
            for m in conv.messages
        ],
    }


# ── Statistics ────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """High-level usage statistics."""
    total_users = (await db.execute(select(func.count(User.id)))).scalar()
    total_convs = (await db.execute(select(func.count(Conversation.id)))).scalar()
    total_msgs = (await db.execute(select(func.count(Message.id)))).scalar()
    total_parts = (await db.execute(select(func.count(SparePart.id)))).scalar()
    return {
        "total_users": total_users,
        "total_conversations": total_convs,
        "total_messages": total_msgs,
        "catalogue_parts": total_parts,
    }
