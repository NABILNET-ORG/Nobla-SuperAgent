from __future__ import annotations

from decimal import Decimal
from typing import Any
from sqlalchemy import String, Boolean, Integer, Numeric, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

from nobla.db.models.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

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
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
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
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    topics: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    messages: Mapped[list[Message]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
        Index("ix_messages_created_at", "created_at"),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    conversation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tokens_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 8), nullable=True
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(
        server_default=text("NOW()"), nullable=False
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    embedding_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    memory_tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    memory_keywords: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    parent_message_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("messages.id"),
        nullable=True,
    )
    entities_extracted: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    conversation: Mapped[Conversation] = relationship(
        "Conversation", back_populates="messages"
    )
