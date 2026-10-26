"""
tests/test_admin.py
────────────────────
Tests for the admin spare parts CRUD API.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spare_part import SparePart


@pytest.mark.asyncio
async def test_create_spare_part(client: AsyncClient, db: AsyncSession):
    response = await client.post(
        "/admin/parts",
        json={
            "name": "Test Bearing SKF 6205",
            "part_number": "TEST-6205",
            "category": "Bearings",
            "brand": "SKF",
            "price_min": 350.0,
            "price_max": 650.0,
            "currency": "INR",
            "in_stock": True,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Bearing SKF 6205"
    assert data["part_number"] == "TEST-6205"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_spare_parts(client: AsyncClient, db: AsyncSession):
    # Create one first
    db.add(SparePart(name="List Test Part", part_number="LIST-001"))
    await db.flush()

    response = await client.get("/admin/parts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_search_spare_parts(client: AsyncClient, db: AsyncSession):
    db.add(SparePart(name="Shaft Seal 20x35x7", part_number="SEAL-001", category="Seals"))
    await db.flush()

    response = await client.get("/admin/parts/search", params={"q": "shaft seal"})
    assert response.status_code == 200
    results = response.json()
    assert any("Seal" in p["name"] for p in results)


@pytest.mark.asyncio
async def test_get_part_not_found(client: AsyncClient):
    import uuid
    response = await client.get(f"/admin/parts/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stats_endpoint(client: AsyncClient):
    response = await client.get("/admin/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_users" in data
    assert "catalogue_parts" in data


@pytest.mark.asyncio
async def test_bulk_import_csv(client: AsyncClient):
    csv_content = (
        "part_number,name,category,brand,price_min,price_max,currency,in_stock\n"
        "IMPORT-001,Import Bearing,Bearings,Test,100,200,INR,true\n"
        "IMPORT-002,Import Belt,Belts,Test,50,100,INR,true\n"
    )
    response = await client.post(
        "/admin/parts/bulk-import",
        files={"file": ("test_parts.csv", csv_content.encode(), "text/csv")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["created"] == 2
    assert data["errors"] == []
