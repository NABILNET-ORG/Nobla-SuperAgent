# Phase 3B-1: Persona Engine + Emotion Detection — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persona system (data model, presets, CRUD API, prompt injection) and emotion detection (Hume AI + local fallback) to the Nobla Agent backend, integrating with the existing voice pipeline and brain router.

**Architecture:** Top-level `persona/` module for persona logic, `voice/emotion/` for audio-based emotion detection. Shared service function `resolve_and_route()` integrates both into voice and text chat paths. TDD throughout.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (async, PostgreSQL), Pydantic v2, Hume AI REST API, HuggingFace transformers (wav2vec2), pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-03-21-phase3b-persona-engine-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `backend/nobla/persona/__init__.py` | Package exports |
| `backend/nobla/persona/models.py` | Persona SQLAlchemy model, Pydantic schemas, UserPersonaPreference |
| `backend/nobla/persona/presets.py` | Professional, Friendly, Military bundled defaults |
| `backend/nobla/persona/repository.py` | Async CRUD operations against PostgreSQL |
| `backend/nobla/persona/manager.py` | Preset loading, session tracking, resolve chain, clone |
| `backend/nobla/persona/prompt.py` | Build system prompt string from persona + emotion |
| `backend/nobla/persona/service.py` | `resolve_and_route()` shared service function |
| `backend/nobla/voice/emotion/base.py` | Abstract `EmotionEngine` interface |
| `backend/nobla/voice/emotion/hume.py` | Hume AI REST client |
| `backend/nobla/voice/emotion/local.py` | wav2vec2 local emotion classifier |
| `backend/nobla/voice/emotion/detector.py` | Fallback chain + 30s cache |
| `backend/nobla/gateway/persona_routes.py` | REST API endpoints for persona CRUD + preference |
| `backend/nobla/db/migrations/versions/002_phase3b_persona_tables.py` | Alembic migration |
| `backend/tests/test_persona_models.py` | Unit tests for persona models + presets |
| `backend/tests/test_persona_repository.py` | Unit tests for CRUD repository |
| `backend/tests/test_persona_manager.py` | Unit tests for manager resolve/clone logic |
| `backend/tests/test_prompt_builder.py` | Unit tests for prompt assembly |
| `backend/tests/test_emotion.py` | Unit tests for emotion engines + detector |
| `backend/tests/test_persona_routes.py` | Unit tests for REST API endpoints |
| `backend/tests/integration/test_persona_flow.py` | Integration tests for full persona flow |

### Modified Files

| File | Changes |
|------|---------|
| `backend/nobla/config/settings.py:107-121` | Add `PersonaSettings` class + `persona` field on `Settings` |
| `backend/nobla/brain/base_provider.py:8-18` | Add `default_temperature: float` class attribute |
| `backend/nobla/brain/router.py:99-133` | Handle `system_prompt_extra` and `temperature_bias` kwargs in `route()` |
| `backend/nobla/voice/pipeline.py:15-22,27-36,67-108` | Add `emotion_result` to `PipelineResult` (defined here, not models.py), add emotion detection to `process_segment()`, refactor to STT+emotion only mode |
| `backend/nobla/voice/emotion/__init__.py` | Update exports |
| `backend/nobla/gateway/app.py:57-268` | Initialize PersonaManager, PromptBuilder, EmotionDetector in lifespan; register persona routes |
| `backend/nobla/gateway/websocket.py:134-205,403-458,737-740` | Add persona accessors, inject persona into chat.send, cleanup on disconnect |
| `backend/nobla/gateway/voice_handlers.py:18-33,94-138` | Add persona/emotion accessors, pass emotion to resolve_and_route |
| `backend/nobla/voice/persona/` | **Remove** — empty placeholder directory, replaced by top-level `nobla/persona/` |
| `backend/nobla/brain/router.py:135-167` | Apply same persona support to `stream_route()` |

---

## Task 1: PersonaSettings Configuration

**Files:**
- Modify: `backend/nobla/config/settings.py:95-121`
- Test: `backend/tests/test_persona_models.py`

- [ ] **Step 1: Write failing test for PersonaSettings**

```python
# backend/tests/test_persona_models.py
"""Tests for persona models, schemas, and configuration."""
import pytest
from nobla.config.settings import PersonaSettings, Settings


class TestPersonaSettings:
    def test_default_values(self):
        s = PersonaSettings()
        assert s.hume_api_key is None
        assert s.emotion_enabled is True
        assert s.emotion_cache_ttl == 30
        assert s.emotion_confidence_threshold == 0.5
        assert s.default_persona == "professional"

    def test_settings_has_persona_field(self):
        settings = Settings()
        assert hasattr(settings, "persona")
        assert isinstance(settings.persona, PersonaSettings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_persona_models.py::TestPersonaSettings -v`
Expected: FAIL — `PersonaSettings` not importable

- [ ] **Step 3: Implement PersonaSettings**

Add to `backend/nobla/config/settings.py` after the `VoiceSettings` class (after line 104):

```python
class PersonaSettings(BaseModel):
    """Persona system configuration."""

    hume_api_key: str | None = None
    emotion_enabled: bool = True
    emotion_cache_ttl: int = 30
    emotion_confidence_threshold: float = 0.5
    default_persona: str = "professional"
    local_emotion_model: str = (
        "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition"
    )
```

Add to the `Settings` class (after `voice` field, around line 119):

```python
    persona: PersonaSettings = Field(default_factory=PersonaSettings)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_persona_models.py::TestPersonaSettings -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/config/settings.py backend/tests/test_persona_models.py
git commit -m "feat(persona): add PersonaSettings configuration"
```

---

## Task 2: Persona Data Models

**Files:**
- Create: `backend/nobla/persona/__init__.py`
- Create: `backend/nobla/persona/models.py`
- Test: `backend/tests/test_persona_models.py` (append)

- [ ] **Step 1: Write failing tests for persona models**

Append to `backend/tests/test_persona_models.py`:

```python
from nobla.persona.models import (
    PersonaCreate,
    PersonaResponse,
    PersonaContext,
    EmotionResult,
)


class TestEmotionResult:
    def test_create_valid(self):
        e = EmotionResult(
            emotion="happy", confidence=0.85, secondary="curious", source="hume"
        )
        assert e.emotion == "happy"
        assert e.confidence == 0.85
        assert e.source == "hume"

    def test_neutral_has_no_secondary(self):
        e = EmotionResult(emotion="neutral", confidence=0.3, source="local")
        assert e.secondary is None


class TestPersonaCreate:
    def test_valid_creation(self):
        p = PersonaCreate(
            name="Test Persona",
            personality="Helpful assistant",
            language_style="casual",
            rules=["Be friendly"],
        )
        assert p.name == "Test Persona"
        assert p.temperature_bias is None

    def test_name_too_long(self):
        with pytest.raises(ValueError):
            PersonaCreate(
                name="x" * 101,
                personality="test",
                language_style="test",
            )

    def test_too_many_rules(self):
        with pytest.raises(ValueError):
            PersonaCreate(
                name="test",
                personality="test",
                language_style="test",
                rules=["rule"] * 21,
            )

    def test_temperature_bias_out_of_range(self):
        with pytest.raises(ValueError):
            PersonaCreate(
                name="test",
                personality="test",
                language_style="test",
                temperature_bias=0.8,
            )


class TestPersonaResponse:
    def test_includes_is_builtin(self):
        r = PersonaResponse(
            id="abc-123",
            name="Test",
            personality="test",
            language_style="test",
            is_builtin=True,
            rules=[],
        )
        assert r.is_builtin is True


class TestPersonaContext:
    def test_create(self):
        ctx = PersonaContext(
            persona_id="abc",
            persona_name="Pro",
            system_prompt_addition="You are Pro.",
            temperature_bias=0.1,
            voice_config={"engine": "fish_speech"},
        )
        assert ctx.system_prompt_addition == "You are Pro."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_persona_models.py::TestEmotionResult -v`
Expected: FAIL — `nobla.persona.models` not found

- [ ] **Step 3: Create persona package and models**

```python
# backend/nobla/persona/__init__.py
"""Persona system — data models, presets, CRUD, prompt building."""
```

```python
# backend/nobla/persona/models.py
"""Persona data models: SQLAlchemy ORM + Pydantic schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nobla.db.models.base import Base


# ---------------------------------------------------------------------------
# SQLAlchemy ORM
# ---------------------------------------------------------------------------

class Persona(Base):
    """Persona DB row — only user-created personas live here."""

    __tablename__ = "personas"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    personality: Mapped[str] = mapped_column(String(1000), nullable=False)
    language_style: Mapped[str] = mapped_column(String(500), nullable=False)
    voice_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    background: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    rules: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    temperature_bias: Mapped[float | None] = mapped_column(nullable=True)
    max_response_length: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[str] = mapped_column(
        server_default=text("NOW()"), nullable=False
    )
    updated_at: Mapped[str] = mapped_column(
        server_default=text("NOW()"), nullable=False
    )


class UserPersonaPreference(Base):
    """Stores each user's default persona choice."""

    __tablename__ = "user_persona_preferences"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True
    )
    default_persona_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), nullable=True
    )


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class EmotionResult(BaseModel):
    """Ephemeral emotion detection output."""

    emotion: str
    confidence: float = Field(ge=0.0, le=1.0)
    secondary: str | None = None
    source: str  # "hume" or "local"


class PersonaCreate(BaseModel):
    """Request body for creating a persona."""

    name: str = Field(min_length=1, max_length=100)
    personality: str = Field(min_length=1, max_length=1000)
    language_style: str = Field(min_length=1, max_length=500)
    background: str | None = Field(default=None, max_length=2000)
    voice_config: dict | None = None
    rules: list[str] = Field(default_factory=list)
    temperature_bias: float | None = Field(default=None, ge=-0.5, le=0.5)
    max_response_length: int | None = Field(default=None, ge=50, le=4096)

    @field_validator("rules")
    @classmethod
    def validate_rules(cls, v: list[str]) -> list[str]:
        if len(v) > 20:
            raise ValueError("Maximum 20 rules allowed")
        for rule in v:
            if len(rule) > 500:
                raise ValueError("Each rule must be at most 500 characters")
        return v


class PersonaUpdate(BaseModel):
    """Request body for updating a persona (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    personality: str | None = Field(default=None, min_length=1, max_length=1000)
    language_style: str | None = Field(default=None, min_length=1, max_length=500)
    background: str | None = None
    voice_config: dict | None = None
    rules: list[str] | None = None
    temperature_bias: float | None = Field(default=None, ge=-0.5, le=0.5)
    max_response_length: int | None = Field(default=None, ge=50, le=4096)

    @field_validator("rules")
    @classmethod
    def validate_rules(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if len(v) > 20:
            raise ValueError("Maximum 20 rules allowed")
        for rule in v:
            if len(rule) > 500:
                raise ValueError("Each rule must be at most 500 characters")
        return v


class PersonaResponse(BaseModel):
    """API response for a persona."""

    id: str
    name: str
    personality: str
    language_style: str
    background: str | None = None
    voice_config: dict | None = None
    rules: list[str] = Field(default_factory=list)
    temperature_bias: float | None = None
    max_response_length: int | None = None
    is_builtin: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class PersonaContext(BaseModel):
    """Assembled persona + emotion context for the router."""

    persona_id: str
    persona_name: str
    system_prompt_addition: str
    temperature_bias: float | None = None
    voice_config: dict | None = None


class PreferenceResponse(BaseModel):
    """API response for user persona preference."""

    default_persona_id: str | None = None


class PreferenceUpdate(BaseModel):
    """Request body for setting default persona."""

    default_persona_id: str
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_persona_models.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/persona/__init__.py backend/nobla/persona/models.py backend/tests/test_persona_models.py
git commit -m "feat(persona): add persona data models and Pydantic schemas"
```

---

## Task 3: Alembic Migration

**Files:**
- Create: `backend/nobla/db/migrations/versions/002_phase3b_persona_tables.py`

- [ ] **Step 1: Write the migration**

```python
# backend/nobla/db/migrations/versions/002_phase3b_persona_tables.py
"""Phase 3B: persona system tables.

Revision ID: 002_phase3b
Revises: 001_phase2a
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "002_phase3b"
down_revision = "001_phase2a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personas",
        sa.Column("id", UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=False), nullable=True, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("personality", sa.String(1000), nullable=False),
        sa.Column("language_style", sa.String(500), nullable=False),
        sa.Column("voice_config", JSONB, nullable=True),
        sa.Column("background", sa.String(2000), nullable=True),
        sa.Column("rules", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("temperature_bias", sa.Float, nullable=True),
        sa.Column("max_response_length", sa.Integer, nullable=True),
        sa.Column("created_at", sa.String, server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.String, server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_personas_user_name", "personas", ["user_id", "name"], unique=True)

    op.create_table(
        "user_persona_preferences",
        sa.Column("user_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("default_persona_id", UUID(as_uuid=False), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("user_persona_preferences")
    op.drop_index("ix_personas_user_name", table_name="personas")
    op.drop_table("personas")
```

- [ ] **Step 2: Verify migration file syntax**

Run: `cd backend && python -c "import nobla.db.migrations.versions.002_phase3b_persona_tables as m; print(m.revision)"`
Expected: Prints `002_phase3b`

- [ ] **Step 3: Commit**

```bash
git add backend/nobla/db/migrations/versions/002_phase3b_persona_tables.py
git commit -m "feat(persona): add Alembic migration for persona tables"
```

---

## Task 4: Bundled Presets

**Files:**
- Create: `backend/nobla/persona/presets.py`
- Test: `backend/tests/test_persona_models.py` (append)

- [ ] **Step 1: Write failing tests for presets**

Append to `backend/tests/test_persona_models.py`:

```python
from nobla.persona.presets import PRESETS, get_preset, PROFESSIONAL_ID, FRIENDLY_ID, MILITARY_ID


class TestPresets:
    def test_three_presets_exist(self):
        assert len(PRESETS) == 3

    def test_professional_is_default(self):
        p = get_preset("professional")
        assert p is not None
        assert p.id == PROFESSIONAL_ID
        assert p.is_builtin is True

    def test_friendly_preset(self):
        p = get_preset("friendly")
        assert p is not None
        assert p.temperature_bias == 0.2

    def test_military_preset(self):
        p = get_preset("military")
        assert p is not None
        assert p.temperature_bias == -0.3

    def test_get_by_id(self):
        from nobla.persona.presets import get_preset_by_id
        p = get_preset_by_id(PROFESSIONAL_ID)
        assert p is not None
        assert p.name == "Professional"

    def test_unknown_returns_none(self):
        assert get_preset("nonexistent") is None

    def test_all_presets_are_builtin(self):
        for p in PRESETS.values():
            assert p.is_builtin is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_persona_models.py::TestPresets -v`
Expected: FAIL — `nobla.persona.presets` not found

- [ ] **Step 3: Implement presets**

```python
# backend/nobla/persona/presets.py
"""Bundled persona presets — always available, even without DB."""
from __future__ import annotations

from dataclasses import dataclass, field

# Stable UUIDs for builtins (deterministic, never change).
PROFESSIONAL_ID = "00000000-0000-4000-a000-000000000001"
FRIENDLY_ID = "00000000-0000-4000-a000-000000000002"
MILITARY_ID = "00000000-0000-4000-a000-000000000003"

BUILTIN_NAMES = frozenset({"professional", "friendly", "military"})


@dataclass(frozen=True)
class PresetPersona:
    """Immutable in-memory persona preset."""

    id: str
    name: str
    personality: str
    language_style: str
    background: str
    rules: list[str] = field(default_factory=list)
    voice_config: dict | None = None
    temperature_bias: float | None = None
    max_response_length: int | None = None
    is_builtin: bool = True


_PROFESSIONAL = PresetPersona(
    id=PROFESSIONAL_ID,
    name="Professional",
    personality="Expert assistant focused on clarity and efficiency",
    language_style="formal, concise, structured",
    background="Productivity-oriented AI assistant",
    rules=[
        "Use bullet points for lists",
        "Cite sources when available",
        "Avoid colloquialisms",
    ],
    temperature_bias=0.0,
)

_FRIENDLY = PresetPersona(
    id=FRIENDLY_ID,
    name="Friendly",
    personality="Warm conversational companion, encouraging and approachable",
    language_style="casual, warm, uses analogies",
    background="Approachable AI companion for everyday conversations",
    rules=[
        "Match the user's energy level",
        "Use simple language",
        "Encourage questions",
    ],
    temperature_bias=0.2,
)

_MILITARY = PresetPersona(
    id=MILITARY_ID,
    name="Military",
    personality="Direct, mission-focused tactical advisor",
    language_style="terse, action-oriented, uses military terminology",
    background="Tactical advisor with military communication style",
    rules=[
        "Lead with the bottom line",
        "Use short sentences",
        "No hedging or filler",
    ],
    temperature_bias=-0.3,
)

PRESETS: dict[str, PresetPersona] = {
    "professional": _PROFESSIONAL,
    "friendly": _FRIENDLY,
    "military": _MILITARY,
}

_PRESETS_BY_ID: dict[str, PresetPersona] = {
    p.id: p for p in PRESETS.values()
}


def get_preset(name: str) -> PresetPersona | None:
    """Get a preset by lowercase name."""
    return PRESETS.get(name.lower())


def get_preset_by_id(preset_id: str) -> PresetPersona | None:
    """Get a preset by its stable UUID."""
    return _PRESETS_BY_ID.get(preset_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_persona_models.py::TestPresets -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/persona/presets.py backend/tests/test_persona_models.py
git commit -m "feat(persona): add bundled presets (Professional, Friendly, Military)"
```

---

## Task 5: Persona Repository

**Files:**
- Create: `backend/nobla/persona/repository.py`
- Test: `backend/tests/test_persona_repository.py`

- [ ] **Step 1: Write failing tests for repository**

```python
# backend/tests/test_persona_repository.py
"""Tests for persona CRUD repository."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.persona.repository import PersonaRepository
from nobla.persona.models import PersonaCreate


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.fixture
def mock_session_factory(mock_session):
    factory = MagicMock()
    factory.return_value = mock_session
    return factory


@pytest.fixture
def repo(mock_session_factory):
    return PersonaRepository(mock_session_factory)


class TestPersonaRepository:
    @pytest.mark.asyncio
    async def test_create_persona(self, repo, mock_session):
        data = PersonaCreate(
            name="TestBot",
            personality="Helpful",
            language_style="casual",
        )
        mock_session.refresh = AsyncMock()
        result = await repo.create("user-123", data)
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_rejects_builtin_name(self, repo):
        data = PersonaCreate(
            name="Professional",
            personality="test",
            language_style="test",
        )
        with pytest.raises(ValueError, match="builtin"):
            await repo.create("user-123", data)

    @pytest.mark.asyncio
    async def test_delete_rejects_missing(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        result = await repo.delete("nonexistent", "user-123")
        assert result is False

    @pytest.mark.asyncio
    async def test_set_default(self, repo, mock_session):
        await repo.set_default("user-123", "persona-456")
        mock_session.commit.assert_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_persona_repository.py -v`
Expected: FAIL — `nobla.persona.repository` not found

- [ ] **Step 3: Implement repository**

```python
# backend/nobla/persona/repository.py
"""Async CRUD repository for personas and user preferences."""
from __future__ import annotations

import logging

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from nobla.persona.models import (
    Persona,
    PersonaCreate,
    PersonaUpdate,
    UserPersonaPreference,
)
from nobla.persona.presets import BUILTIN_NAMES

logger = logging.getLogger(__name__)


class PersonaRepository:
    """Async CRUD operations for personas.

    Uses session_factory (not a single session) for concurrency safety.
    Each method creates its own session via async context manager.
    """

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def create(self, user_id: str, data: PersonaCreate) -> Persona:
        if data.name.lower() in BUILTIN_NAMES:
            raise ValueError(
                f"Name '{data.name}' conflicts with a builtin persona"
            )
        async with self._session_factory() as session:
            persona = Persona(
                user_id=user_id,
                name=data.name,
                personality=data.personality,
                language_style=data.language_style,
                background=data.background,
                voice_config=data.voice_config,
                rules=data.rules,
                temperature_bias=data.temperature_bias,
                max_response_length=data.max_response_length,
            )
            session.add(persona)
            await session.commit()
            await session.refresh(persona)
            return persona

    async def get(self, persona_id: str) -> Persona | None:
        async with self._session_factory() as session:
            stmt = select(Persona).where(Persona.id == persona_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_by_user(self, user_id: str) -> list[Persona]:
        async with self._session_factory() as session:
            stmt = select(Persona).where(Persona.user_id == user_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update(
        self, persona_id: str, user_id: str, data: PersonaUpdate
    ) -> Persona | None:
        async with self._session_factory() as session:
            stmt = select(Persona).where(Persona.id == persona_id)
            result = await session.execute(stmt)
            persona = result.scalar_one_or_none()
            if persona is None or persona.user_id != user_id:
                return None
            updates = data.model_dump(exclude_unset=True)
            if "name" in updates and updates["name"].lower() in BUILTIN_NAMES:
                raise ValueError(
                    f"Name '{updates['name']}' conflicts with a builtin persona"
                )
            for key, value in updates.items():
                setattr(persona, key, value)
            await session.commit()
            await session.refresh(persona)
            return persona

    async def delete(self, persona_id: str, user_id: str) -> bool:
        async with self._session_factory() as session:
            stmt = select(Persona).where(Persona.id == persona_id)
            result = await session.execute(stmt)
            persona = result.scalar_one_or_none()
            if persona is None or persona.user_id != user_id:
                return False
            await session.execute(
                sa_delete(Persona).where(Persona.id == persona_id)
            )
            await session.commit()
            return True

    async def set_default(
        self, user_id: str, persona_id: str | None
    ) -> None:
        async with self._session_factory() as session:
            stmt = select(UserPersonaPreference).where(
                UserPersonaPreference.user_id == user_id
            )
            result = await session.execute(stmt)
            pref = result.scalar_one_or_none()
            if pref is None:
                pref = UserPersonaPreference(
                    user_id=user_id, default_persona_id=persona_id
                )
                session.add(pref)
            else:
                pref.default_persona_id = persona_id
            await session.commit()

    async def get_default(self, user_id: str) -> str | None:
        async with self._session_factory() as session:
            stmt = select(UserPersonaPreference.default_persona_id).where(
                UserPersonaPreference.user_id == user_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_persona_repository.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/persona/repository.py backend/tests/test_persona_repository.py
git commit -m "feat(persona): add async CRUD repository with builtin name protection"
```

---

## Task 6: Prompt Builder

**Files:**
- Create: `backend/nobla/persona/prompt.py`
- Test: `backend/tests/test_prompt_builder.py`

- [ ] **Step 1: Write failing tests for prompt builder**

```python
# backend/tests/test_prompt_builder.py
"""Tests for persona prompt builder."""
import pytest
from nobla.persona.prompt import PromptBuilder
from nobla.persona.presets import get_preset
from nobla.persona.models import EmotionResult, PersonaContext


class TestPromptBuilder:
    def setup_method(self):
        self.builder = PromptBuilder()

    def test_build_basic_persona(self):
        preset = get_preset("professional")
        ctx = self.builder.build(preset, emotion=None)
        assert isinstance(ctx, PersonaContext)
        assert "Professional" in ctx.system_prompt_addition
        assert "formal, concise" in ctx.system_prompt_addition
        assert ctx.persona_id == preset.id
        assert ctx.temperature_bias == 0.0

    def test_build_includes_rules(self):
        preset = get_preset("military")
        ctx = self.builder.build(preset, emotion=None)
        assert "Lead with the bottom line" in ctx.system_prompt_addition

    def test_build_with_emotion(self):
        preset = get_preset("friendly")
        emotion = EmotionResult(
            emotion="frustrated", confidence=0.82, source="hume"
        )
        ctx = self.builder.build(preset, emotion=emotion)
        assert "frustrated" in ctx.system_prompt_addition
        assert "0.82" in ctx.system_prompt_addition

    def test_build_skips_low_confidence_emotion(self):
        preset = get_preset("professional")
        emotion = EmotionResult(
            emotion="happy", confidence=0.3, source="local"
        )
        ctx = self.builder.build(preset, emotion=emotion)
        assert "happy" not in ctx.system_prompt_addition

    def test_build_includes_max_response_length(self):
        preset = get_preset("professional")
        # Use a mock-like object with max_response_length set
        from nobla.persona.presets import PresetPersona
        custom = PresetPersona(
            id="test-id",
            name="Custom",
            personality="test",
            language_style="test",
            background="test",
            max_response_length=500,
        )
        ctx = self.builder.build(custom, emotion=None)
        assert "500" in ctx.system_prompt_addition

    def test_build_skips_none_background(self):
        from nobla.persona.presets import PresetPersona
        custom = PresetPersona(
            id="test-id",
            name="NoBg",
            personality="test",
            language_style="test",
            background="",
        )
        ctx = self.builder.build(custom, emotion=None)
        assert "Background:" not in ctx.system_prompt_addition

    def test_voice_config_passed_through(self):
        from nobla.persona.presets import PresetPersona
        custom = PresetPersona(
            id="test-id",
            name="VoiceTest",
            personality="test",
            language_style="test",
            background="test",
            voice_config={"engine": "fish_speech", "voice": "alloy"},
        )
        ctx = self.builder.build(custom, emotion=None)
        assert ctx.voice_config == {"engine": "fish_speech", "voice": "alloy"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_prompt_builder.py -v`
Expected: FAIL — `nobla.persona.prompt` not found

- [ ] **Step 3: Implement prompt builder**

```python
# backend/nobla/persona/prompt.py
"""Build LLM system prompt additions from persona + emotion context."""
from __future__ import annotations

from nobla.persona.models import EmotionResult, PersonaContext

# Confidence threshold below which emotion is treated as neutral.
_EMOTION_CONFIDENCE_THRESHOLD = 0.5


class PromptBuilder:
    """Assembles persona + emotion into a system prompt string."""

    def build(
        self,
        persona,  # PresetPersona or Persona ORM row (duck-typed)
        emotion: EmotionResult | None = None,
    ) -> PersonaContext:
        parts: list[str] = []

        parts.append(f"You are {persona.name}. {persona.personality}")
        parts.append(f"\nCommunication style: {persona.language_style}")

        if persona.background:
            parts.append(f"Background: {persona.background}")

        if persona.rules:
            parts.append("\nRules:")
            for rule in persona.rules:
                parts.append(f"- {rule}")

        if (
            emotion is not None
            and emotion.confidence >= _EMOTION_CONFIDENCE_THRESHOLD
        ):
            parts.append(
                f"\nUser's current mood: {emotion.emotion} "
                f"(confidence: {emotion.confidence})"
            )
            parts.append("Adapt your response accordingly.")

        if getattr(persona, "max_response_length", None):
            parts.append(
                f"\nKeep responses under {persona.max_response_length} tokens."
            )

        return PersonaContext(
            persona_id=persona.id,
            persona_name=persona.name,
            system_prompt_addition="\n".join(parts),
            temperature_bias=getattr(persona, "temperature_bias", None),
            voice_config=getattr(persona, "voice_config", None),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_prompt_builder.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/persona/prompt.py backend/tests/test_prompt_builder.py
git commit -m "feat(persona): add prompt builder with emotion + persona injection"
```

---

## Task 7: Persona Manager

**Files:**
- Create: `backend/nobla/persona/manager.py`
- Test: `backend/tests/test_persona_manager.py`

- [ ] **Step 1: Write failing tests for manager**

```python
# backend/tests/test_persona_manager.py
"""Tests for persona manager — resolve, clone, session tracking."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from nobla.persona.manager import PersonaManager
from nobla.persona.presets import PROFESSIONAL_ID, FRIENDLY_ID


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.get_default.return_value = None
    repo.get.return_value = None
    return repo


@pytest.fixture
def manager(mock_repo):
    return PersonaManager(repo=mock_repo)


class TestPersonaManager:
    @pytest.mark.asyncio
    async def test_resolve_defaults_to_professional(self, manager):
        result = await manager.resolve("session-1", "user-1")
        assert result.id == PROFESSIONAL_ID
        assert result.name == "Professional"

    @pytest.mark.asyncio
    async def test_resolve_session_override(self, manager):
        manager.set_session_persona("session-1", FRIENDLY_ID)
        result = await manager.resolve("session-1", "user-1")
        assert result.id == FRIENDLY_ID

    @pytest.mark.asyncio
    async def test_resolve_user_default(self, manager, mock_repo):
        mock_repo.get_default.return_value = FRIENDLY_ID
        result = await manager.resolve("session-1", "user-1")
        assert result.id == FRIENDLY_ID

    @pytest.mark.asyncio
    async def test_session_override_beats_user_default(self, manager, mock_repo):
        mock_repo.get_default.return_value = FRIENDLY_ID
        from nobla.persona.presets import MILITARY_ID
        manager.set_session_persona("session-1", MILITARY_ID)
        result = await manager.resolve("session-1", "user-1")
        assert result.id == MILITARY_ID

    def test_clear_session(self, manager):
        manager.set_session_persona("session-1", FRIENDLY_ID)
        manager.clear_session("session-1")
        # After clearing, no session override exists
        assert manager._session_personas.get("session-1") is None

    @pytest.mark.asyncio
    async def test_resolve_custom_persona_from_db(self, manager, mock_repo):
        mock_db_persona = MagicMock()
        mock_db_persona.id = "custom-id"
        mock_db_persona.name = "Custom"
        mock_repo.get.return_value = mock_db_persona
        mock_repo.get_default.return_value = "custom-id"
        result = await manager.resolve("session-1", "user-1")
        assert result.id == "custom-id"

    @pytest.mark.asyncio
    async def test_resolve_falls_back_on_db_error(self, manager, mock_repo):
        mock_repo.get_default.side_effect = Exception("DB down")
        result = await manager.resolve("session-1", "user-1")
        assert result.id == PROFESSIONAL_ID  # fallback

    @pytest.mark.asyncio
    async def test_get_persona_checks_presets_first(self, manager):
        result = await manager.get_persona(PROFESSIONAL_ID)
        assert result is not None
        assert result.name == "Professional"

    @pytest.mark.asyncio
    async def test_list_for_user(self, manager, mock_repo):
        mock_repo.list_by_user.return_value = []
        result = await manager.list_for_user("user-1")
        # Should include 3 presets even with no DB personas
        assert len(result) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_persona_manager.py -v`
Expected: FAIL — `nobla.persona.manager` not found

- [ ] **Step 3: Implement manager**

```python
# backend/nobla/persona/manager.py
"""Persona manager — resolution chain, session tracking, clone."""
from __future__ import annotations

import logging
from typing import Union

from nobla.persona.models import Persona, PersonaCreate
from nobla.persona.presets import (
    PRESETS,
    PROFESSIONAL_ID,
    PresetPersona,
    get_preset,
    get_preset_by_id,
)
from nobla.persona.repository import PersonaRepository

logger = logging.getLogger(__name__)

AnyPersona = Union[PresetPersona, Persona]


class PersonaManager:
    """Loads presets, resolves per-session persona, manages cloning."""

    def __init__(self, repo: PersonaRepository) -> None:
        self._repo = repo
        self._session_personas: dict[str, str] = {}

    def set_session_persona(self, session_id: str, persona_id: str) -> None:
        self._session_personas[session_id] = persona_id

    def clear_session(self, session_id: str) -> None:
        self._session_personas.pop(session_id, None)

    async def resolve(
        self, session_id: str, user_id: str
    ) -> AnyPersona:
        """Resolution chain: session override -> user default -> Professional."""
        # 1. Session override
        override_id = self._session_personas.get(session_id)
        if override_id:
            persona = await self.get_persona(override_id)
            if persona is not None:
                return persona

        # 2. User default from DB
        try:
            default_id = await self._repo.get_default(user_id)
            if default_id:
                persona = await self.get_persona(default_id)
                if persona is not None:
                    return persona
        except Exception:
            logger.warning(
                "DB unreachable during persona resolve, falling back to preset",
                exc_info=True,
            )

        # 3. Professional fallback
        return get_preset_by_id(PROFESSIONAL_ID)  # type: ignore[return-value]

    async def get_persona(self, persona_id: str) -> AnyPersona | None:
        """Lookup by ID — checks presets first, then DB."""
        preset = get_preset_by_id(persona_id)
        if preset is not None:
            return preset
        try:
            return await self._repo.get(persona_id)
        except Exception:
            logger.warning("DB error looking up persona %s", persona_id)
            return None

    async def list_for_user(self, user_id: str) -> list[AnyPersona]:
        """Returns all presets + user's custom personas."""
        result: list[AnyPersona] = list(PRESETS.values())
        try:
            db_personas = await self._repo.list_by_user(user_id)
            result.extend(db_personas)
        except Exception:
            logger.warning("DB error listing personas for user %s", user_id)
        return result

    async def clone(self, persona_id: str, user_id: str) -> Persona:
        """Clone a preset or custom persona as an editable copy."""
        source = await self.get_persona(persona_id)
        if source is None:
            raise ValueError(f"Persona {persona_id} not found")

        base_name = f"{source.name} (Copy)"
        name = base_name
        counter = 2
        # Resolve name collisions
        existing = await self._repo.list_by_user(user_id)
        existing_names = {p.name for p in existing}
        while name in existing_names:
            name = f"{source.name} (Copy {counter})"
            counter += 1

        data = PersonaCreate(
            name=name,
            personality=source.personality,
            language_style=source.language_style,
            background=getattr(source, "background", None) or "",
            voice_config=getattr(source, "voice_config", None),
            rules=list(source.rules) if source.rules else [],
            temperature_bias=getattr(source, "temperature_bias", None),
            max_response_length=getattr(source, "max_response_length", None),
        )
        return await self._repo.create(user_id, data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_persona_manager.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/persona/manager.py backend/tests/test_persona_manager.py
git commit -m "feat(persona): add persona manager with resolve chain and clone"
```

---

## Task 8: Emotion Detection — Base + Local Engine

**Files:**
- Modify: `backend/nobla/voice/emotion/__init__.py`
- Create: `backend/nobla/voice/emotion/base.py`
- Create: `backend/nobla/voice/emotion/local.py`
- Test: `backend/tests/test_emotion.py`

- [ ] **Step 1: Write failing tests for emotion engines**

```python
# backend/tests/test_emotion.py
"""Tests for emotion detection engines."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from nobla.voice.emotion.base import EmotionEngine
from nobla.persona.models import EmotionResult


class TestEmotionEngineInterface:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            EmotionEngine()


class TestLocalEmotionEngine:
    @pytest.mark.asyncio
    async def test_detect_returns_emotion_result(self):
        from nobla.voice.emotion.local import LocalEmotionEngine

        with patch.object(
            LocalEmotionEngine, "_classify", return_value=("happy", 0.75, "curious")
        ):
            engine = LocalEmotionEngine.__new__(LocalEmotionEngine)
            engine._model = MagicMock()
            engine._processor = MagicMock()
            result = await engine.detect(b"fake_audio_bytes")
            assert isinstance(result, EmotionResult)
            assert result.emotion == "happy"
            assert result.source == "local"

    @pytest.mark.asyncio
    async def test_detect_maps_to_vocabulary(self):
        from nobla.voice.emotion.local import LocalEmotionEngine, EMOTION_MAP

        assert "angry" in EMOTION_MAP  # maps to our vocabulary
        assert EMOTION_MAP["angry"] == "frustrated"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_emotion.py -v`
Expected: FAIL — modules not found

- [ ] **Step 3: Implement base and local engine**

```python
# backend/nobla/voice/emotion/base.py
"""Abstract base class for emotion detection engines."""
from __future__ import annotations

from abc import ABC, abstractmethod

from nobla.persona.models import EmotionResult


class EmotionEngine(ABC):
    """Interface for emotion detection from audio."""

    @abstractmethod
    async def detect(self, audio: bytes) -> EmotionResult:
        """Detect emotion from raw audio bytes."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this engine is ready to process."""
        ...
```

```python
# backend/nobla/voice/emotion/local.py
"""Local wav2vec2-based emotion classifier — free, runs on CPU."""
from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np

from nobla.persona.models import EmotionResult
from nobla.voice.emotion.base import EmotionEngine

logger = logging.getLogger(__name__)

# Map model labels to our 6-emotion vocabulary.
EMOTION_MAP: dict[str, str] = {
    "angry": "frustrated",
    "disgust": "frustrated",
    "fear": "anxious",
    "happy": "happy",
    "sad": "sad",
    "surprise": "curious",
    "neutral": "neutral",
    "calm": "neutral",
}

VALID_EMOTIONS = frozenset({"happy", "sad", "frustrated", "curious", "neutral", "anxious"})


class LocalEmotionEngine(EmotionEngine):
    """HuggingFace wav2vec2 emotion classifier."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None
        self._processor = None
        self._loaded = False

    async def is_available(self) -> bool:
        if not self._loaded:
            try:
                self._load_model()
            except Exception:
                logger.warning("Local emotion model unavailable", exc_info=True)
                return False
        return True

    def _load_model(self) -> None:
        """Lazy-load model on first use."""
        if self._loaded:
            return
        try:
            from transformers import Wav2Vec2ForSequenceClassification, Wav2Vec2Processor
            self._processor = Wav2Vec2Processor.from_pretrained(self._model_name)
            self._model = Wav2Vec2ForSequenceClassification.from_pretrained(self._model_name)
            self._loaded = True
            logger.info("Local emotion model loaded: %s", self._model_name)
        except Exception:
            logger.error("Failed to load emotion model %s", self._model_name, exc_info=True)
            raise

    def _classify(self, audio: bytes) -> tuple[str, float, str | None]:
        """Run classification, return (emotion, confidence, secondary)."""
        import torch

        self._load_model()
        audio_array = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        inputs = self._processor(audio_array, sampling_rate=16000, return_tensors="pt")

        with torch.no_grad():
            logits = self._model(**inputs).logits

        probs = torch.nn.functional.softmax(logits, dim=-1)[0]
        sorted_indices = torch.argsort(probs, descending=True)

        labels = self._model.config.id2label
        top_label = labels[sorted_indices[0].item()]
        top_conf = probs[sorted_indices[0]].item()
        second_label = labels[sorted_indices[1].item()] if len(sorted_indices) > 1 else None

        primary = EMOTION_MAP.get(top_label, "neutral")
        secondary = EMOTION_MAP.get(second_label, None) if second_label else None

        return primary, top_conf, secondary

    async def detect(self, audio: bytes) -> EmotionResult:
        primary, confidence, secondary = self._classify(audio)
        return EmotionResult(
            emotion=primary,
            confidence=round(confidence, 2),
            secondary=secondary,
            source="local",
        )
```

**Note:** Do NOT update `voice/emotion/__init__.py` yet — `EmotionDetector` (imported there) is not created until Task 10. The `__init__.py` update is deferred to Task 17 (final cleanup).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_emotion.py::TestEmotionEngineInterface tests/test_emotion.py::TestLocalEmotionEngine -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/voice/emotion/base.py backend/nobla/voice/emotion/local.py backend/tests/test_emotion.py
git commit -m "feat(emotion): add base interface and local wav2vec2 engine"
```

---

## Task 9: Emotion Detection — Hume AI Engine

**Files:**
- Create: `backend/nobla/voice/emotion/hume.py`
- Test: `backend/tests/test_emotion.py` (append)

- [ ] **Step 1: Write failing tests for Hume engine**

Append to `backend/tests/test_emotion.py`:

```python
class TestHumeEmotionEngine:
    @pytest.mark.asyncio
    async def test_is_available_without_key(self):
        from nobla.voice.emotion.hume import HumeEmotionEngine
        engine = HumeEmotionEngine(api_key=None)
        assert await engine.is_available() is False

    @pytest.mark.asyncio
    async def test_is_available_with_key(self):
        from nobla.voice.emotion.hume import HumeEmotionEngine
        engine = HumeEmotionEngine(api_key="test-key")
        assert await engine.is_available() is True

    @pytest.mark.asyncio
    async def test_detect_calls_api(self):
        from nobla.voice.emotion.hume import HumeEmotionEngine

        engine = HumeEmotionEngine(api_key="test-key")
        mock_response = {
            "results": {
                "predictions": [{
                    "models": {
                        "prosody": {
                            "grouped_predictions": [{
                                "predictions": [{
                                    "emotions": [
                                        {"name": "Joy", "score": 0.85},
                                        {"name": "Interest", "score": 0.6},
                                        {"name": "Sadness", "score": 0.1},
                                    ]
                                }]
                            }]
                        }
                    }
                }]
            }
        }
        with patch.object(engine, "_call_api", return_value=mock_response):
            result = await engine.detect(b"fake_audio")
            assert result.source == "hume"
            assert result.emotion == "happy"
            assert result.confidence > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_emotion.py::TestHumeEmotionEngine -v`
Expected: FAIL — `nobla.voice.emotion.hume` not found

- [ ] **Step 3: Implement Hume engine**

```python
# backend/nobla/voice/emotion/hume.py
"""Hume AI REST API client for emotion detection."""
from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from nobla.persona.models import EmotionResult
from nobla.voice.emotion.base import EmotionEngine

logger = logging.getLogger(__name__)

# Map Hume emotion names to our 6-emotion vocabulary.
_HUME_MAP: dict[str, str] = {
    "joy": "happy",
    "amusement": "happy",
    "excitement": "happy",
    "sadness": "sad",
    "grief": "sad",
    "disappointment": "sad",
    "anger": "frustrated",
    "contempt": "frustrated",
    "annoyance": "frustrated",
    "interest": "curious",
    "surprise (positive)": "curious",
    "curiosity": "curious",
    "anxiety": "anxious",
    "fear": "anxious",
    "nervousness": "anxious",
}

_HUME_API_URL = "https://api.hume.ai/v0/batch/jobs"


class HumeEmotionEngine(EmotionEngine):
    """Hume AI prosody-based emotion detection."""

    def __init__(self, api_key: str | None) -> None:
        self._api_key = api_key

    async def is_available(self) -> bool:
        return self._api_key is not None

    async def _call_api(self, audio: bytes) -> dict[str, Any]:
        """Send audio to Hume AI and return raw response."""
        encoded = base64.b64encode(audio).decode()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _HUME_API_URL,
                headers={
                    "X-Hume-Api-Key": self._api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "models": {"prosody": {}},
                    "data": [{"content": encoded, "content_type": "audio/wav"}],
                },
            )
            resp.raise_for_status()
            return resp.json()

    def _parse_response(self, data: dict[str, Any]) -> EmotionResult:
        """Extract top emotions from Hume API response."""
        try:
            emotions_list = (
                data["results"]["predictions"][0]["models"]["prosody"]
                ["grouped_predictions"][0]["predictions"][0]["emotions"]
            )
        except (KeyError, IndexError):
            return EmotionResult(
                emotion="neutral", confidence=0.0, source="hume"
            )

        sorted_emotions = sorted(emotions_list, key=lambda e: e["score"], reverse=True)
        top = sorted_emotions[0]
        second = sorted_emotions[1] if len(sorted_emotions) > 1 else None

        primary = _HUME_MAP.get(top["name"].lower(), "neutral")
        secondary = _HUME_MAP.get(second["name"].lower(), None) if second else None

        return EmotionResult(
            emotion=primary,
            confidence=round(top["score"], 2),
            secondary=secondary,
            source="hume",
        )

    async def detect(self, audio: bytes) -> EmotionResult:
        try:
            response = await self._call_api(audio)
            return self._parse_response(response)
        except Exception:
            logger.warning("Hume AI request failed", exc_info=True)
            raise
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_emotion.py::TestHumeEmotionEngine -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/voice/emotion/hume.py backend/tests/test_emotion.py
git commit -m "feat(emotion): add Hume AI REST client with emotion vocabulary mapping"
```

---

## Task 10: Emotion Detection — Fallback Detector

**Files:**
- Create: `backend/nobla/voice/emotion/detector.py`
- Test: `backend/tests/test_emotion.py` (append)

- [ ] **Step 1: Write failing tests for detector**

Append to `backend/tests/test_emotion.py`:

```python
import time


class TestEmotionDetector:
    @pytest.mark.asyncio
    async def test_uses_hume_when_available(self):
        from nobla.voice.emotion.detector import EmotionDetector

        hume = AsyncMock(spec=EmotionEngine)
        hume.is_available.return_value = True
        hume.detect.return_value = EmotionResult(
            emotion="happy", confidence=0.9, source="hume"
        )
        local = AsyncMock(spec=EmotionEngine)
        detector = EmotionDetector(hume=hume, local=local, cache_ttl=30)

        result = await detector.detect("session-1", b"audio")
        assert result.source == "hume"
        local.detect.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_falls_back_to_local(self):
        from nobla.voice.emotion.detector import EmotionDetector

        hume = AsyncMock(spec=EmotionEngine)
        hume.is_available.return_value = True
        hume.detect.side_effect = Exception("API down")
        local = AsyncMock(spec=EmotionEngine)
        local.is_available.return_value = True
        local.detect.return_value = EmotionResult(
            emotion="neutral", confidence=0.6, source="local"
        )
        detector = EmotionDetector(hume=hume, local=local, cache_ttl=30)

        result = await detector.detect("session-1", b"audio")
        assert result.source == "local"

    @pytest.mark.asyncio
    async def test_returns_none_when_both_fail(self):
        from nobla.voice.emotion.detector import EmotionDetector

        hume = AsyncMock(spec=EmotionEngine)
        hume.is_available.return_value = False
        local = AsyncMock(spec=EmotionEngine)
        local.is_available.return_value = True
        local.detect.side_effect = Exception("Model error")
        detector = EmotionDetector(hume=hume, local=local, cache_ttl=30)

        result = await detector.detect("session-1", b"audio")
        assert result is None

    @pytest.mark.asyncio
    async def test_caches_per_session(self):
        from nobla.voice.emotion.detector import EmotionDetector

        hume = AsyncMock(spec=EmotionEngine)
        hume.is_available.return_value = True
        hume.detect.return_value = EmotionResult(
            emotion="happy", confidence=0.9, source="hume"
        )
        local = AsyncMock(spec=EmotionEngine)
        detector = EmotionDetector(hume=hume, local=local, cache_ttl=30)

        r1 = await detector.detect("session-1", b"audio")
        r2 = await detector.detect("session-1", b"audio")
        assert r1 == r2
        # detect called only once due to cache
        assert hume.detect.await_count == 1

    @pytest.mark.asyncio
    async def test_cache_expires(self):
        from nobla.voice.emotion.detector import EmotionDetector

        hume = AsyncMock(spec=EmotionEngine)
        hume.is_available.return_value = True
        hume.detect.return_value = EmotionResult(
            emotion="happy", confidence=0.9, source="hume"
        )
        local = AsyncMock(spec=EmotionEngine)
        detector = EmotionDetector(hume=hume, local=local, cache_ttl=0)

        await detector.detect("session-1", b"audio")
        await detector.detect("session-1", b"audio")
        assert hume.detect.await_count == 2  # no caching with ttl=0

    def test_clear_session(self):
        from nobla.voice.emotion.detector import EmotionDetector

        hume = AsyncMock(spec=EmotionEngine)
        local = AsyncMock(spec=EmotionEngine)
        detector = EmotionDetector(hume=hume, local=local, cache_ttl=30)
        detector._cache["session-1"] = (time.time(), MagicMock())
        detector.clear_session("session-1")
        assert "session-1" not in detector._cache
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_emotion.py::TestEmotionDetector -v`
Expected: FAIL — `nobla.voice.emotion.detector` not found

- [ ] **Step 3: Implement detector**

```python
# backend/nobla/voice/emotion/detector.py
"""Emotion detector with Hume AI -> local fallback and per-session caching."""
from __future__ import annotations

import logging
import time

from nobla.persona.models import EmotionResult
from nobla.voice.emotion.base import EmotionEngine

logger = logging.getLogger(__name__)


class EmotionDetector:
    """Fallback chain: Hume AI -> local model -> None."""

    def __init__(
        self,
        hume: EmotionEngine,
        local: EmotionEngine,
        cache_ttl: int = 30,
    ) -> None:
        self._hume = hume
        self._local = local
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, EmotionResult]] = {}

    async def detect(
        self, connection_id: str, audio: bytes
    ) -> EmotionResult | None:
        """Detect emotion with caching and fallback."""
        # Check cache
        if connection_id in self._cache:
            cached_time, cached_result = self._cache[connection_id]
            if time.time() - cached_time < self._cache_ttl:
                return cached_result

        result = await self._detect_uncached(audio)
        if result is not None:
            self._cache[connection_id] = (time.time(), result)
        return result

    async def _detect_uncached(self, audio: bytes) -> EmotionResult | None:
        """Try Hume, fall back to local, return None if both fail."""
        # 1. Try Hume AI
        if await self._hume.is_available():
            try:
                return await self._hume.detect(audio)
            except Exception:
                logger.warning("Hume AI failed, falling back to local")

        # 2. Try local model
        if await self._local.is_available():
            try:
                return await self._local.detect(audio)
            except Exception:
                logger.warning("Local emotion model failed")

        # 3. Both unavailable
        logger.info("No emotion detection available")
        return None

    def clear_session(self, connection_id: str) -> None:
        """Remove cached emotion for a disconnected session."""
        self._cache.pop(connection_id, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_emotion.py::TestEmotionDetector -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/voice/emotion/detector.py backend/tests/test_emotion.py
git commit -m "feat(emotion): add fallback detector with per-session caching"
```

---

## Task 11: Brain Router Integration

**Files:**
- Modify: `backend/nobla/brain/base_provider.py` — add `default_temperature` class attribute
- Modify: `backend/nobla/brain/router.py:99-133,135-167` — handle persona kwargs in `route()` and `stream_route()`
- Test: `backend/tests/test_persona_models.py` (append)

- [ ] **Step 1: Write failing test for router kwargs**

Append to `backend/tests/test_persona_models.py`:

```python
class TestRouterIntegration:
    @pytest.mark.asyncio
    async def test_route_with_system_prompt_extra(self):
        from nobla.brain.router import LLMRouter
        from nobla.brain.base_provider import LLMMessage, LLMResponse
        from unittest.mock import AsyncMock

        mock_provider = AsyncMock()
        mock_provider.name = "test"
        mock_provider.default_temperature = 1.0
        mock_provider.health_check = AsyncMock(return_value=True)
        mock_provider.generate.return_value = LLMResponse(
            content="hello", model="test", tokens_input=10,
            tokens_output=5, cost_usd=0.0, latency_ms=100,
        )

        router = LLMRouter(
            providers={"test": mock_provider},
            fallback_chain=["test"],
        )

        messages = [LLMMessage(role="user", content="hi")]
        result = await router.route(
            messages,
            system_prompt_extra="You are Professional.",
            temperature_bias=-0.3,
        )

        # Verify system_prompt_extra was prepended
        call_args = mock_provider.generate.call_args
        sent_messages = call_args[0][0]
        assert sent_messages[0].role == "system"
        assert "Professional" in sent_messages[0].content
        # Verify temperature_bias was applied
        sent_kwargs = call_args[1]
        assert sent_kwargs["temperature"] == pytest.approx(0.7)  # 1.0 + (-0.3)

    @pytest.mark.asyncio
    async def test_route_without_persona_kwargs(self):
        """Verify backward compatibility — no persona kwargs works as before."""
        from nobla.brain.router import LLMRouter
        from nobla.brain.base_provider import LLMMessage, LLMResponse
        from unittest.mock import AsyncMock

        mock_provider = AsyncMock()
        mock_provider.name = "test"
        mock_provider.default_temperature = 1.0
        mock_provider.health_check = AsyncMock(return_value=True)
        mock_provider.generate.return_value = LLMResponse(
            content="hello", model="test", tokens_input=10,
            tokens_output=5, cost_usd=0.0, latency_ms=100,
        )

        router = LLMRouter(
            providers={"test": mock_provider},
            fallback_chain=["test"],
        )

        messages = [LLMMessage(role="user", content="hi")]
        result = await router.route(messages)

        # No system message prepended
        call_args = mock_provider.generate.call_args
        sent_messages = call_args[0][0]
        assert sent_messages[0].role == "user"
        # No temperature kwarg
        assert "temperature" not in call_args[1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_persona_models.py::TestRouterIntegration -v`
Expected: FAIL — `default_temperature` not on provider / unexpected kwargs

- [ ] **Step 3: Add `default_temperature` to base_provider.py**

In `backend/nobla/brain/base_provider.py`, add class attribute to the abstract provider class (after the class docstring):

```python
    default_temperature: float = 1.0
```

- [ ] **Step 4: Provide complete replacement for `route()` in router.py**

Replace the `route()` method body (lines 99-133) with:

```python
    async def route(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        # --- Persona integration: extract persona kwargs before forwarding ---
        system_prompt_extra = kwargs.pop("system_prompt_extra", None)
        temperature_bias = kwargs.pop("temperature_bias", None)

        if system_prompt_extra:
            messages = [
                LLMMessage(role="system", content=system_prompt_extra),
                *messages,
            ]

        # --- Existing logic: classify and select providers ---
        last_message = messages[-1].content if messages else ""
        complexity, preferred = self.classify_complexity(last_message)

        errors: list[str] = []
        for provider_name in preferred:
            provider = self.providers.get(provider_name)
            if provider is None:
                continue
            try:
                # Apply temperature bias relative to provider default
                call_kwargs = dict(kwargs)
                if temperature_bias is not None:
                    base_temp = getattr(provider, "default_temperature", 1.0)
                    call_kwargs["temperature"] = max(
                        0.0, min(2.0, base_temp + temperature_bias)
                    )
                response = await provider.generate(messages, **call_kwargs)
                return response
            except Exception as exc:
                errors.append(f"{provider_name}: {exc}")
                continue

        raise RuntimeError(
            f"All providers failed for {complexity}: {'; '.join(errors)}"
        )
```

- [ ] **Step 5: Apply same changes to `stream_route()` (lines 135-167)**

Replace `stream_route()` with the same persona kwarg handling:

```python
    async def stream_route(
        self, messages: list[LLMMessage], **kwargs
    ) -> tuple[str, AsyncIterator[str]]:
        # --- Persona integration ---
        system_prompt_extra = kwargs.pop("system_prompt_extra", None)
        temperature_bias = kwargs.pop("temperature_bias", None)

        if system_prompt_extra:
            messages = [
                LLMMessage(role="system", content=system_prompt_extra),
                *messages,
            ]

        last_message = messages[-1].content if messages else ""
        complexity, preferred = self.classify_complexity(last_message)

        for provider_name in preferred:
            provider = self.providers.get(provider_name)
            if provider is None:
                continue
            try:
                call_kwargs = dict(kwargs)
                if temperature_bias is not None:
                    base_temp = getattr(provider, "default_temperature", 1.0)
                    call_kwargs["temperature"] = max(
                        0.0, min(2.0, base_temp + temperature_bias)
                    )
                return provider.name, provider.stream(messages, **call_kwargs)
            except Exception:
                continue

        raise RuntimeError(f"All providers failed for streaming {complexity}")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_persona_models.py::TestRouterIntegration -v`
Expected: PASS

- [ ] **Step 7: Run existing router tests to verify no regressions**

Run: `cd backend && python -m pytest tests/ -v -k "router or brain" --tb=short`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add backend/nobla/brain/base_provider.py backend/nobla/brain/router.py backend/tests/test_persona_models.py
git commit -m "feat(brain): add system_prompt_extra and temperature_bias to route() and stream_route()"
```

---

## Task 12: Persona Service (resolve_and_route)

**Files:**
- Create: `backend/nobla/persona/service.py`

- [ ] **Step 1: Implement service function**

```python
# backend/nobla/persona/service.py
"""Shared service function for persona-aware LLM routing."""
from __future__ import annotations

from nobla.persona.models import EmotionResult, PersonaContext
from nobla.persona.manager import PersonaManager
from nobla.persona.prompt import PromptBuilder
from nobla.brain.base_provider import LLMMessage, LLMResponse

# Module-level accessors (set during app lifespan).
_persona_manager: PersonaManager | None = None
_prompt_builder: PromptBuilder | None = None


def set_persona_manager(mgr: PersonaManager) -> None:
    global _persona_manager
    _persona_manager = mgr


def get_persona_manager() -> PersonaManager | None:
    return _persona_manager


def set_prompt_builder(builder: PromptBuilder) -> None:
    global _prompt_builder
    _prompt_builder = builder


def get_prompt_builder() -> PromptBuilder | None:
    return _prompt_builder


async def resolve_and_route(
    messages: list[LLMMessage],
    session_id: str,
    user_id: str,
    emotion: EmotionResult | None = None,
    router=None,
) -> tuple[LLMResponse, PersonaContext]:
    """Resolve persona, build prompt, route through LLM.

    Returns both the LLM response and the PersonaContext (needed by
    voice handler for TTS voice_config selection).
    """
    from nobla.gateway.websocket import get_router

    brain_router = router or get_router()
    manager = _persona_manager
    builder = _prompt_builder

    persona = await manager.resolve(session_id, user_id)
    ctx = builder.build(persona, emotion)

    response = await brain_router.route(
        messages,
        system_prompt_extra=ctx.system_prompt_addition,
        temperature_bias=ctx.temperature_bias,
    )
    return response, ctx
```

- [ ] **Step 2: Verify import works**

Run: `cd backend && python -c "from nobla.persona.service import resolve_and_route; print('OK')"`
Expected: Prints `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/nobla/persona/service.py
git commit -m "feat(persona): add resolve_and_route shared service function"
```

---

## Task 13: REST API Routes

**Files:**
- Create: `backend/nobla/gateway/persona_routes.py`
- Test: `backend/tests/test_persona_routes.py`

- [ ] **Step 1: Write failing tests for API routes**

```python
# backend/tests/test_persona_routes.py
"""Tests for persona REST API endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI

from nobla.gateway.persona_routes import create_persona_router
from nobla.persona.presets import PROFESSIONAL_ID


@pytest.fixture
def mock_manager():
    mgr = AsyncMock()
    mgr.list_for_user = AsyncMock(return_value=[])
    mgr.get_persona = AsyncMock(return_value=None)
    return mgr


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    return repo


@pytest.fixture
def app(mock_manager, mock_repo):
    app = FastAPI()
    router = create_persona_router(mock_manager, mock_repo)
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestPersonaRoutes:
    def test_list_personas(self, client, mock_manager):
        from nobla.persona.presets import PRESETS
        mock_manager.list_for_user.return_value = list(PRESETS.values())
        resp = client.get("/api/personas", headers={"X-User-Id": "user-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    def test_create_persona(self, client, mock_repo):
        mock_persona = MagicMock()
        mock_persona.id = "new-id"
        mock_persona.name = "Custom"
        mock_persona.personality = "test"
        mock_persona.language_style = "test"
        mock_persona.background = None
        mock_persona.voice_config = None
        mock_persona.rules = []
        mock_persona.temperature_bias = None
        mock_persona.max_response_length = None
        mock_persona.created_at = "2026-03-21"
        mock_persona.updated_at = "2026-03-21"
        mock_repo.create.return_value = mock_persona
        resp = client.post(
            "/api/personas",
            json={
                "name": "Custom",
                "personality": "test",
                "language_style": "test",
            },
            headers={"X-User-Id": "user-1"},
        )
        assert resp.status_code == 201

    def test_delete_builtin_rejected(self, client, mock_manager, mock_repo):
        from nobla.persona.presets import get_preset_by_id
        mock_manager.get_persona.return_value = get_preset_by_id(PROFESSIONAL_ID)
        resp = client.delete(
            f"/api/personas/{PROFESSIONAL_ID}",
            headers={"X-User-Id": "user-1"},
        )
        assert resp.status_code == 403

    def test_get_preference(self, client, mock_repo):
        mock_repo.get_default.return_value = None
        resp = client.get(
            "/api/user/persona-preference",
            headers={"X-User-Id": "user-1"},
        )
        assert resp.status_code == 200

    def test_set_preference(self, client, mock_repo):
        resp = client.put(
            "/api/user/persona-preference",
            json={"default_persona_id": PROFESSIONAL_ID},
            headers={"X-User-Id": "user-1"},
        )
        assert resp.status_code == 200
        mock_repo.set_default.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_persona_routes.py -v`
Expected: FAIL — `nobla.gateway.persona_routes` not found

- [ ] **Step 3: Implement routes**

```python
# backend/nobla/gateway/persona_routes.py
"""REST API routes for persona CRUD and user preference."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from nobla.persona.manager import PersonaManager
from nobla.persona.models import (
    PersonaCreate,
    PersonaResponse,
    PersonaUpdate,
    PreferenceResponse,
    PreferenceUpdate,
)
from nobla.persona.presets import PresetPersona
from nobla.persona.repository import PersonaRepository


def _to_response(persona) -> PersonaResponse:
    """Convert ORM row or preset to API response."""
    is_builtin = isinstance(persona, PresetPersona)
    return PersonaResponse(
        id=persona.id,
        name=persona.name,
        personality=persona.personality,
        language_style=persona.language_style,
        background=getattr(persona, "background", None),
        voice_config=getattr(persona, "voice_config", None),
        rules=list(persona.rules) if persona.rules else [],
        temperature_bias=getattr(persona, "temperature_bias", None),
        max_response_length=getattr(persona, "max_response_length", None),
        is_builtin=is_builtin,
        created_at=getattr(persona, "created_at", None),
        updated_at=getattr(persona, "updated_at", None),
    )


def create_persona_router(
    manager: PersonaManager, repo: PersonaRepository
) -> APIRouter:
    """Factory: creates the persona APIRouter with injected deps.

    NOTE: Auth uses X-User-Id header as a temporary placeholder.
    TODO: Replace with proper JWT dependency injection via
    Depends(get_current_user) that extracts user_id from the
    Authorization header (Phase 1 auth system).
    """
    router = APIRouter(prefix="/api", tags=["personas"])

    @router.get("/personas", response_model=list[PersonaResponse])
    async def list_personas(x_user_id: str = Header()):
        personas = await manager.list_for_user(x_user_id)
        return [_to_response(p) for p in personas]

    @router.post("/personas", response_model=PersonaResponse, status_code=201)
    async def create_persona(
        data: PersonaCreate, x_user_id: str = Header()
    ):
        try:
            persona = await repo.create(x_user_id, data)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return _to_response(persona)

    @router.get("/personas/{persona_id}", response_model=PersonaResponse)
    async def get_persona(persona_id: str, x_user_id: str = Header()):
        persona = await manager.get_persona(persona_id)
        if persona is None:
            raise HTTPException(status_code=404, detail="Persona not found")
        return _to_response(persona)

    @router.put("/personas/{persona_id}", response_model=PersonaResponse)
    async def update_persona(
        persona_id: str, data: PersonaUpdate, x_user_id: str = Header()
    ):
        existing = await manager.get_persona(persona_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Persona not found")
        if isinstance(existing, PresetPersona):
            raise HTTPException(
                status_code=403, detail="Cannot modify builtin persona"
            )
        try:
            result = await repo.update(persona_id, x_user_id, data)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        if result is None:
            raise HTTPException(status_code=404, detail="Persona not found")
        return _to_response(result)

    @router.delete("/personas/{persona_id}", status_code=204)
    async def delete_persona(
        persona_id: str, x_user_id: str = Header()
    ):
        existing = await manager.get_persona(persona_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Persona not found")
        if isinstance(existing, PresetPersona):
            raise HTTPException(
                status_code=403, detail="Cannot delete builtin persona"
            )
        deleted = await repo.delete(persona_id, x_user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Persona not found")

    @router.post(
        "/personas/{persona_id}/clone",
        response_model=PersonaResponse,
        status_code=201,
    )
    async def clone_persona(
        persona_id: str, x_user_id: str = Header()
    ):
        try:
            cloned = await manager.clone(persona_id, x_user_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return _to_response(cloned)

    @router.get(
        "/user/persona-preference", response_model=PreferenceResponse
    )
    async def get_preference(x_user_id: str = Header()):
        default_id = await repo.get_default(x_user_id)
        return PreferenceResponse(default_persona_id=default_id)

    @router.put(
        "/user/persona-preference", response_model=PreferenceResponse
    )
    async def set_preference(
        data: PreferenceUpdate, x_user_id: str = Header()
    ):
        await repo.set_default(x_user_id, data.default_persona_id)
        return PreferenceResponse(
            default_persona_id=data.default_persona_id
        )

    return router
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_persona_routes.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/gateway/persona_routes.py backend/tests/test_persona_routes.py
git commit -m "feat(persona): add REST API routes for persona CRUD and preference"
```

---

## Task 14: Voice Pipeline — Emotion Integration + STT-Only Mode

**Architecture decision:** The pipeline currently does STT → LLM → TTS in one call. For persona support, the voice handler needs to inject persona context between STT and LLM. We add a `transcribe_only()` method that does STT + emotion detection without LLM/TTS. The handler then calls `resolve_and_route()` and TTS separately. The existing `process_segment()` stays as-is for backward compatibility.

**Files:**
- Modify: `backend/nobla/voice/pipeline.py:15-22,27-36,67-108` — `PipelineResult` lives here (not models.py)

- [ ] **Step 1: Add `emotion_result` to PipelineResult in pipeline.py**

`PipelineResult` is defined in `backend/nobla/voice/pipeline.py` (lines 15-22). Modify it:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nobla.persona.models import EmotionResult

@dataclass
class PipelineResult:
    transcript: Transcript
    response_text: str
    audio_chunks: list[bytes] = field(default_factory=list)
    emotion_result: EmotionResult | None = None
```

- [ ] **Step 2: Add emotion_detector to VoicePipeline.__init__**

Modify the constructor (lines 27-36):

```python
def __init__(
    self,
    stt_engine: STTEngine,
    tts_engines: dict[str, TTSEngine],
    llm_router: object,
    emotion_detector=None,
) -> None:
    self._stt = stt_engine
    self._tts_engines = tts_engines
    self._router = llm_router
    self._sessions: dict[str, VoiceSession] = {}
    self._emotion_detector = emotion_detector
```

- [ ] **Step 3: Add `transcribe_and_detect()` method**

Add a new method that does STT + emotion only (no LLM, no TTS):

```python
async def transcribe_and_detect(
    self, session: VoiceSession, audio: bytes
) -> tuple[Transcript, EmotionResult | None]:
    """STT + emotion detection only. Handler controls LLM routing."""
    transcript = await self._stt.transcribe(audio)

    emotion_result = None
    if self._emotion_detector is not None:
        emotion_result = await self._emotion_detector.detect(
            session.connection_id, audio
        )

    return transcript, emotion_result
```

The existing `process_segment()` stays unchanged — it continues to work for non-persona voice paths. The voice handler in Task 15 will use `transcribe_and_detect()` + `resolve_and_route()` + TTS instead.

- [ ] **Step 4: Run existing voice tests to verify no regressions**

Run: `cd backend && python -m pytest tests/ -v -k "voice" --tb=short`
Expected: ALL PASS (no existing behavior changed, only new method added)

- [ ] **Step 5: Commit**

```bash
git add backend/nobla/voice/pipeline.py backend/nobla/voice/models.py
git commit -m "feat(voice): add emotion detection to voice pipeline"
```

---

## Task 15: Gateway Wiring — Lifespan, Handlers, Disconnect, Cleanup

**Files:**
- Modify: `backend/nobla/gateway/app.py:57-268`
- Modify: `backend/nobla/gateway/websocket.py:134-205,403-458,737-740`
- Modify: `backend/nobla/gateway/voice_handlers.py:94-138`
- Remove: `backend/nobla/voice/persona/` (empty placeholder, replaced by top-level `nobla/persona/`)

This is the integration task that wires everything together.

- [ ] **Step 1: Remove the empty `voice/persona/` placeholder**

```bash
rm -rf backend/nobla/voice/persona/
```

This directory only contained an empty `__init__.py` with a docstring. The top-level `nobla/persona/` module replaces it. Removing avoids confusion between `nobla.voice.persona` and `nobla.persona`.

- [ ] **Step 2: Add persona imports and accessors to websocket.py**

After the existing service accessor block (around line 205), add:

```python
from nobla.persona.service import set_persona_manager, set_prompt_builder
```

- [ ] **Step 3: Modify chat.send handler to use persona**

In `websocket.py`, modify the `chat.send` handler (around line 437) to use `resolve_and_route()`:

Replace the direct `router.route(llm_messages)` call with:

```python
    from nobla.persona.service import resolve_and_route

    response, persona_ctx = await resolve_and_route(
        messages=llm_messages,
        session_id=state.connection_id,
        user_id=state.user_id or "",
    )
```

The rest of the handler continues using `response.content`, `response.cost_usd`, etc. as before.

- [ ] **Step 4: Add persona + emotion cleanup on disconnect**

In `websocket.py`, in the `finally` block (around line 737-740), add:

```python
finally:
    manager.disconnect(state.connection_id)
    # Clean up persona session state + emotion cache
    from nobla.persona.service import get_persona_manager
    pm = get_persona_manager()
    if pm:
        pm.clear_session(state.connection_id)
```

- [ ] **Step 5: Modify voice handler to use transcribe_and_detect + resolve_and_route**

In `voice_handlers.py`, modify the `voice.audio` handler (around line 122-138). Replace the single `process_segment()` call with the persona-aware flow:

```python
    pipeline = get_voice_pipeline()
    session = pipeline.get_session(state.connection_id)

    # Step 1: STT + emotion detection (pipeline)
    transcript, emotion_result = await pipeline.transcribe_and_detect(
        session, audio_data
    )

    # Step 2: Persona-aware LLM routing (service)
    from nobla.persona.service import resolve_and_route
    from nobla.brain.base_provider import LLMMessage

    llm_messages = [LLMMessage(role="user", content=transcript.text)]
    response, persona_ctx = await resolve_and_route(
        messages=llm_messages,
        session_id=state.connection_id,
        user_id=state.user_id or "",
        emotion=emotion_result,
    )

    # Step 3: TTS with persona voice_config
    tts_engine_name = (
        persona_ctx.voice_config.get("engine", session.config.tts_engine)
        if persona_ctx.voice_config
        else session.config.tts_engine
    )
    tts_engine = pipeline._tts_engines.get(tts_engine_name)
    audio_chunks = []
    if tts_engine:
        async for chunk in tts_engine.synthesize(response.content):
            audio_chunks.append(chunk)

    return {
        "transcript": transcript.text,
        "language": transcript.language,
        "response": response.content,
        "audio_chunks": [
            base64.b64encode(c).decode() for c in audio_chunks
        ],
        "emotion": emotion_result.model_dump() if emotion_result else None,
    }
```

- [ ] **Step 6: Add initialization to app.py lifespan**

In `backend/nobla/gateway/app.py`, inside the `lifespan()` function, after voice pipeline initialization (around line 231), add:

```python
    # --- Phase 3B: Persona system ---
    from nobla.persona.repository import PersonaRepository
    from nobla.persona.manager import PersonaManager
    from nobla.persona.prompt import PromptBuilder
    from nobla.persona.service import set_persona_manager, set_prompt_builder
    from nobla.voice.emotion.hume import HumeEmotionEngine
    from nobla.voice.emotion.local import LocalEmotionEngine
    from nobla.voice.emotion.detector import EmotionDetector
    from nobla.gateway.persona_routes import create_persona_router

    # Uses db.session_factory (async_sessionmaker), NOT a single session
    persona_repo = PersonaRepository(db.session_factory)
    persona_manager = PersonaManager(repo=persona_repo)
    prompt_builder = PromptBuilder()
    set_persona_manager(persona_manager)
    set_prompt_builder(prompt_builder)

    # Emotion detection
    hume_engine = HumeEmotionEngine(api_key=settings.persona.hume_api_key)
    local_engine = LocalEmotionEngine(model_name=settings.persona.local_emotion_model)
    emotion_detector = EmotionDetector(
        hume=hume_engine,
        local=local_engine,
        cache_ttl=settings.persona.emotion_cache_ttl,
    )

    # Pass emotion detector to voice pipeline
    if voice_pipeline:
        voice_pipeline._emotion_detector = emotion_detector

    # Register persona routes
    persona_router = create_persona_router(persona_manager, persona_repo)
    app.include_router(persona_router)
```

- [ ] **Step 7: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add -A backend/nobla/gateway/ backend/nobla/voice/persona/
git commit -m "feat(persona): wire persona system into gateway lifespan and handlers, remove voice/persona placeholder"
```

---

## Task 16: Integration Tests

**Files:**
- Create: `backend/tests/integration/test_persona_flow.py`

- [ ] **Step 1: Write integration tests**

```python
# backend/tests/integration/test_persona_flow.py
"""Integration tests for the full persona flow."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from nobla.persona.manager import PersonaManager
from nobla.persona.prompt import PromptBuilder
from nobla.persona.presets import PROFESSIONAL_ID, FRIENDLY_ID
from nobla.persona.models import EmotionResult
from nobla.voice.emotion.detector import EmotionDetector
from nobla.voice.emotion.base import EmotionEngine


class TestPersonaFlow:
    """Test the full resolve -> prompt -> emotion flow."""

    @pytest.mark.asyncio
    async def test_full_text_chat_flow(self):
        """Text chat: resolve persona, build prompt, no emotion."""
        repo = AsyncMock()
        repo.get_default.return_value = FRIENDLY_ID
        manager = PersonaManager(repo=repo)
        builder = PromptBuilder()

        persona = await manager.resolve("session-1", "user-1")
        ctx = builder.build(persona, emotion=None)

        assert "Friendly" in ctx.system_prompt_addition
        assert "casual, warm" in ctx.system_prompt_addition
        assert ctx.temperature_bias == 0.2
        assert "mood" not in ctx.system_prompt_addition.lower()

    @pytest.mark.asyncio
    async def test_full_voice_flow_with_emotion(self):
        """Voice chat: resolve persona, detect emotion, build prompt."""
        repo = AsyncMock()
        repo.get_default.return_value = None
        manager = PersonaManager(repo=repo)
        builder = PromptBuilder()

        persona = await manager.resolve("session-1", "user-1")
        emotion = EmotionResult(
            emotion="frustrated",
            confidence=0.82,
            secondary="anxious",
            source="hume",
        )
        ctx = builder.build(persona, emotion=emotion)

        assert "Professional" in ctx.system_prompt_addition
        assert "frustrated" in ctx.system_prompt_addition
        assert "0.82" in ctx.system_prompt_addition

    @pytest.mark.asyncio
    async def test_session_persona_switch(self):
        """Switch persona mid-conversation."""
        repo = AsyncMock()
        repo.get_default.return_value = None
        manager = PersonaManager(repo=repo)
        builder = PromptBuilder()

        # Start with default (Professional)
        p1 = await manager.resolve("session-1", "user-1")
        assert p1.name == "Professional"

        # Switch to Military
        from nobla.persona.presets import MILITARY_ID
        manager.set_session_persona("session-1", MILITARY_ID)
        p2 = await manager.resolve("session-1", "user-1")
        assert p2.name == "Military"

        ctx = builder.build(p2, emotion=None)
        assert "terse, action-oriented" in ctx.system_prompt_addition

    @pytest.mark.asyncio
    async def test_emotion_fallback_chain(self):
        """Hume fails -> local succeeds."""
        hume = AsyncMock(spec=EmotionEngine)
        hume.is_available.return_value = True
        hume.detect.side_effect = Exception("API timeout")

        local = AsyncMock(spec=EmotionEngine)
        local.is_available.return_value = True
        local.detect.return_value = EmotionResult(
            emotion="curious", confidence=0.65, source="local"
        )

        detector = EmotionDetector(hume=hume, local=local, cache_ttl=30)
        result = await detector.detect("conn-1", b"audio_data")

        assert result is not None
        assert result.emotion == "curious"
        assert result.source == "local"

    @pytest.mark.asyncio
    async def test_emotion_both_fail_gracefully(self):
        """Both engines fail -> None, persona works without emotion."""
        hume = AsyncMock(spec=EmotionEngine)
        hume.is_available.return_value = False
        local = AsyncMock(spec=EmotionEngine)
        local.is_available.return_value = False

        detector = EmotionDetector(hume=hume, local=local, cache_ttl=30)
        result = await detector.detect("conn-1", b"audio_data")
        assert result is None

        # Persona still works without emotion
        repo = AsyncMock()
        repo.get_default.return_value = None
        manager = PersonaManager(repo=repo)
        builder = PromptBuilder()
        persona = await manager.resolve("session-1", "user-1")
        ctx = builder.build(persona, emotion=None)
        assert "Professional" in ctx.system_prompt_addition
        assert "mood" not in ctx.system_prompt_addition.lower()
```

- [ ] **Step 2: Run integration tests**

Run: `cd backend && python -m pytest tests/integration/test_persona_flow.py -v`
Expected: ALL PASS

- [ ] **Step 3: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_persona_flow.py
git commit -m "test(persona): add integration tests for full persona + emotion flow"
```

---

## Task 17: Update Package Exports + Final Cleanup

**Files:**
- Modify: `backend/nobla/persona/__init__.py`
- Modify: `backend/nobla/voice/emotion/__init__.py`

- [ ] **Step 1: Update persona package exports**

```python
# backend/nobla/persona/__init__.py
"""Persona system — data models, presets, CRUD, prompt building."""
from nobla.persona.models import (
    EmotionResult,
    PersonaContext,
    PersonaCreate,
    PersonaResponse,
    PersonaUpdate,
)
from nobla.persona.manager import PersonaManager
from nobla.persona.prompt import PromptBuilder
from nobla.persona.presets import PresetPersona
from nobla.persona.service import resolve_and_route

__all__ = [
    "EmotionResult",
    "PersonaContext",
    "PersonaCreate",
    "PersonaManager",
    "PersonaResponse",
    "PersonaUpdate",
    "PresetPersona",
    "PromptBuilder",
    "resolve_and_route",
]
```

- [ ] **Step 2: Update emotion __init__.py** (deferred from Task 8 — detector.py didn't exist yet)

```python
# backend/nobla/voice/emotion/__init__.py
"""Emotion detection subpackage — Hume AI + local wav2vec2 fallback."""
from nobla.voice.emotion.base import EmotionEngine
from nobla.voice.emotion.detector import EmotionDetector

__all__ = ["EmotionEngine", "EmotionDetector"]
```

- [ ] **Step 3: Run full test suite one final time**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add backend/nobla/persona/__init__.py backend/nobla/voice/emotion/__init__.py
git commit -m "chore(persona): update package exports and final cleanup"
```

---

## Summary

| Task | Component | New Lines | Test Lines |
|------|-----------|-----------|------------|
| 1 | PersonaSettings | ~15 | ~15 |
| 2 | Data models + schemas | ~140 | ~80 |
| 3 | Alembic migration | ~40 | — |
| 4 | Bundled presets | ~90 | ~30 |
| 5 | CRUD repository | ~95 | ~45 |
| 6 | Prompt builder | ~50 | ~60 |
| 7 | Persona manager | ~100 | ~60 |
| 8-9 | Emotion base + local + Hume | ~175 | ~50 |
| 10 | Emotion detector | ~60 | ~70 |
| 11 | Router integration | ~20 | ~25 |
| 12 | Persona service | ~55 | — |
| 13 | REST API routes | ~120 | ~60 |
| 14 | Pipeline emotion | ~15 | — |
| 15 | Gateway wiring | ~40 | — |
| 16 | Integration tests | — | ~80 |
| 17 | Package exports | ~20 | — |
| **Total** | | **~1035** | **~575** |

17 tasks, ~75 steps, estimated total new code ~1035 lines + ~575 test lines.
