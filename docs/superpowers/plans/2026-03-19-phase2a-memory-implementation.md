# Phase 2A: Memory System + Conversation Persistence — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 5-layer memory engine that makes Nobla remember, learn, and persist conversations across sessions.

**Architecture:** Layered pipeline with independent modules per memory layer, coordinated by a thin orchestrator. Three processing paths: hot (real-time, no LLM), warm (post-conversation, cheap LLM), cold (nightly maintenance). Hybrid retrieval: 0.7 semantic + 0.3 BM25 + lightweight re-ranking.

**Tech Stack:** Python 3.12+, FastAPI, PostgreSQL (asyncpg/SQLAlchemy), ChromaDB, NetworkX, spaCy (en_core_web_sm), sentence-transformers, APScheduler, Flutter/Dart/Riverpod.

**Spec:** `docs/superpowers/specs/2026-03-19-phase2a-memory-conversation-design.md`

---

## File Structure

### Backend — New Files
```
backend/nobla/memory/
├── __init__.py
├── orchestrator.py       # Thin coordinator — routes to layers (~200 lines)
├── working.py            # Context window management (~250 lines)
├── episodic.py           # Conversation CRUD + full-text search (~300 lines)
├── semantic.py           # Fact storage + ChromaDB embeddings (~300 lines)
├── procedural.py         # Bayesian workflow learning (~250 lines)
├── graph_builder.py      # Entity/relationship CRUD (~200 lines)
├── graph_queries.py      # Graph traversal + search (~150 lines)
├── graph_persistence.py  # NetworkX <-> PostgreSQL serialization (~200 lines)
├── retrieval.py          # Merge + re-rank orchestration (~200 lines)
├── retrieval_sources.py  # ChromaDB, BM25, graph query backends (~250 lines)
├── extraction.py         # spaCy NER + TF-IDF keywords (~200 lines)
├── consolidation.py      # Warm path LLM extraction (~300 lines)
└── maintenance.py        # Cold path decay/dedup/prune (~200 lines)
```

### Backend — Modified Files
```
backend/nobla/gateway/app.py           # Add MemoryOrchestrator to lifespan (lines 42-128)
backend/nobla/gateway/websocket.py     # Integrate memory into chat.send (lines 389-407)
backend/nobla/db/models/memory.py      # Add new columns to existing models
backend/nobla/db/models/conversations.py # Add summary, topics, parent_message_id
backend/nobla/config/settings.py       # Add memory config section (lines 35-38)
backend/pyproject.toml                 # Add spacy, chromadb, sentence-transformers
backend/config.yaml                    # Add memory configuration
```

### Backend — New Test Files
```
backend/tests/
├── test_working_memory.py
├── test_episodic.py
├── test_semantic.py
├── test_procedural.py
├── test_graph.py
├── test_retrieval.py
├── test_extraction.py
├── test_consolidation.py
├── test_maintenance.py
├── test_orchestrator.py
├── integration/
│   ├── test_memory_flow.py
│   ├── test_chat_send_memory.py
│   └── test_conversation_lifecycle.py
```

### Flutter — New Files
```
app/lib/features/conversations/
├── providers/
│   └── conversation_provider.dart    # ConversationListNotifier
├── screens/
│   └── conversation_drawer.dart      # Sidebar drawer
└── widgets/
    └── conversation_tile.dart        # Single conversation item

app/lib/features/memory/
├── providers/
│   └── memory_provider.dart          # MemoryStatsNotifier, MemorySearchNotifier
├── screens/
│   └── memory_viewer_screen.dart     # Facts/entities/procedures tabs
└── widgets/
    ├── fact_card.dart
    ├── entity_card.dart
    └── procedure_card.dart

app/lib/shared/models/
├── conversation.dart                 # Conversation model
├── memory_fact.dart                  # MemoryFact model
├── memory_entity.dart                # MemoryEntity model
└── memory_stats.dart                 # MemoryStats model
```

### Flutter — Modified Files
```
app/lib/core/routing/app_router.dart              # Add memory route
app/lib/features/chat/screens/chat_screen.dart     # Add drawer toggle
app/lib/features/chat/providers/chat_provider.dart # Add conversation switching
app/lib/features/dashboard/screens/dashboard_screen.dart # Add memory stats card
app/lib/main.dart                                  # Add new providers
```

---

## Phase 2A-1: Memory Foundation (Tasks 1-8)

### Task 1: Add Backend Dependencies

**Files:**
- Modify: `backend/pyproject.toml:14-33`
- Modify: `backend/config.yaml`
- Modify: `backend/nobla/config/settings.py:35-38`

- [ ] **Step 1: Add new dependencies to pyproject.toml**

Add to the `dependencies` array after line 33:

```toml
"chromadb>=0.5.0",
"sentence-transformers>=3.0.0",
"spacy>=3.7.0",
"scikit-learn>=1.5.0",
"scipy>=1.14.0",
```

- [ ] **Step 2: Update memory settings**

In `backend/nobla/config/settings.py`, replace the MemorySettings class (lines 35-38) with:

```python
class MemorySettings(BaseModel):
    context_window_messages: int = 20
    max_context_tokens: int = 8000
    store_embeddings: bool = True
    chromadb_path: str = "./data/chromadb"
    embedding_model: str = "all-MiniLM-L6-v2"
    spacy_model: str = "en_core_web_sm"
    warm_path_idle_timeout_minutes: int = 5
    cold_path_schedule_hour: int = 3
    memory_retention_days: int = 90
    retrieval_top_k: int = 5
    semantic_weight: float = 0.7
    keyword_weight: float = 0.3
```

- [ ] **Step 3: Update config.yaml**

Add to `backend/config.yaml`:

```yaml
memory:
  context_window_messages: 20
  max_context_tokens: 8000
  store_embeddings: true
  chromadb_path: "./data/chromadb"
  embedding_model: "all-MiniLM-L6-v2"
  spacy_model: "en_core_web_sm"
  warm_path_idle_timeout_minutes: 5
  cold_path_schedule_hour: 3
  memory_retention_days: 90
  retrieval_top_k: 5
```

- [ ] **Step 4: Install dependencies**

Run: `cd backend && pip install -e ".[dev]" && python -m spacy download en_core_web_sm`

- [ ] **Step 5: Verify installation**

Run: `python -c "import chromadb; import spacy; import sentence_transformers; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/config.yaml backend/nobla/config/settings.py
git commit -m "deps: add chromadb, spacy, sentence-transformers for Phase 2A memory"
```

---

### Task 2: Database Schema Migrations

**Files:**
- Modify: `backend/nobla/db/models/conversations.py:12-94`
- Modify: `backend/nobla/db/models/memory.py:14-134`

- [ ] **Step 1: Write test for new conversation columns**

Create `backend/tests/test_memory_models.py`:

```python
import pytest
from nobla.db.models.conversations import Conversation, Message

def test_conversation_has_summary_field():
    """Verify summary column exists on Conversation model."""
    assert hasattr(Conversation, 'summary')

def test_conversation_has_topics_field():
    assert hasattr(Conversation, 'topics')

def test_conversation_has_message_count_field():
    assert hasattr(Conversation, 'message_count')

def test_message_has_parent_message_id():
    assert hasattr(Message, 'parent_message_id')

def test_message_has_entities_extracted():
    assert hasattr(Message, 'entities_extracted')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_memory_models.py -v`
Expected: FAIL — attributes don't exist yet

- [ ] **Step 3: Add new columns to Conversation model**

In `backend/nobla/db/models/conversations.py`, add after `is_archived` (around line 40):

```python
    summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    topics: Mapped[Optional[list]] = mapped_column(ARRAY(String), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, server_default="0")
```

- [ ] **Step 4: Add new columns to Message model**

In `backend/nobla/db/models/conversations.py`, add after `memory_keywords` (around line 89):

```python
    parent_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id"),
        nullable=True
    )
    entities_extracted: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
```

- [ ] **Step 5: Add new columns to MemoryNode model**

In `backend/nobla/db/models/memory.py`, add after `metadata_` (around line 47):

```python
    source_conversation_ids: Mapped[Optional[list]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )
    decay_factor: Mapped[float] = mapped_column(Float, server_default="1.0")
```

- [ ] **Step 6: Add new columns to Procedure model**

In `backend/nobla/db/models/memory.py`, add after `metadata_` (around line 115):

```python
    beta_success: Mapped[float] = mapped_column(Float, server_default="2.0")
    beta_failure: Mapped[float] = mapped_column(Float, server_default="1.0")
    trigger_context: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_triggered: Mapped[Optional[str]] = mapped_column(String, nullable=True)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_memory_models.py -v`
Expected: PASS

- [ ] **Step 8: Create Alembic migration**

Run: `cd backend && alembic revision --autogenerate -m "phase2a_memory_columns_and_indexes"`

- [ ] **Step 9: Add GIN indexes to the migration**

Edit the generated migration file to add after the column additions:

```python
# Full-text search indexes (BM25 via GIN)
op.execute("CREATE INDEX IF NOT EXISTS idx_messages_content_fts ON messages USING GIN (to_tsvector('english', content))")
op.execute("CREATE INDEX IF NOT EXISTS idx_conversations_summary_fts ON conversations USING GIN (to_tsvector('english', summary))")
op.execute("CREATE INDEX IF NOT EXISTS idx_conversations_topics ON conversations USING GIN (topics)")
# Memory retrieval indexes
op.execute("CREATE INDEX IF NOT EXISTS idx_memory_nodes_retrieval ON memory_nodes (user_id, note_type, confidence DESC)")
op.execute("CREATE INDEX IF NOT EXISTS idx_memory_links_source ON memory_links (source_id, link_type)")
op.execute("CREATE INDEX IF NOT EXISTS idx_memory_links_target ON memory_links (target_id, link_type)")
```

- [ ] **Step 10: Run migration**

Run: `cd backend && alembic upgrade head`
Expected: Migration applies successfully

- [ ] **Step 11: Commit**

```bash
git add backend/nobla/db/ backend/tests/test_memory_models.py
git commit -m "schema: add Phase 2A columns, GIN indexes, and Alembic migration"
```

---

### Task 3: Extraction Module (spaCy NER + TF-IDF)

**Files:**
- Create: `backend/nobla/memory/__init__.py`
- Create: `backend/nobla/memory/extraction.py`
- Create: `backend/tests/test_extraction.py`

- [ ] **Step 1: Create memory package**

Create `backend/nobla/memory/__init__.py`:

```python
"""Nobla Agent 5-layer memory system."""
```

- [ ] **Step 2: Write failing tests for extraction**

Create `backend/tests/test_extraction.py`:

```python
import pytest
from nobla.memory.extraction import ExtractionEngine

@pytest.fixture
def engine():
    return ExtractionEngine(spacy_model=None)  # Graceful: no spaCy

def test_extract_keywords(engine):
    result = engine.extract_keywords("Python is great for machine learning projects")
    assert isinstance(result, list)
    assert len(result) > 0
    assert "python" in [k.lower() for k in result]

def test_extract_entities_without_spacy(engine):
    """When spaCy is not loaded, entities should be empty list."""
    result = engine.extract_entities("Alice works at Google on ProjectX")
    assert isinstance(result, list)

def test_extract_entities_with_spacy():
    engine = ExtractionEngine(spacy_model="en_core_web_sm")
    if engine.nlp is None:
        pytest.skip("spaCy model not available")
    result = engine.extract_entities("Alice works at Google in New York")
    names = [e["text"] for e in result]
    assert "Alice" in names or "Google" in names

def test_extract_all(engine):
    result = engine.extract("Alice loves Python for ML projects")
    assert "keywords" in result
    assert "entities" in result
    assert isinstance(result["keywords"], list)
    assert isinstance(result["entities"], list)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/test_extraction.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 4: Implement extraction engine**

Create `backend/nobla/memory/extraction.py`:

```python
"""Lightweight NER + keyword extraction for the hot path.

No LLM calls. Uses spaCy for NER (optional) and TF-IDF for keywords.
Graceful degradation: if spaCy is not available, skip NER.
"""

from __future__ import annotations

import logging
from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer

logger = logging.getLogger(__name__)


class ExtractionEngine:
    """Extracts entities and keywords from text without LLM calls."""

    ENTITY_TYPE_MAP = {
        "PERSON": "PERSON",
        "ORG": "ORGANIZATION",
        "GPE": "LOCATION",
        "LOC": "LOCATION",
        "DATE": "DATE",
        "PRODUCT": "TOOL",
    }

    def __init__(self, spacy_model: Optional[str] = "en_core_web_sm"):
        self.nlp = None
        if spacy_model:
            try:
                import spacy
                self.nlp = spacy.load(spacy_model)
                logger.info("spaCy model '%s' loaded", spacy_model)
            except Exception as e:
                logger.warning("spaCy not available, NER disabled: %s", e)

        self._tfidf = TfidfVectorizer(
            max_features=20,
            stop_words="english",
            ngram_range=(1, 2),
        )

    def extract_keywords(self, text: str, top_k: int = 10) -> list[str]:
        """Extract top-K keywords using TF-IDF."""
        if not text or len(text.strip()) < 5:
            return []
        try:
            tfidf_matrix = self._tfidf.fit_transform([text])
            feature_names = self._tfidf.get_feature_names_out()
            scores = tfidf_matrix.toarray()[0]
            ranked = sorted(
                zip(feature_names, scores), key=lambda x: x[1], reverse=True
            )
            return [word for word, score in ranked[:top_k] if score > 0]
        except Exception:
            return []

    def extract_entities(self, text: str) -> list[dict]:
        """Extract named entities using spaCy. Returns [] if spaCy unavailable."""
        if self.nlp is None or not text:
            return []
        try:
            doc = self.nlp(text)
            entities = []
            seen = set()
            for ent in doc.ents:
                key = (ent.text.lower(), ent.label_)
                if key not in seen:
                    seen.add(key)
                    entities.append({
                        "text": ent.text,
                        "type": self.ENTITY_TYPE_MAP.get(ent.label_, ent.label_),
                        "start": ent.start_char,
                        "end": ent.end_char,
                    })
            return entities
        except Exception as e:
            logger.warning("NER extraction failed: %s", e)
            return []

    def extract(self, text: str) -> dict:
        """Run full extraction pipeline. Returns keywords + entities."""
        return {
            "keywords": self.extract_keywords(text),
            "entities": self.extract_entities(text),
        }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_extraction.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/nobla/memory/ backend/tests/test_extraction.py
git commit -m "feat: extraction engine with spaCy NER + TF-IDF keywords"
```

---

### Task 4: Episodic Memory Layer

**Files:**
- Create: `backend/nobla/memory/episodic.py`
- Create: `backend/tests/test_episodic.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_episodic.py`:

```python
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from nobla.memory.episodic import EpisodicMemory

@pytest.fixture
def episodic():
    db_session = AsyncMock()
    return EpisodicMemory(db_session=db_session)

@pytest.mark.asyncio
async def test_store_message(episodic):
    msg = await episodic.store_message(
        conversation_id=uuid.uuid4(),
        role="user",
        content="Hello world",
        metadata={"keywords": ["hello"], "entities": []},
    )
    assert msg is not None

@pytest.mark.asyncio
async def test_get_conversation_messages(episodic):
    conv_id = uuid.uuid4()
    messages = await episodic.get_messages(conv_id, limit=10)
    assert isinstance(messages, list)

@pytest.mark.asyncio
async def test_list_conversations(episodic):
    user_id = uuid.uuid4()
    conversations = await episodic.list_conversations(user_id, limit=20, offset=0)
    assert isinstance(conversations, list)

@pytest.mark.asyncio
async def test_create_conversation(episodic):
    conv = await episodic.create_conversation(
        user_id=uuid.uuid4(),
        title="Test conversation",
    )
    assert conv is not None

@pytest.mark.asyncio
async def test_archive_conversation(episodic):
    result = await episodic.archive_conversation(uuid.uuid4())
    assert isinstance(result, bool)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_episodic.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement episodic memory**

Create `backend/nobla/memory/episodic.py`:

```python
"""Episodic memory — conversation storage and full-text search.

Stores raw messages in PostgreSQL with metadata from the hot path.
Supports full-text search via GIN indexes and conversation lifecycle.
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, text, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from nobla.db.models.conversations import Conversation, Message

logger = logging.getLogger(__name__)


class EpisodicMemory:
    """Manages conversation storage and retrieval."""

    def __init__(self, db_session: AsyncSession):
        self._db = db_session

    async def store_message(
        self,
        conversation_id: uuid_lib.UUID,
        role: str,
        content: str,
        metadata: Optional[dict] = None,
        model_used: Optional[str] = None,
        tokens_input: Optional[int] = None,
        tokens_output: Optional[int] = None,
        cost_usd: Optional[float] = None,
        parent_message_id: Optional[uuid_lib.UUID] = None,
    ) -> Message:
        """Store a message in episodic memory (hot path)."""
        meta = metadata or {}
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            model_used=model_used,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=cost_usd,
            parent_message_id=parent_message_id,
            memory_keywords=meta.get("keywords"),
            entities_extracted=meta.get("entities"),
        )
        self._db.add(msg)
        await self._db.flush()

        # Update conversation message count
        await self._db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(message_count=Conversation.message_count + 1)
        )
        return msg

    async def get_messages(
        self,
        conversation_id: uuid_lib.UUID,
        limit: int = 50,
        before: Optional[datetime] = None,
    ) -> list[Message]:
        """Get messages for a conversation, ordered by creation time."""
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(desc(Message.created_at))
            .limit(limit)
        )
        if before:
            query = query.where(Message.created_at < str(before))
        result = await self._db.execute(query)
        return list(reversed(result.scalars().all()))

    async def create_conversation(
        self,
        user_id: uuid_lib.UUID,
        title: Optional[str] = None,
    ) -> Conversation:
        """Create a new conversation."""
        conv = Conversation(user_id=user_id, title=title or "New Conversation")
        self._db.add(conv)
        await self._db.flush()
        return conv

    async def list_conversations(
        self,
        user_id: uuid_lib.UUID,
        limit: int = 20,
        offset: int = 0,
        include_archived: bool = False,
    ) -> list[Conversation]:
        """List conversations for a user, newest first."""
        query = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(desc(Conversation.updated_at))
            .limit(limit)
            .offset(offset)
        )
        if not include_archived:
            query = query.where(Conversation.is_archived == False)  # noqa: E712
        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def archive_conversation(self, conversation_id: uuid_lib.UUID) -> bool:
        """Soft-delete a conversation."""
        result = await self._db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(is_archived=True)
        )
        return result.rowcount > 0

    async def rename_conversation(
        self, conversation_id: uuid_lib.UUID, title: str
    ) -> bool:
        """Update conversation title."""
        result = await self._db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(title=title)
        )
        return result.rowcount > 0

    async def update_summary(
        self, conversation_id: uuid_lib.UUID, summary: str, topics: list[str]
    ) -> None:
        """Set conversation summary and topics (warm path)."""
        await self._db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(summary=summary, topics=topics)
        )

    async def search_conversations(
        self, user_id: uuid_lib.UUID, query: str, limit: int = 10
    ) -> list[dict]:
        """Full-text search across messages using PostgreSQL GIN index."""
        sql = text("""
            SELECT DISTINCT c.id, c.title, c.updated_at, c.summary,
                   ts_rank(to_tsvector('english', m.content),
                           plainto_tsquery('english', :query)) as rank
            FROM conversations c
            JOIN messages m ON m.conversation_id = c.id
            WHERE c.user_id = :user_id
              AND c.is_archived = false
              AND to_tsvector('english', m.content) @@
                  plainto_tsquery('english', :query)
            ORDER BY rank DESC
            LIMIT :limit
        """)
        result = await self._db.execute(
            sql, {"user_id": str(user_id), "query": query, "limit": limit}
        )
        return [dict(row._mapping) for row in result]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_episodic.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/memory/episodic.py backend/tests/test_episodic.py
git commit -m "feat: episodic memory layer — conversation CRUD and full-text search"
```

---

### Task 5: Working Memory (Context Window Manager)

**Files:**
- Create: `backend/nobla/memory/working.py`
- Create: `backend/tests/test_working_memory.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_working_memory.py`:

```python
import pytest
from nobla.memory.working import WorkingMemory

@pytest.fixture
def wm():
    return WorkingMemory(max_tokens=1000)

def test_add_message(wm):
    wm.add_message("user", "Hello world")
    assert len(wm.messages) == 1

def test_get_context_within_budget(wm):
    wm.add_message("user", "Hello")
    wm.add_message("assistant", "Hi there!")
    ctx = wm.get_context(system_prompt="You are Nobla.", memory_block="")
    assert "Hello" in ctx
    assert "Hi there!" in ctx

def test_context_respects_token_budget():
    wm = WorkingMemory(max_tokens=50)
    for i in range(20):
        wm.add_message("user", f"This is message number {i} with some extra words")
    ctx = wm.get_context(system_prompt="System.", memory_block="")
    # Should truncate older messages
    assert "message number 19" in ctx  # Most recent kept

def test_observation_masking(wm):
    wm.add_message("assistant", "Running code...", tool_output="x = 1\n>>> 1")
    ctx = wm.get_context(system_prompt="", memory_block="")
    assert "Running code..." in ctx
    assert ">>> 1" not in ctx  # Tool output masked

def test_clear(wm):
    wm.add_message("user", "test")
    wm.clear()
    assert len(wm.messages) == 0

def test_rolling_summary_placeholder(wm):
    """Rolling summary is set externally by the warm path."""
    wm.set_rolling_summary("Previously discussed Python deployment.")
    ctx = wm.get_context(system_prompt="", memory_block="")
    assert "Previously discussed" in ctx
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_working_memory.py -v`
Expected: FAIL

- [ ] **Step 3: Implement working memory**

Create `backend/nobla/memory/working.py`:

```python
"""Working memory — active conversation context window management.

Manages what goes into the LLM's context window for each request.
Handles token budgeting, observation masking, and rolling summaries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Rough estimate: 1 token ~= 4 characters
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Rough token estimate. Actual counting done at router level."""
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass
class ContextMessage:
    role: str
    content: str
    tool_output: Optional[str] = None  # Masked from context
    token_estimate: int = 0

    def __post_init__(self):
        self.token_estimate = estimate_tokens(self.content)


class WorkingMemory:
    """Manages the active context window for a conversation."""

    def __init__(self, max_tokens: int = 8000):
        self.max_tokens = max_tokens
        self.messages: list[ContextMessage] = []
        self._rolling_summary: Optional[str] = None

    def add_message(
        self,
        role: str,
        content: str,
        tool_output: Optional[str] = None,
    ) -> None:
        """Add a message to working memory."""
        self.messages.append(ContextMessage(
            role=role,
            content=content,
            tool_output=tool_output,
        ))

    def set_rolling_summary(self, summary: str) -> None:
        """Set the rolling summary for older messages (from warm path)."""
        self._rolling_summary = summary

    def clear(self) -> None:
        """Clear all messages and summary."""
        self.messages.clear()
        self._rolling_summary = None

    def get_context(
        self,
        system_prompt: str,
        memory_block: str,
        current_message: Optional[str] = None,
    ) -> str:
        """Assemble the context window within the token budget.

        Priority order (if budget tight):
        1. System prompt (never truncated)
        2. Current user message (never truncated)
        3. Memory block (truncated to 500 tokens max)
        4. Last 3 messages verbatim (minimum coherence)
        5. Remaining history fills whatever budget is left
        """
        budget = self.max_tokens
        parts: list[str] = []

        # 1. System prompt (always included)
        if system_prompt:
            parts.append(f"[System] {system_prompt}")
            budget -= estimate_tokens(system_prompt)

        # 2. Memory block (cap at 500 tokens)
        if memory_block:
            mem_tokens = estimate_tokens(memory_block)
            if mem_tokens > 500:
                # Truncate memory block
                memory_block = memory_block[:500 * CHARS_PER_TOKEN]
            parts.append(f"[Memory] {memory_block}")
            budget -= min(mem_tokens, 500)

        # 3. Rolling summary of older messages
        if self._rolling_summary:
            parts.append(f"[Summary] {self._rolling_summary}")
            budget -= estimate_tokens(self._rolling_summary)

        # 4. Conversation messages (newest first until budget exhausted)
        message_parts: list[str] = []
        for msg in reversed(self.messages):
            # Observation masking: skip tool_output, keep content only
            msg_text = f"{msg.role}: {msg.content}"
            msg_tokens = estimate_tokens(msg_text)
            if budget - msg_tokens < 0 and len(message_parts) >= 3:
                break  # Keep at least 3 recent messages
            message_parts.append(msg_text)
            budget -= msg_tokens

        # Reverse back to chronological order
        message_parts.reverse()
        parts.extend(message_parts)

        # 5. Current message
        if current_message:
            parts.append(f"user: {current_message}")

        return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_working_memory.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/memory/working.py backend/tests/test_working_memory.py
git commit -m "feat: working memory — context window management with observation masking"
```

---

### Task 6: Memory Orchestrator

**Files:**
- Create: `backend/nobla/memory/orchestrator.py`
- Create: `backend/tests/test_orchestrator.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_orchestrator.py`:

```python
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.memory.orchestrator import MemoryOrchestrator

@pytest.fixture
def orchestrator():
    return MemoryOrchestrator(
        db_session=AsyncMock(),
        settings=MagicMock(
            memory=MagicMock(
                max_context_tokens=8000,
                chromadb_path="./test_chromadb",
                embedding_model="all-MiniLM-L6-v2",
                spacy_model=None,  # Skip spaCy in tests
                retrieval_top_k=5,
                semantic_weight=0.7,
                keyword_weight=0.3,
            )
        ),
    )

@pytest.mark.asyncio
async def test_process_message_hot_path(orchestrator):
    """Hot path should store message and extract metadata."""
    result = await orchestrator.process_message(
        conversation_id=uuid.uuid4(),
        role="user",
        content="Alice likes Python for ML",
    )
    assert result is not None

@pytest.mark.asyncio
async def test_get_memory_context(orchestrator):
    """Should return a formatted memory context string."""
    context = await orchestrator.get_memory_context(
        user_id=uuid.uuid4(),
        query="What does Alice like?",
    )
    assert isinstance(context, str)

def test_get_working_memory(orchestrator):
    conv_id = uuid.uuid4()
    wm = orchestrator.get_working_memory(conv_id)
    assert wm is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_orchestrator.py -v`
Expected: FAIL

- [ ] **Step 3: Implement orchestrator**

Create `backend/nobla/memory/orchestrator.py`:

```python
"""Memory orchestrator — thin coordinator routing to independent layers.

Does not own logic. Delegates to episodic, semantic, procedural, graph,
retrieval, extraction, and working memory modules.
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from nobla.memory.working import WorkingMemory
from nobla.memory.episodic import EpisodicMemory
from nobla.memory.extraction import ExtractionEngine

logger = logging.getLogger(__name__)


class MemoryOrchestrator:
    """Coordinates all memory layers. Injected into gateway at startup."""

    def __init__(self, db_session: AsyncSession, settings):
        self._db = db_session
        self._settings = settings.memory

        # Initialize layers
        self._episodic = EpisodicMemory(db_session)
        self._extraction = ExtractionEngine(
            spacy_model=self._settings.spacy_model
        )

        # Working memory: one per active conversation
        self._working_memories: dict[uuid_lib.UUID, WorkingMemory] = {}

        # Semantic, procedural, graph — initialized in Phase 2A-2
        self._semantic = None
        self._procedural = None
        self._graph = None
        self._retrieval = None

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

        # 2. Store in episodic memory
        msg = await self._episodic.store_message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata=extraction,
            **kwargs,
        )

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
        return await self._episodic.create_conversation(user_id, title)

    async def list_conversations(
        self, user_id: uuid_lib.UUID, limit: int = 20, offset: int = 0
    ):
        return await self._episodic.list_conversations(user_id, limit, offset)

    async def get_messages(
        self, conversation_id: uuid_lib.UUID, limit: int = 50
    ):
        return await self._episodic.get_messages(conversation_id, limit)

    async def archive_conversation(self, conversation_id: uuid_lib.UUID):
        return await self._episodic.archive_conversation(conversation_id)

    async def rename_conversation(
        self, conversation_id: uuid_lib.UUID, title: str
    ):
        return await self._episodic.rename_conversation(conversation_id, title)

    async def search_conversations(
        self, user_id: uuid_lib.UUID, query: str, limit: int = 10
    ):
        return await self._episodic.search_conversations(user_id, query, limit)

    def release_working_memory(self, conversation_id: uuid_lib.UUID) -> None:
        """Release working memory for a conversation (on switch/close)."""
        self._working_memories.pop(conversation_id, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_orchestrator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/memory/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat: memory orchestrator — thin coordinator for all memory layers"
```

---

### Task 7: Integrate Memory into Gateway

**Files:**
- Modify: `backend/nobla/gateway/app.py:42-128`
- Modify: `backend/nobla/gateway/websocket.py:389-407`
- Create: `backend/tests/integration/test_chat_send_memory.py`

- [ ] **Step 1: Write integration test**

Create `backend/tests/integration/test_chat_send_memory.py`:

```python
"""Test that chat.send integrates with memory orchestrator."""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_chat_send_stores_message_in_memory():
    """Verify chat.send calls memory orchestrator hot path."""
    # This test validates the integration point exists
    from nobla.memory.orchestrator import MemoryOrchestrator
    orch = MemoryOrchestrator(
        db_session=AsyncMock(),
        settings=MagicMock(memory=MagicMock(
            max_context_tokens=8000,
            spacy_model=None,
            chromadb_path="./test",
            embedding_model="test",
            retrieval_top_k=5,
            semantic_weight=0.7,
            keyword_weight=0.3,
        )),
    )
    result = await orch.process_message(
        conversation_id=uuid.uuid4(),
        role="user",
        content="Test message",
    )
    assert "message_id" in result
    assert "keywords" in result
```

- [ ] **Step 2: Add MemoryOrchestrator to app lifespan**

In `backend/nobla/gateway/app.py`, add import at top:
```python
from nobla.memory.orchestrator import MemoryOrchestrator
```

In the `lifespan()` function (after security services init, around line 115), add:
```python
        # Memory system
        memory_orchestrator = MemoryOrchestrator(
            db_session=None,  # Will use per-request sessions
            settings=settings,
        )
        set_memory_orchestrator(memory_orchestrator)
```

- [ ] **Step 3: Add memory accessor to websocket.py**

In `backend/nobla/gateway/websocket.py`, add getter function (near line 191):
```python
_memory_orchestrator = None

def set_memory_orchestrator(orch):
    global _memory_orchestrator
    _memory_orchestrator = orch

def get_memory_orchestrator():
    return _memory_orchestrator
```

- [ ] **Step 4: Modify handle_chat_send to use memory**

In `backend/nobla/gateway/websocket.py`, modify `handle_chat_send` (lines 389-407):

```python
async def handle_chat_send(params: dict, state: ConnectionState) -> dict:
    message = params.get("message", "")
    conversation_id = params.get("conversation_id", str(uuid.uuid4()))
    conv_uuid = uuid.UUID(conversation_id)

    # 1. Hot path: store user message + extract
    memory = get_memory_orchestrator()
    if memory:
        await memory.process_message(
            conversation_id=conv_uuid,
            role="user",
            content=message,
        )

    # 2. Retrieve memory context
    memory_context = ""
    if memory and state.user_id:
        memory_context = await memory.get_memory_context(
            user_id=uuid.UUID(state.user_id),
            query=message,
        )

    # 3. Build messages for LLM — MUST use LLMMessage objects, not dicts
    #    (router.route() expects list[LLMMessage], see brain/router.py:124)
    from nobla.brain.router import LLMMessage
    llm_messages = []
    if memory_context:
        llm_messages.append(LLMMessage(role="system", content=f"[Memory] {memory_context}"))
    llm_messages.append(LLMMessage(role="user", content=message))

    # 4. Route to LLM (existing logic)
    router = get_router()
    response = await router.route(llm_messages)

    # 5. Hot path: store assistant response
    if memory:
        await memory.process_message(
            conversation_id=conv_uuid,
            role="assistant",
            content=response.content,
            model_used=response.model,
            tokens_input=response.input_tokens,
            tokens_output=response.output_tokens,
            cost_usd=float(response.cost) if response.cost else None,
        )

    # IMPORTANT: Preserve existing response field names for Flutter compatibility
    # (Flutter reads "message", "tokens_used", "cost_usd" — do NOT rename)
    return {
        "message": response.content,
        "model": response.model,
        "tokens_used": response.input_tokens + response.output_tokens,
        "cost_usd": str(response.cost),
        "conversation_id": conversation_id,
    }
```

- [ ] **Step 5: Run integration test**

Run: `cd backend && pytest tests/integration/test_chat_send_memory.py -v`
Expected: PASS

- [ ] **Step 6: Run all existing tests to verify no regressions**

Run: `cd backend && pytest tests/ -v --tb=short`
Expected: All existing tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/nobla/gateway/ backend/tests/integration/test_chat_send_memory.py
git commit -m "feat: integrate memory orchestrator into chat.send gateway handler"
```

---

### Task 8: Add Conversation JSON-RPC Methods

**Files:**
- Modify: `backend/nobla/gateway/websocket.py`
- Create: `backend/tests/test_conversation_rpc.py`

- [ ] **Step 1: Write tests for new RPC methods**

Create `backend/tests/test_conversation_rpc.py`:

```python
import pytest
from nobla.gateway.protocol import JsonRpcRequest

def test_conversation_list_method_exists():
    req = JsonRpcRequest(method="conversation.list", params={}, id=1)
    assert req.method == "conversation.list"

def test_conversation_get_method_format():
    req = JsonRpcRequest(
        method="conversation.get",
        params={"conversation_id": "test-uuid"},
        id=2,
    )
    assert req.params["conversation_id"] == "test-uuid"

def test_conversation_search_method_format():
    req = JsonRpcRequest(
        method="conversation.search",
        params={"query": "python deployment"},
        id=3,
    )
    assert req.params["query"] == "python deployment"
```

- [ ] **Step 2: Register new RPC handlers in websocket.py**

Add these handler functions to `websocket.py` and register them in the method dispatch table:

```python
async def handle_conversation_list(params: dict, state: ConnectionState) -> dict:
    memory = get_memory_orchestrator()
    conversations = await memory.list_conversations(
        user_id=uuid.UUID(state.user_id),
        limit=params.get("limit", 20),
        offset=params.get("offset", 0),
    )
    return {
        "conversations": [
            {
                "id": str(c.id),
                "title": c.title,
                "summary": c.summary,
                "topics": c.topics or [],
                "message_count": c.message_count,
                "updated_at": c.updated_at,
                "created_at": c.created_at,
            }
            for c in conversations
        ]
    }

async def handle_conversation_get(params: dict, state: ConnectionState) -> dict:
    memory = get_memory_orchestrator()
    conv_id = uuid.UUID(params["conversation_id"])
    messages = await memory.get_messages(conv_id, limit=params.get("limit", 50))
    return {
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
                "model_used": m.model_used,
            }
            for m in messages
        ]
    }

async def handle_conversation_search(params: dict, state: ConnectionState) -> dict:
    memory = get_memory_orchestrator()
    results = await memory.search_conversations(
        user_id=uuid.UUID(state.user_id),
        query=params["query"],
        limit=params.get("limit", 10),
    )
    return {"results": results}

async def handle_conversation_delete(params: dict, state: ConnectionState) -> dict:
    memory = get_memory_orchestrator()
    success = await memory.archive_conversation(uuid.UUID(params["conversation_id"]))
    return {"archived": success}

async def handle_conversation_rename(params: dict, state: ConnectionState) -> dict:
    memory = get_memory_orchestrator()
    success = await memory.rename_conversation(
        uuid.UUID(params["conversation_id"]),
        params["title"],
    )
    return {"renamed": success}

async def handle_conversation_create(params: dict, state: ConnectionState) -> dict:
    """Create a new conversation. Called by Flutter 'New Conversation' button."""
    memory = get_memory_orchestrator()
    conv = await memory.create_conversation(
        user_id=uuid.UUID(state.user_id),
        title=params.get("title"),
    )
    return {"conversation_id": str(conv.id), "title": conv.title}

async def handle_conversation_pause(params: dict, state: ConnectionState) -> dict:
    """Flutter sends this on AppLifecycleState.paused. Triggers warm path."""
    memory = get_memory_orchestrator()
    conv_id = uuid.UUID(params["conversation_id"])
    # Trigger warm path consolidation asynchronously
    import asyncio
    asyncio.create_task(memory.trigger_warm_path(conv_id, uuid.UUID(state.user_id)))
    memory.release_working_memory(conv_id)
    return {"status": "consolidation_started"}

async def handle_conversation_close(params: dict, state: ConnectionState) -> dict:
    """Explicit conversation end. Same as pause but user-initiated."""
    return await handle_conversation_pause(params, state)
```

- [ ] **Step 3: Run tests**

Run: `cd backend && pytest tests/test_conversation_rpc.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/nobla/gateway/websocket.py backend/tests/test_conversation_rpc.py
git commit -m "feat: add conversation.list/get/search/delete/rename RPC methods"
```

---

## Phase 2A-2: Intelligence Layers (Tasks 9-14)

> Tasks 9-14 build the semantic memory, retrieval pipeline, knowledge graph, and warm path.
> These can be partially parallelized: Tasks 9-10 (semantic + retrieval) and Tasks 11-12 (graph) are independent.

### Task 9: Semantic Memory (ChromaDB + PostgreSQL)

**Files:**
- Create: `backend/nobla/memory/semantic.py`
- Create: `backend/tests/test_semantic.py`

- [ ] **Step 1: Write failing tests**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement semantic memory** — ChromaDB collection per user, fact CRUD, embedding storage, dedup detection (cosine >0.85)
- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

### Task 10: Retrieval Pipeline (Hybrid Search + Re-ranking)

**Files:**
- Create: `backend/nobla/memory/retrieval_sources.py`
- Create: `backend/nobla/memory/retrieval.py`
- Create: `backend/tests/test_retrieval.py`

- [ ] **Step 1: Write failing tests** — Test parallel query, merge/dedup, re-ranking formula
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement retrieval sources** — ChromaDB semantic, PostgreSQL BM25, graph neighbor backends
- [ ] **Step 4: Implement retrieval orchestrator** — Parallel query, merge, re-rank with formula: `0.4*similarity + 0.3*recency + 0.2*frequency + 0.1*confidence`
- [ ] **Step 5: Wire retrieval into orchestrator.get_memory_context()**
- [ ] **Step 6: Run tests to verify they pass**
- [ ] **Step 7: Commit**

### Task 11: Knowledge Graph Builder + Persistence

**Files:**
- Create: `backend/nobla/memory/graph_builder.py`
- Create: `backend/nobla/memory/graph_persistence.py`
- Create: `backend/tests/test_graph.py`

- [ ] **Step 1: Write failing tests** — Entity CRUD, relationship management, serialization round-trip
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement graph builder** — NetworkX DiGraph, add_entity(), add_relationship(), entity types from spec
- [ ] **Step 4: Implement graph persistence** — Load from PostgreSQL memory_nodes/memory_links, save incremental changes
- [ ] **Step 5: Run tests to verify they pass**
- [ ] **Step 6: Commit**

### Task 12: Knowledge Graph Queries

**Files:**
- Create: `backend/nobla/memory/graph_queries.py`

- [ ] **Step 1: Write failing tests** — 1-hop neighbors, relationship queries, entity search
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement graph queries** — neighbors(), get_related(), search_entities()
- [ ] **Step 4: Wire graph queries into retrieval_sources.py as a retrieval backend**
- [ ] **Step 5: Run tests to verify they pass**
- [ ] **Step 6: Commit**

### Task 13: Warm Path Consolidation

**Files:**
- Create: `backend/nobla/memory/consolidation.py`
- Create: `backend/tests/test_consolidation.py`

- [ ] **Step 1: Write failing tests** — Summary generation, fact extraction, graph update, dedup
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement consolidation** — Uses cheap LLM call to extract facts/entities, updates semantic memory + knowledge graph
- [ ] **Step 4: Add warm path trigger to orchestrator** — On conversation pause/switch/idle
- [ ] **Step 5: Run tests to verify they pass**
- [ ] **Step 6: Commit**

### Task 14: Async Embedding (Fire-and-Forget)

**Files:**
- Modify: `backend/nobla/memory/orchestrator.py`

- [ ] **Step 1: Write test for async embedding**
- [ ] **Step 2: Implement `_embed_async()` in orchestrator** — sentence-transformers embed + store in ChromaDB
- [ ] **Step 3: Uncomment fire-and-forget call in `process_message()`**
- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

---

## Phase 2A-3: Learning & Polish (Tasks 15-22)

### Task 15: Procedural Memory (Bayesian Scoring)

**Files:**
- Create: `backend/nobla/memory/procedural.py`
- Create: `backend/tests/test_procedural.py`

- [ ] **Step 1-5: TDD cycle** — Implement procedure CRUD, Bayesian Beta scoring, trigger matching, auto-suggestion
- [ ] **Step 6: Commit**

### Task 16: Cold Path Maintenance

**Files:**
- Create: `backend/nobla/memory/maintenance.py`
- Create: `backend/tests/test_maintenance.py`

- [ ] **Step 1-5: TDD cycle** — Implement decay, dedup, prune, graph cleanup, APScheduler integration
- [ ] **Step 6: Commit**

### Task 17: Memory RPC Methods

**Files:**
- Modify: `backend/nobla/gateway/websocket.py`

- [ ] **Step 1-4: TDD cycle** — Add memory.search, memory.facts, memory.graph, memory.stats handlers
- [ ] **Step 5: Commit**

### Task 18: Flutter — Shared Models

**Files:**
- Create: `app/lib/shared/models/conversation.dart`
- Create: `app/lib/shared/models/memory_fact.dart`
- Create: `app/lib/shared/models/memory_entity.dart`
- Create: `app/lib/shared/models/memory_stats.dart`

- [ ] **Step 1: Create Conversation model** — id, title, summary, topics, messageCount, updatedAt, lastMessagePreview
- [ ] **Step 2: Create MemoryFact model** — id, content, confidence, keywords, lastAccessed, accessCount
- [ ] **Step 3: Create MemoryEntity model** — id, name, type, relationshipCount, lastSeen
- [ ] **Step 4: Create MemoryStats model** — totalFacts, totalEntities, totalProcedures, graphEdges, lastConsolidation
- [ ] **Step 5: Commit**

### Task 19: Flutter — Conversation Provider + Drawer

**Files:**
- Create: `app/lib/features/conversations/providers/conversation_provider.dart`
- Create: `app/lib/features/conversations/screens/conversation_drawer.dart`
- Create: `app/lib/features/conversations/widgets/conversation_tile.dart`
- Modify: `app/lib/features/chat/screens/chat_screen.dart`

- [ ] **Step 1: Implement ConversationListNotifier** — Calls conversation.list/search/delete/rename via JSON-RPC
- [ ] **Step 2: Implement ConversationDrawer** — Sidebar with search, grouped by date (Today/Yesterday/This Week/Older)
- [ ] **Step 3: Implement ConversationTile** — Title, preview, topic tags, swipe to archive
- [ ] **Step 4: Add drawer toggle to ChatScreen** — Hamburger menu or swipe from left
- [ ] **Step 5: Wire conversation switching** — Tap tile → load conversation → update ChatNotifier
- [ ] **Step 6: Run `flutter analyze` and `dart format lib/`**
- [ ] **Step 7: Commit**

### Task 20: Flutter — Memory Viewer Screen

**Files:**
- Create: `app/lib/features/memory/providers/memory_provider.dart`
- Create: `app/lib/features/memory/screens/memory_viewer_screen.dart`
- Create: `app/lib/features/memory/widgets/fact_card.dart`
- Create: `app/lib/features/memory/widgets/entity_card.dart`
- Create: `app/lib/features/memory/widgets/procedure_card.dart`
- Modify: `app/lib/core/routing/app_router.dart:39-50`

- [ ] **Step 1: Implement MemoryStatsNotifier + MemorySearchNotifier**
- [ ] **Step 2: Implement MemoryViewerScreen** — TabBar with Facts/Entities/Procedures tabs
- [ ] **Step 3: Implement card widgets** — FactCard (content + confidence), EntityCard (name + type + relationships), ProcedureCard (name + success rate)
- [ ] **Step 4: Add `/home/memory` route to app_router.dart** — New bottom nav destination
- [ ] **Step 5: Run `flutter analyze` and `flutter test`**
- [ ] **Step 6: Commit**

### Task 21: Flutter — Dashboard Memory Stats Card

**Files:**
- Modify: `app/lib/features/dashboard/screens/dashboard_screen.dart`

- [ ] **Step 1: Add MemoryStatsCard widget** — Shows total facts, entities, procedures, last consolidation
- [ ] **Step 2: Add to dashboard layout** — Below existing connection/cost/security cards
- [ ] **Step 3: Add community placeholder card** — "Skills Marketplace — Coming Soon"
- [ ] **Step 4: Commit**

### Task 22: Skill/Plugin Schema Files + Final Integration Test

**Files:**
- Create: `skills/bundled/.gitkeep`
- Create: `skills/community/.gitkeep`
- Create: `skills/custom/.gitkeep`
- Create: `plugins/bundled/.gitkeep`
- Create: `plugins/community/.gitkeep`
- Create: `plugins/custom/.gitkeep`
- Create: `backend/tests/integration/test_memory_flow.py`

- [ ] **Step 1: Create skill/plugin directory structure**
- [ ] **Step 2: Write full integration test** — Create conversation → send messages → verify hot path → trigger warm path → verify facts extracted → search conversations → verify retrieval augments prompt
- [ ] **Step 3: Run full test suite**

Run: `cd backend && pytest tests/ -v --cov=nobla`
Expected: All tests pass, coverage >90% for memory modules

- [ ] **Step 4: Run Flutter tests**

Run: `cd app && flutter test --coverage && flutter analyze`
Expected: All tests pass, no analysis issues

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: Phase 2A complete — 5-layer memory system + conversation persistence"
```

---

## Cross-Cutting Fixes (Applied Throughout)

These issues apply across multiple tasks. Apply them during implementation:

**Session management (I8):** The `MemoryOrchestrator` must NOT be initialized with `db_session=None`. Use a session factory pattern:
```python
# In app.py lifespan, pass the session factory, not a session:
from nobla.db.session import async_session_factory
memory_orchestrator = MemoryOrchestrator(session_factory=async_session_factory, settings=settings)

# In orchestrator, create sessions per operation:
async def process_message(self, ...):
    async with self._session_factory() as session:
        episodic = EpisodicMemory(session)
        ...
```

**DRY with ConversationRepository (I9):** `EpisodicMemory` should delegate to the existing `ConversationRepository` at `backend/nobla/db/repositories/conversation_repo.py` for basic CRUD, and add only the new memory-specific methods (search, summary update, hot path metadata).

**UUID consistency (I10):** All new `UUID` columns must use `as_uuid=False` to match the existing convention (e.g., `Message.id` uses `UUID(as_uuid=False)`).

**Use structlog (M4):** All new modules must use `import structlog; logger = structlog.get_logger(__name__)` instead of `import logging`.

**RPC handler decorators (M5):** All new RPC handlers must use the `@rpc_method("method.name")` decorator to register in the dispatch table, matching the existing pattern.

**websocket.py 750-line risk (I14):** When adding conversation + memory RPC handlers, create a new file `backend/nobla/gateway/conversation_handlers.py` for conversation-related handlers and `backend/nobla/gateway/memory_handlers.py` for memory-related handlers. Import and register them in websocket.py.

**Hard-Query LLM Re-ranking (I2):** Explicitly deferred to Phase 2B. The retrieval pipeline returns results from the lightweight re-ranking formula only. A TODO comment marks where LLM re-ranking would be added.

---

### Task 23: Security, Concurrency, and Performance Tests

**Files:**
- Create: `backend/tests/test_memory_isolation.py`
- Create: `backend/tests/test_concurrent_memory.py`
- Create: `backend/tests/test_sensitive_extraction.py`
- Create: `backend/tests/bench_hot_path.py`
- Create: `backend/tests/bench_retrieval.py`

- [ ] **Step 1: Write memory isolation test**

```python
# test_memory_isolation.py
import pytest, uuid
@pytest.mark.asyncio
async def test_no_cross_user_memory_leakage(orchestrator_factory):
    """Two users should never see each other's memories."""
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    orch = orchestrator_factory()
    # Store fact for user_a
    # Retrieve as user_b — must return empty
```

- [ ] **Step 2: Write concurrent memory test**

```python
# test_concurrent_memory.py
import pytest, asyncio, uuid
@pytest.mark.asyncio
async def test_concurrent_warm_paths_no_race_condition():
    """Two conversations ending simultaneously should not corrupt facts."""
    # Create 2 conversations, send messages to both
    # Trigger warm path on both simultaneously via asyncio.gather
    # Verify no duplicate/corrupted facts
```

- [ ] **Step 3: Write sensitive data extraction test**

```python
# test_sensitive_extraction.py
import pytest
@pytest.mark.asyncio
async def test_extraction_filters_passwords():
    """Warm path must NOT extract passwords, API keys, or tokens as facts."""
    messages = [
        "My API key is sk-abc123def456",
        "Password for server: MyS3cret!Pass",
        "Bearer token: eyJhbGciOiJIUzI1...",
    ]
    # Run warm path extraction on these
    # Verify no extracted fact contains the sensitive values
```

- [ ] **Step 4: Write performance benchmarks**

```python
# bench_hot_path.py — validate <50ms sync target
# bench_retrieval.py — validate <200ms with 1K, 5K, 10K nodes
```

- [ ] **Step 5: Run all tests**

Run: `cd backend && pytest tests/ -v --cov=nobla`
Expected: All pass, >90% coverage on memory modules

- [ ] **Step 6: Commit**

```bash
git add backend/tests/
git commit -m "test: add security, concurrency, and performance tests for memory"
```

---

### Task 24: Flutter Lifecycle + Tests

**Files:**
- Modify: `app/lib/main.dart` — Add `AppLifecycleState` observer
- Create: `app/test/features/conversations/conversation_provider_test.dart`
- Create: `app/test/features/memory/memory_viewer_screen_test.dart`

- [ ] **Step 1: Add lifecycle observer to main.dart**

```dart
// In NoblaApp, add WidgetsBindingObserver mixin
// On AppLifecycleState.paused: send conversation.pause via JSON-RPC
// On AppLifecycleState.resumed: reconnect WebSocket if needed
```

- [ ] **Step 2: Write conversation provider tests**

```dart
// conversation_provider_test.dart
// Test: list conversations returns parsed models
// Test: search conversations filters correctly
// Test: archive conversation calls RPC
```

- [ ] **Step 3: Write memory viewer widget tests**

```dart
// memory_viewer_screen_test.dart
// Test: renders tabs (Facts, Entities, Procedures)
// Test: shows empty state when no memories
// Test: displays fact cards with confidence
```

- [ ] **Step 4: Run Flutter tests**

Run: `cd app && flutter test --coverage && flutter analyze`
Expected: All pass, no analysis issues

- [ ] **Step 5: Commit**

```bash
git add app/
git commit -m "feat: Flutter lifecycle observer + widget/provider tests"
```

---

## Task Dependencies

```
Task 1 (deps) ──→ Task 2 (schema + migration + indexes)
                    ├──→ Task 3 (extraction — no DB dependency)
                    └──→ Task 4 (episodic) → Task 5 (working)
                                                    ↓
Task 6 (orchestrator) → Task 7 (gateway integration) → Task 8 (conversation RPC)
                                                                      ↓
                    ┌───────────────────────────────────────────────────┤
                    ↓                                                   ↓
Task 9 (semantic) → Task 10 (retrieval)          Task 11 (graph builder) → Task 12 (graph queries)
        ↓           ↓                                                   ↓
  Task 14 (embed)   └───────────────────────────────────────────────────┤
                                                                      ↓
Task 13 (consolidation/warm path)
                          ↓
Task 15 (procedural) → Task 16 (maintenance/cold) → Task 17 (memory RPC)
                                                              ↓
Task 18 (Flutter models) ──→ Task 19a (conversation drawer)
                          ├──→ Task 19b (conversation switching)
                          ├──→ Task 20 (memory viewer)
                          └──→ Task 21 (dashboard)
                                        ↓
Task 22 (skill schema + integration) → Task 23 (security/perf tests) → Task 24 (Flutter tests)
```

**Parallelizable groups:**
- Tasks 3 (extraction) || Task 2 (schema) — extraction has no DB dependency
- Tasks 9-10 (semantic + retrieval) || Tasks 11-12 (graph)
- Task 14 (async embedding) depends on Task 9 only, not Task 13
- Tasks 19a, 19b, 20, 21 (Flutter screens) — all independent, share only Task 18 models

---

## Verification Checklist

After all tasks complete, verify:

- [ ] Send a message → response includes memory context from past conversations
- [ ] Close app → reopen → conversation history preserved
- [ ] Chat about preferences → facts extracted after conversation ends
- [ ] Mention people/projects → entities appear in knowledge graph
- [ ] Repeat a workflow → procedure created with Bayesian score
- [ ] Search past conversations → relevant results returned
- [ ] Memory viewer shows facts, entities, procedures
- [ ] Dashboard shows memory stats
- [ ] Background app → warm path triggers (conversation.pause sent)
- [ ] Two users' memories are fully isolated (security test passes)
- [ ] Sensitive data (passwords, API keys) never stored as facts
- [ ] All tests pass with >90% coverage on memory modules
- [ ] No file exceeds 750 lines
- [ ] websocket.py stays under 750 lines (handlers split into separate files)
