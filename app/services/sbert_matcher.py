"""
app/services/sbert_matcher.py
──────────────────────────────
Sentence-BERT (SBERT) Semantic Matching Engine for Spare Parts.

Uses sentence-transformers (all-MiniLM-L6-v2) to provide:
1. Dense semantic search across spare parts descriptions, compatibility & fault symptoms.
2. Intelligent matching of user queries and AI suggestions to actual inventory items,
   even when exact keywords or part numbers differ.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spare_part import SparePart

logger = logging.getLogger(__name__)

# Default model: lightweight, fast (CPU friendly), high semantic accuracy
DEFAULT_SBERT_MODEL = "all-MiniLM-L6-v2"


class SBERTEngine:
    """Singleton service for SBERT semantic embedding & part retrieval."""

    def __init__(self, model_name: str = DEFAULT_SBERT_MODEL):
        self.model_name = model_name
        self._model = None
        self._load_lock = asyncio.Lock()

        # Cache of part embeddings
        self._part_ids: list[str] = []
        self._part_records: list[SparePart] = []
        self._embeddings = None  # torch.Tensor of shape (N, dim)
        self._last_index_time: float = 0.0
        self._cache_ttl: float = 300.0  # Refresh every 5 minutes if requested

    def _get_or_load_model(self):
        """Synchronously load model if not already in memory."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading SBERT model '%s'...", self.model_name)
                t0 = time.time()
                self._model = SentenceTransformer(self.model_name)
                logger.info(
                    "SBERT model '%s' loaded in %.2f seconds.",
                    self.model_name,
                    time.time() - t0,
                )
            except Exception as exc:
                logger.error("Failed to load SBERT model: %s", exc)
                raise
        return self._model

    def build_part_corpus_text(self, part: SparePart) -> str:
        """
        Build rich semantic representation for a spare part including
        name, category, brand, compatible models, and common fault symptoms.
        """
        parts_text = [part.name]
        if part.category:
            parts_text.append(f"Category: {part.category}")
        if part.brand:
            parts_text.append(f"Brand: {part.brand}")
        if part.compatible_with and isinstance(part.compatible_with, list):
            parts_text.append(f"Compatible vehicles: {', '.join(part.compatible_with)}")
        if part.fault_keywords and isinstance(part.fault_keywords, list):
            parts_text.append(f"Fault symptoms: {', '.join(part.fault_keywords)}")
        if part.description:
            parts_text.append(f"Description: {part.description}")
        return " | ".join(parts_text)

    async def ensure_index(self, db: AsyncSession, force_refresh: bool = False) -> None:
        """Ensure parts embeddings index is built and fresh."""
        now = time.time()
        if (
            not force_refresh
            and self._embeddings is not None
            and (now - self._last_index_time) < self._cache_ttl
        ):
            return

        async with self._load_lock:
            # Recheck inside lock
            if (
                not force_refresh
                and self._embeddings is not None
                and (now - self._last_index_time) < self._cache_ttl
            ):
                return

            stmt = select(SparePart).where(SparePart.in_stock.is_(True))
            result = await db.execute(stmt)
            parts = list(result.scalars().all())

            if not parts:
                logger.warning("No spare parts found in DB to index for SBERT.")
                self._part_ids = []
                self._part_records = []
                self._embeddings = None
                self._last_index_time = now
                return

            corpus_texts = [self.build_part_corpus_text(p) for p in parts]

            # Offload heavy embedding computation to thread
            loop = asyncio.get_running_loop()

            def _encode_corpus():
                model = self._get_or_load_model()
                return model.encode(
                    corpus_texts,
                    convert_to_tensor=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )

            embeddings = await loop.run_in_executor(None, _encode_corpus)

            self._part_records = parts
            self._part_ids = [str(p.id) for p in parts]
            self._embeddings = embeddings
            self._last_index_time = now
            logger.info("SBERT indexed %d spare parts successfully.", len(parts))

    def invalidate_cache(self) -> None:
        """Clear the cached embeddings index."""
        self._embeddings = None
        self._last_index_time = 0.0

    async def semantic_search(
        self,
        query: str,
        db: AsyncSession,
        top_k: int = 5,
        min_score: float = 0.25,
    ) -> list[dict[str, Any]]:
        """
        Perform dense semantic search for a query string (symptom, description, or part name)
        against all indexed parts in the catalogue.
        """
        if not query or not query.strip():
            return []

        await self.ensure_index(db)
        if self._embeddings is None or len(self._part_records) == 0:
            return []

        loop = asyncio.get_running_loop()

        def _compute_similarity():
            import torch
            from sentence_transformers import util

            model = self._get_or_load_model()
            query_embedding = model.encode(
                query.strip(),
                convert_to_tensor=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )

            # Cosine similarity between normalized vectors
            scores = util.cos_sim(query_embedding, self._embeddings)[0]
            top_scores, top_indices = torch.topk(
                scores, k=min(top_k, len(self._part_records))
            )
            return top_scores.tolist(), top_indices.tolist()

        scores, indices = await loop.run_in_executor(None, _compute_similarity)

        results: list[dict[str, Any]] = []
        for score, idx in zip(scores, indices):
            if score < min_score:
                continue
            part = self._part_records[idx]
            results.append(
                {
                    "id": str(part.id),
                    "part_number": part.part_number,
                    "name": part.name,
                    "category": part.category,
                    "brand": part.brand,
                    "compatible_with": part.compatible_with,
                    "fault_keywords": part.fault_keywords,
                    "price_min": part.price_min,
                    "price_max": part.price_max,
                    "currency": part.currency,
                    "in_stock": part.in_stock,
                    "similarity_score": round(float(score), 4),
                }
            )

        return results

    async def match_ai_part(
        self,
        ai_part_name: str,
        db: AsyncSession,
        min_score: float = 0.40,
    ) -> tuple[SparePart | None, float]:
        """
        Attempt to match an AI suggested part name to an existing catalogue item
        using SBERT semantic similarity.
        """
        if not ai_part_name:
            return None, 0.0

        results = await self.semantic_search(
            query=ai_part_name,
            db=db,
            top_k=1,
            min_score=min_score,
        )

        if not results:
            return None, 0.0

        top_match = results[0]
        # Find matching SparePart record
        for part in self._part_records:
            if str(part.id) == top_match["id"]:
                return part, top_match["similarity_score"]

        return None, 0.0


# Global singleton instance
sbert_engine = SBERTEngine()
