"""Memory orchestrator — thin coordinator routing to independent layers.

Does not own logic. Delegates to episodic, semantic, procedural, graph,
retrieval, extraction, and working memory modules.

Uses session factory pattern (cross-cutting fix I8): creates a fresh
database session per operation instead of holding a single long-lived session.
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from typing import Optional

from nobla.memory.working import WorkingMemory
from nobla.memory.episodic import EpisodicMemory
from nobla.memory.extraction import ExtractionEngine

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

        # Semantic, procedural, graph — initialized in Phase 2A-2
        self._semantic = None
        self._procedural = None
        self._graph = None
        self._retrieval = None

    def _episodic(self, session) -> EpisodicMemory:
        """Create an EpisodicMemory bound to the given session."""
        return EpisodicMemory(db_session=session)

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

        # 4. Async embedding (fire-and-forget) — added in Phase 2A-2
        # asyncio.create_task(self._embed_async(msg, content))

        return {
            "message_id": str(msg.id),
            "keywords": extraction["keywords"],
            "entities": extraction["entities"],
        }

    async def get_memory_context(
        self,
        user_id: uuid_lib.UUID,
        query: str,
    ) -> str:
        """Retrieve relevant memories and format as context block.

        Uses hybrid retrieval (semantic + keyword + graph) when available.
        Falls back to empty string if no retrieval layers are initialized.
        """
        if self._retrieval is None:
            return ""

        # Retrieval pipeline delegates to semantic, keyword, graph sources
        # Implemented in Phase 2A-2 Task 10
        return ""

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
