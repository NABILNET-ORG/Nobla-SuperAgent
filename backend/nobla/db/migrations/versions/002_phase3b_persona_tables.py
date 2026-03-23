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
