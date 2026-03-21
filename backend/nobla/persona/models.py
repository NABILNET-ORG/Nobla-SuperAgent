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
    background: str | None = Field(default=None, max_length=2000)
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
