"""
Procurement Flow — Tender Embedding Service
Uses Ollama nomic-embed-text for semantic tender search and matching.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np

logger = logging.getLogger("procureflow.embeddings")


class TenderEmbeddingService:
    """
    Semantic search for tenders using Ollama embeddings (nomic-embed-text).
    Converts tender descriptions to vectors for similarity matching.
    """

    def __init__(self):
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = "nomic-embed-text:latest"
        self.index_path = os.getenv("TENDERAI_DIR", "./runtime") + "/embeddings"
        self._index: Dict[str, Any] = {}  # tender_id -> {embedding, metadata}

    # ── Embedding Generation ────────────────────────────────────────────

    def _make_embed_text(self, tender: Dict[str, Any]) -> str:
        """Create a searchable text representation of a tender."""
        parts = [
            f"Title: {tender.get('title', '')}",
            f"Entity: {tender.get('procuring_entity', '')}",
            f"Description: {tender.get('title', '')}",
            f"Nature: {tender.get('detected_nature', tender.get('nature', ''))}",
            f"Category: {tender.get('category', '')}",
        ]
        return " | ".join(parts)

    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding vector from Ollama."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{self.ollama_url}/api/embed",
                    json={"model": self.model, "input": text},
                )
                if r.status_code == 200:
                    data = r.json()
                    embeddings = data.get("embeddings", [])
                    if embeddings:
                        return embeddings[0]
                logger.warning(f"Embedding failed: {r.status_code}")
                return None
        except Exception as e:
            logger.warning(f"Embedding error: {e}")
            return None

    # ── Index Management ───────────────────────────────────────────────

    def _index_path(self) -> Path:
        p = Path(self.index_path)
        p.mkdir(parents=True, exist_ok=True)
        return p / "tender_embeddings.json"

    def save_index(self):
        """Save embedding index to disk."""
        fp = self._index_path()
        # Store only metadata (embeddings are regenerated on load for space)
        index_data = {
            "tenders": {
                tid: meta for tid, meta in self._index.items()
            },
        }
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(index_data, f, indent=2, default=str, ensure_ascii=False)
        logger.info(f"Embedding index saved: {len(self._index)} tenders")

    def load_index(self):
        """Load embedding index from disk."""
        fp = self._index_path()
        if fp.exists():
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                self._index = data.get("tenders", {})
                logger.info(f"Embedding index loaded: {len(self._index)} tenders")
            except Exception as e:
                logger.warning(f"Failed to load index: {e}")
                self._index = {}

    async def index_tender(self, tender: Dict[str, Any]) -> bool:
        """Generate embedding for a tender and add to index."""
        tid = tender.get("tender_id", "")
        if not tid:
            return False

        text = self._make_embed_text(tender)
        emb = await self.get_embedding(text)
        if emb is None:
            return False

        self._index[tid] = {
            "embedding": emb,
            "metadata": {
                "tender_id": tid,
                "title": (tender.get("title", "") or "")[:200],
                "entity": (tender.get("procuring_entity", "") or "")[:100],
                "deadline": tender.get("deadline", ""),
                "estimated_value_bdt": tender.get("estimated_value_bdt", 0),
                "nature": tender.get("detected_nature", tender.get("nature", "")),
                "status": tender.get("status", ""),
            },
        }
        return True

    async def index_tenders(self, tenders: List[Dict[str, Any]]) -> int:
        """Index multiple tenders."""
        count = 0
        for t in tenders:
            if await self.index_tender(t):
                count += 1
        self.save_index()
        return count

    # ── Semantic Search ────────────────────────────────────────────────

    def cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        arr_a = np.array(a, dtype=np.float32)
        arr_b = np.array(b, dtype=np.float32)
        norm_a = np.linalg.norm(arr_a)
        norm_b = np.linalg.norm(arr_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(arr_a, arr_b) / (norm_a * norm_b))

    async def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search tenders by semantic similarity to query."""
        query_emb = await self.get_embedding(query)
        if query_emb is None:
            return []

        results = []
        for tid, entry in self._index.items():
            if "embedding" not in entry:
                continue
            score = self.cosine_similarity(query_emb, entry["embedding"])
            results.append({
                "tender_id": tid,
                "score": round(score, 4),
                **entry["metadata"],
            })

        results.sort(key=lambda x: -x["score"])
        return results[:top_k]

    async def find_similar(self, tender_id: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Find tenders similar to a given tender by ID."""
        if tender_id not in self._index:
            return []
        entry = self._index[tender_id]
        if "embedding" not in entry:
            return []

        query_emb = entry["embedding"]
        results = []
        for tid, e in self._index.items():
            if tid == tender_id or "embedding" not in e:
                continue
            score = self.cosine_similarity(query_emb, e["embedding"])
            results.append({
                "tender_id": tid,
                "score": round(score, 4),
                **e["metadata"],
            })

        results.sort(key=lambda x: -x["score"])
        return results[:top_k]

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        return {
            "total_indexed": len(self._index),
            "model": self.model,
            "index_path": str(self._index_path()),
        }


tender_embedding_service = TenderEmbeddingService()
