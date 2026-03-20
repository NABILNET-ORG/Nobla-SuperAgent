from __future__ import annotations

from typing import Any
from sqlalchemy import String, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from nobla.db.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    passphrase_hash: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[str] = mapped_column(
        server_default=text("NOW()"), nullable=False
    )
    last_active_at: Mapped[str | None] = mapped_column(nullable=True)
    settings_: Mapped[dict[str, Any]] = mapped_column(
        "settings",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
