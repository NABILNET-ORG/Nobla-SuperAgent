"""Phase 2A: memory columns and GIN indexes.

Revision ID: 001_phase2a
Revises: None
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID, JSONB

revision = "001_phase2a"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Conversation columns ---
    op.add_column("conversations", sa.Column("summary", sa.String(), nullable=True))
    op.add_column("conversations", sa.Column("topics", ARRAY(sa.String()), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("message_count", sa.Integer(), server_default="0", nullable=False),
    )

    # --- Message columns ---
    op.add_column(
        "messages",
        sa.Column(
            "parent_message_id",
            UUID(as_uuid=False),
            sa.ForeignKey("messages.id"),
            nullable=True,
        ),
    )
    op.add_column("messages", sa.Column("entities_extracted", JSONB(), nullable=True))

    # --- MemoryNode columns ---
    op.add_column(
        "memory_nodes",
        sa.Column("source_conversation_ids", ARRAY(UUID(as_uuid=False)), nullable=True),
    )
    op.add_column(
        "memory_nodes",
        sa.Column("decay_factor", sa.Float(), server_default="1.0", nullable=False),
    )

    # --- Procedure columns ---
    op.add_column(
        "procedures",
        sa.Column("beta_success", sa.Float(), server_default="2.0", nullable=False),
    )
    op.add_column(
        "procedures",
        sa.Column("beta_failure", sa.Float(), server_default="1.0", nullable=False),
    )
    op.add_column("procedures", sa.Column("trigger_context", sa.String(), nullable=True))
    op.add_column("procedures", sa.Column("last_triggered", sa.String(), nullable=True))

    # --- GIN indexes for full-text search (BM25 via tsvector) ---
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_content_fts "
        "ON messages USING GIN (to_tsvector('english', content))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversations_summary_fts "
        "ON conversations USING GIN (to_tsvector('english', summary))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversations_topics "
        "ON conversations USING GIN (topics)"
    )

    # --- Memory retrieval indexes ---
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_nodes_retrieval "
        "ON memory_nodes (user_id, note_type, confidence DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_links_source "
        "ON memory_links (source_id, link_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_links_target "
        "ON memory_links (target_id, link_type)"
    )


def downgrade() -> None:
    # --- Drop indexes ---
    op.execute("DROP INDEX IF EXISTS idx_memory_links_target")
    op.execute("DROP INDEX IF EXISTS idx_memory_links_source")
    op.execute("DROP INDEX IF EXISTS idx_memory_nodes_retrieval")
    op.execute("DROP INDEX IF EXISTS idx_conversations_topics")
    op.execute("DROP INDEX IF EXISTS idx_conversations_summary_fts")
    op.execute("DROP INDEX IF EXISTS idx_messages_content_fts")

    # --- Drop columns (reverse order) ---
    op.drop_column("procedures", "last_triggered")
    op.drop_column("procedures", "trigger_context")
    op.drop_column("procedures", "beta_failure")
    op.drop_column("procedures", "beta_success")
    op.drop_column("memory_nodes", "decay_factor")
    op.drop_column("memory_nodes", "source_conversation_ids")
    op.drop_column("messages", "entities_extracted")
    op.drop_column("messages", "parent_message_id")
    op.drop_column("conversations", "message_count")
    op.drop_column("conversations", "topics")
    op.drop_column("conversations", "summary")
