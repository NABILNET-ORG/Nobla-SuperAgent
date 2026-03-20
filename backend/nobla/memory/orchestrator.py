"""Memory orchestrator — thin coordinator routing to independent layers.

Does not own logic. Delegates to episodic, semantic, procedural, graph,
retrieval, extraction, and working memory modules.

Uses session factory pattern (cross-cutting fix I8): creates a fresh
database session per operation instead of holding a single long-lived session.
"""

from __future__ import annotations

import asyncio
import logging
import uuid as uuid_lib
from typing import Optional

from nobla.memory.working import WorkingMemory
from nobla.memory.episodic import EpisodicMemory
from nobla.memory.extraction import ExtractionEngine
from nobla.memory.semantic import SemanticMemory
from nobla.memory.graph_builder import KnowledgeGraphBuilder
from nobla.memory.graph_queries import GraphQueries
from nobla.memory.retrieval import RetrievalPipeline
from nobla.memory.retrieval_sources import SemanticSource, GraphSource

logger = logging.getLogger(__name__)


class MemoryOrchestrator:
    """Coordinates all memory layers. Injected into gateway at startup."""

    def __init__(self, session_factory, settings):
        self._session_factory = session_factory
        self._settings = settings.memory

        # Extraction engine is stateless (no DB needed)
        self._extraction = ExtractionEngine(
            spacy_model=self._settings.spacy_model
        )

        # Working memory: one per active conversation (in-process, no DB)
        self._working_memories: dict[uuid_lib.UUID, WorkingMemory] = {}

        # Knowledge graph (in-memory, loaded per user on first access)
        self._user_graphs: dict[uuid_lib.UUID, KnowledgeGraphBuilder] = {}

        # Embedding model name for async embedding
        self._embedding_model = self._settings.embedding_model
        self._chromadb_path = self._settings.chromadb_path

    def _episodic(self, session) -> EpisodicMemory:
        """Create an EpisodicMemory bound to the given session."""
        return EpisodicMemory(db_session=session)

    def _semantic(self, session) -> SemanticMemory:
        """Create a SemanticMemory bound to the given session."""
        return SemanticMemory(
            db_session=session,
            chromadb_path=self._chromadb_path,
            embedding_model=self._embedding_model,
        )

    def _get_graph(self, user_id: uuid_lib.UUID) -> KnowledgeGraphBuilder:
        """Get or create the in-memory graph for a user."""
        if user_id not in self._user_graphs:
            self._user_graphs[user_id] = KnowledgeGraphBuilder()
        return self._user_graphs[user_id]

    def get_working_memory(self, conversation_id: uuid_lib.UUID) -> WorkingMemory:
        """Get or create working memory for a conversation."""
        if conversation_id not in self._working_memories:
            self._working_memories[conversation_id] = WorkingMemory(
                max_tokens=self._settings.max_context_tokens
            )
        return self._working_memories[conversation_id]

    async def process_message(
        self,
        conversation_id: uuid_lib.UUID,
        role: str,
        content: str,
        **kwargs,
    ) -> dict:
        """Hot path: store message + lightweight extraction. No LLM calls."""
        # 1. Extract keywords + entities (sync, <30ms)
        extraction = self._extraction.extract(content)

        # 2. Store in episodic memory (new session per operation)
        async with self._session_factory() as session:
            episodic = self._episodic(session)
            msg = await episodic.store_message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                metadata=extraction,
                **kwargs,
            )
            await session.commit()

        # 3. Update working memory
        wm = self.get_working_memory(conversation_id)
        wm.add_message(role, content)

        # 4. Async embedding (fire-and-forget)
        if self._embedding_model:
            asyncio.create_task(self._embed_async(str(msg.id), content))

        return {
            "message_id": str(msg.id),
            "keywords": extraction["keywords"],
            "entities": extraction["entities"],
        }

    async def _embed_async(self, message_id: str, content: str) -> None:
        """Fire-and-forget: embed message content in ChromaDB."""
        try:
            async with self._session_factory() as session:
                semantic = self._semantic(session)
                embedding = semantic._embed(content)
                if embedding:
                    collection = semantic._get_collection(
                        uuid_lib.UUID("00000000-0000-0000-0000-000000000000")
                    )
                    if collection:
                        collection.upsert(
                            ids=[f"msg:{message_id}"],
                            embeddings=[embedding],
                            documents=[content],
                            metadatas=[{"type": "message"}],
                        )
        except Exception as e:
            logger.warning("Async embedding failed: %s", e)

    async def get_memory_context(
        self,
        user_id: uuid_lib.UUID,
        query: str,
    ) -> str:
        """Retrieve relevant memories and format as context block.

        Uses hybrid retrieval (semantic + graph) when available.
        """
        async with self._session_factory() as session:
            # Build retrieval sources
            sources = []
            semantic = self._semantic(session)
            sources.append(SemanticSource(semantic))

            graph = self._get_graph(user_id)
            if graph.entity_count > 0:
                sources.append(GraphSource(GraphQueries(graph)))

            pipeline = RetrievalPipeline(sources=sources)
            results = await pipeline.query(
                user_id=str(user_id),
                query_text=query,
                top_k=self._settings.retrieval_top_k,
            )
            return pipeline.format_context(results)

    async def trigger_warm_path(
        self,
        conversation_id: uuid_lib.UUID,
        user_id: uuid_lib.UUID,
    ) -> None:
        """Trigger warm path consolidation for a conversation.

        Called on conversation pause/switch. Extracts entities into the
        knowledge graph. Full LLM-based consolidation added in Task 13.
        """
        try:
            async with self._session_factory() as session:
                episodic = self._episodic(session)
                messages = await episodic.get_messages(conversation_id, limit=50)

                graph = self._get_graph(user_id)
                for msg in messages:
                    if msg.entities_extracted:
                        entities = msg.entities_extracted
                        if isinstance(entities, list):
                            for ent in entities:
                                graph.add_entity(
                                    ent.get("text", ""),
                                    entity_type=ent.get("type", "UNKNOWN"),
                                )
        except Exception as e:
            logger.warning("Warm path failed: %s", e)

    # --- Conversation lifecycle ---

    async def create_conversation(
        self, user_id: uuid_lib.UUID, title: Optional[str] = None
    ):
        async with self._session_factory() as session:
            result = await self._episodic(session).create_conversation(user_id, title)
            await session.commit()
            return result

    async def list_conversations(
        self, user_id: uuid_lib.UUID, limit: int = 20, offset: int = 0
    ):
        async with self._session_factory() as session:
            return await self._episodic(session).list_conversations(user_id, limit, offset)

    async def get_messages(
        self, conversation_id: uuid_lib.UUID, limit: int = 50
    ):
        async with self._session_factory() as session:
            return await self._episodic(session).get_messages(conversation_id, limit)

    async def archive_conversation(self, conversation_id: uuid_lib.UUID):
        async with self._session_factory() as session:
            result = await self._episodic(session).archive_conversation(conversation_id)
            await session.commit()
            return result

    async def rename_conversation(
        self, conversation_id: uuid_lib.UUID, title: str
    ):
        async with self._session_factory() as session:
            result = await self._episodic(session).rename_conversation(conversation_id, title)
            await session.commit()
            return result

    async def search_conversations(
        self, user_id: uuid_lib.UUID, query: str, limit: int = 10
    ):
        async with self._session_factory() as session:
            return await self._episodic(session).search_conversations(user_id, query, limit)

    def release_working_memory(self, conversation_id: uuid_lib.UUID) -> None:
        """Release working memory for a conversation (on switch/close)."""
        self._working_memories.pop(conversation_id, None)
