def test_all_models_importable():
    from nobla.db.models import (
        Base, User, Conversation, Message,
        MemoryNode, MemoryLink, Procedure, ProcedureSource,
        ConversationSummary, LLMUsage, AuditLog,
    )
    table_names = {t.name for t in Base.metadata.sorted_tables}
    expected = {
        "users", "conversations", "messages",
        "memory_nodes", "memory_links", "procedures", "procedure_sources",
        "conversation_summaries", "llm_usage", "audit_logs",
    }
    assert expected == table_names
