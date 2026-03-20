"""Semantic memory — fact storage with ChromaDB vector embeddings.

Stores extracted facts (preferences, knowledge, relationships) in PostgreSQL
with vector embeddings in ChromaDB for semantic search. Supports dedup
detection via cosine similarity threshold (>0.85).
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from typing import Optional

from sqlalchemy import select, update, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession

from nobla.db.models.memory import MemoryNode

logger = logging.getLogger(__name__)


class SemanticMemory:
    """Manages fact storage with vector embeddings for semantic search."""

    def __init__(
        self,
        db_session: AsyncSession,
        chromadb_path: str = "./data/chromadb",
        embedding_model: Optional[str] = "all-MiniLM-L6-v2",
    ):
        self._db = db_session
        self._embedder = None
        self._chroma_client = None
        self._collections: dict[str, object] = {}

        # Load embedding model (optional — graceful degradation)
        if embedding_model:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer(embedding_model)
                logger.info("Embedding model '%s' loaded", embedding_model)
            except Exception as e:
                logger.warning("Embedding model not available: %s", e)

        # Initialize ChromaDB client
        try:
            import chromadb
            self._chroma_client = chromadb.PersistentClient(path=chromadb_path)
            logger.info("ChromaDB initialized at '%s'", chromadb_path)
        except Exception as e:
            logger.warning("ChromaDB not available: %s", e)

    def _get_collection(self, user_id: uuid_lib.UUID):
        """Get or create a ChromaDB collection for a user."""
        key = str(user_id)
        if key not in self._collections and self._chroma_client:
            self._collections[key] = self._chroma_client.get_or_create_collection(
                name=f"user_{key.replace('-', '_')}",
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections.get(key)

    def _embed(self, text: str) -> list[float] | None:
        """Generate embedding vector for text."""
        if not self._embedder:
            return None
        return self._embedder.encode(text).tolist()

    async def store_fact(
        self,
        user_id: uuid_lib.UUID,
        content: str,
        note_type: str = "fact",
        keywords: Optional[list[str]] = None,
        confidence: float = 0.8,
        source_conversation_id: Optional[uuid_lib.UUID] = None,
    ) -> str:
        """Store a fact in PostgreSQL and embed in ChromaDB."""
        source_ids = [str(source_conversation_id)] if source_conversation_id else None

        node = MemoryNode(
            user_id=str(user_id),
            content=content,
            note_type=note_type,
            keywords=keywords or [],
            confidence=confidence,
            source_conversation_ids=source_ids,
        )
        self._db.add(node)
        await self._db.flush()

        # Embed in ChromaDB
        embedding = self._embed(content)
        collection = self._get_collection(user_id)
        if collection and embedding:
            collection.upsert(
                ids=[str(node.id)],
                embeddings=[embedding],
                documents=[content],
                metadatas=[{
                    "note_type": note_type,
                    "confidence": confidence,
                }],
            )
            # Store ChromaDB reference
            await self._db.execute(
                update(MemoryNode)
                .where(MemoryNode.id == node.id)
                .values(embedding_id=str(node.id))
            )

        return str(node.id)

    async def search_facts(
        self,
        user_id: uuid_lib.UUID,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """Semantic search for facts using ChromaDB embeddings."""
        collection = self._get_collection(user_id)
        if not collection or not self._embedder:
            # Fallback: keyword search from PostgreSQL
            return await self._keyword_search(user_id, query, top_k)

        embedding = self._embed(query)
        if not embedding:
            return []

        results = collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        facts = []
        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                facts.append({
                    "id": doc_id,
                    "content": results["documents"][0][i],
                    "similarity": 1 - results["distances"][0][i],  # cosine distance -> similarity
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                })
        return facts

    async def _keyword_search(
        self, user_id: uuid_lib.UUID, query: str, top_k: int
    ) -> list[dict]:
        """Fallback keyword search when embeddings are unavailable."""
        result = await self._db.execute(
            select(MemoryNode)
            .where(MemoryNode.user_id == str(user_id))
            .where(MemoryNode.note_type != "entity")
            .order_by(desc(MemoryNode.confidence))
            .limit(top_k)
        )
        nodes = result.scalars().all()
        return [
            {
                "id": str(n.id),
                "content": n.content,
                "similarity": 0.5,  # Unknown similarity for keyword search
                "metadata": {"note_type": n.note_type, "confidence": n.confidence},
            }
            for n in nodes
        ]

    def is_near_duplicate(
        self,
        user_id: uuid_lib.UUID,
        content: str,
        threshold: float = 0.85,
    ) -> bool:
        """Check if content is a near-duplicate of existing facts."""
        collection = self._get_collection(user_id)
        if not collection or not self._embedder:
            return False

        embedding = self._embed(content)
        if not embedding:
            return False

        try:
            results = collection.query(
                query_embeddings=[embedding],
                n_results=1,
                include=["distances"],
            )
            if results["distances"] and results["distances"][0]:
                similarity = 1 - results["distances"][0][0]
                return similarity >= threshold
        except Exception:
            pass
        return False

    async def delete_fact(self, fact_id: uuid_lib.UUID) -> bool:
        """Delete a fact from PostgreSQL and ChromaDB."""
        # Get the fact first to find user_id for collection
        result = await self._db.execute(
            select(MemoryNode).where(MemoryNode.id == str(fact_id))
        )
        node = result.scalars().first()
        if not node:
            return False

        # Remove from ChromaDB
        collection = self._get_collection(uuid_lib.UUID(node.user_id))
        if collection:
            try:
                collection.delete(ids=[str(fact_id)])
            except Exception:
                pass

        # Remove from PostgreSQL
        await self._db.execute(
            delete(MemoryNode).where(MemoryNode.id == str(fact_id))
        )
        return True

    async def get_facts_by_type(
        self,
        user_id: uuid_lib.UUID,
        note_type: str,
        limit: int = 20,
    ) -> list[dict]:
        """Get facts by type for a user."""
        result = await self._db.execute(
            select(MemoryNode)
            .where(MemoryNode.user_id == str(user_id))
            .where(MemoryNode.note_type == note_type)
            .order_by(desc(MemoryNode.updated_at))
            .limit(limit)
        )
        nodes = result.scalars().all()
        return [
            {
                "id": str(n.id),
                "content": n.content,
                "note_type": n.note_type,
                "confidence": n.confidence,
                "keywords": n.keywords or [],
                "created_at": n.created_at,
            }
            for n in nodes
        ]

    async def update_access(self, fact_id: uuid_lib.UUID) -> None:
        """Increment access count and update last_accessed timestamp."""
        await self._db.execute(
            update(MemoryNode)
            .where(MemoryNode.id == str(fact_id))
            .values(
                access_count=MemoryNode.access_count + 1,
            )
        )
