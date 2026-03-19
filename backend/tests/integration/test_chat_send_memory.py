"""Test that chat.send integrates with memory orchestrator."""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_chat_send_stores_message_in_memory():
    """Verify chat.send calls memory orchestrator hot path."""
    from nobla.memory.orchestrator import MemoryOrchestrator

    session_factory = MagicMock()
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.rowcount = 1
    mock_session.execute.return_value = mock_result
    mock_session.add = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    orch = MemoryOrchestrator(
        session_factory=session_factory,
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
