"""
Test SBERT semantic search on spare parts database.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.database import AsyncSessionLocal
from app.services.sbert_matcher import sbert_engine
from app.services.parts_lookup import enrich_parts, search_parts_semantic


async def main():
    print("Initializing test...")
    async with AsyncSessionLocal() as db:
        queries = [
            "scooter belt slipping loss of speed high rpm",
            "bike not starting clicking sound battery dead",
            "grinding metallic noise on front brakes",
            "heavy engine vibration and dark black oil",
        ]

        print("\n=== SBERT SEMANTIC SEARCH TESTS ===")
        for q in queries:
            print(f"\nQuery: '{q}'")
            results = await search_parts_semantic(q, db, top_k=2, min_score=0.25)
            for r in results:
                print(f"  -> Match: {r['name']} ({r.get('brand')})")
                print(f"     Score: {r.get('similarity_score')} | Category: {r.get('category')} | Price: INR {r.get('price_min')}-{r.get('price_max')}")

        print("\n=== SBERT ENRICHMENT TEST ===")
        # Test AI suggested vague parts
        ai_parts = [
            {"name": "sparking plug", "part_number": None},
            {"name": "front friction brake pads", "part_number": None},
            {"name": "drive belt rubber", "part_number": None},
        ]
        enriched = await enrich_parts(ai_parts, db)
        for ep in enriched:
            print(f"AI input: '{ep['name']}' -> DB Match: '{ep.get('name')}' (Type: {ep.get('match_type')}, Score: {ep.get('similarity_score')}, Source: {ep.get('source')})")


if __name__ == "__main__":
    asyncio.run(main())
