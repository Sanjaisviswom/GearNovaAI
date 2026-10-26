"""
scripts/seed_parts.py
──────────────────────
Load the spare parts seed CSV into the PostgreSQL database.

Usage:
    python scripts/seed_parts.py
    python scripts/seed_parts.py --csv data/my_parts.csv
    python scripts/seed_parts.py --clear   # Delete all parts first
"""

import asyncio
import os
import sys

# Fix for psycopg async and UTF-8 encoding on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import csv
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse

from sqlalchemy import delete, select

from app.database import AsyncSessionLocal, engine, Base
from app.models.spare_part import SparePart
import app.models  # noqa: F401


async def seed(csv_path: Path, clear: bool = False) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        if clear:
            await db.execute(delete(SparePart))
            await db.commit()
            print("[OK] Cleared existing spare parts.")

        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            created = 0
            skipped = 0

            for row in reader:
                part_number = row.get("part_number", "").strip() or None

                # Skip duplicates
                if part_number:
                    existing = await db.execute(
                        select(SparePart).where(SparePart.part_number == part_number)
                    )
                    if existing.scalar_one_or_none():
                        skipped += 1
                        continue

                # Parse JSONB fields
                def parse_json_field(val: str) -> list | None:
                    if not val:
                        return None
                    # Accept comma-separated or JSON array
                    val = val.strip()
                    if val.startswith("["):
                        return json.loads(val)
                    return [v.strip() for v in val.split(",") if v.strip()]

                part = SparePart(
                    part_number=part_number,
                    name=row.get("name", "").strip(),
                    description=row.get("description") or None,
                    category=row.get("category") or None,
                    brand=row.get("brand") or None,
                    compatible_with=parse_json_field(row.get("compatible_with", "")),
                    fault_keywords=parse_json_field(row.get("fault_keywords", "")),
                    price_min=float(row["price_min"]) if row.get("price_min") else None,
                    price_max=float(row["price_max"]) if row.get("price_max") else None,
                    currency=row.get("currency", "INR"),
                    in_stock=row.get("in_stock", "true").lower() in ("true", "1", "yes"),
                    stock_qty=int(row["stock_qty"]) if row.get("stock_qty") else None,
                )
                db.add(part)
                created += 1

            await db.commit()
            print(f"[OK] Seeded {created} parts | Skipped {skipped} duplicates.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed spare parts database")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path(__file__).parent.parent / "data" / "spare_parts_seed.csv",
        help="Path to CSV file",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete all spare parts before importing",
    )
    args = parser.parse_args()
    asyncio.run(seed(args.csv, args.clear))
