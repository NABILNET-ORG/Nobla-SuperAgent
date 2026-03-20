from __future__ import annotations

from decimal import Decimal
from typing import Any
from sqlalchemy import (
    String, Integer, Float, ForeignKey, UniqueConstraint, text
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

from nobla.db.models.base import Base


class MemoryNode(Base):
    __tablename__ = "memory_nodes"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(String, nullable=False)
    note_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    keywords: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    context_description: Mapped[str | None] = mapped_column(String, nullable=True)
    embedding_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    access_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    last_accessed: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[str] = mapped_column(
        server_default=text("NOW()"), nullable=False
    )
    updated_at: Mapped[str] = mapped_column(
        server_default=text("NOW()"), nullable=False
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    source_conversation_ids: Mapped[list[str] | None] = mapped_column(
        ARRAY(UUID(as_uuid=False)), nullable=True
    )
    decay_factor: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("1.0")
    )


class MemoryLink(Base):
    __tablename__ = "memory_links"

    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "link_type", name="uq_memory_links_src_tgt_type"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("memory_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("memory_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    link_type: Mapped[str] = mapped_column(String(64), nullable=False)
    strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[str] = mapped_column(
        server_default=text("NOW()"), nullable=False
    )


class Procedure(Base):
    __tablename__ = "procedures"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    steps: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    success_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    bayesian_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[str] = mapped_column(
        server_default=text("NOW()"), nullable=False
    )
    updated_at: Mapped[str] = mapped_column(
        server_default=text("NOW()"), nullable=False
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    beta_success: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("2.0")
    )
    beta_failure: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("1.0")
    )
    trigger_context: Mapped[str | None] = mapped_column(String, nullable=True)
    last_triggered: Mapped[str | None] = mapped_column(String, nullable=True)


class ProcedureSource(Base):
    __tablename__ = "procedure_sources"

    procedure_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("procedures.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    conversation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
