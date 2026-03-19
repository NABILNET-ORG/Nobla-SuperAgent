import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from nobla.memory.orchestrator import MemoryOrchestrator


@pytest.fixture
def mock_session():
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.rowcount = 1
    session.execute.return_value = mock_result
    session.add = MagicMock()
    return session


@pytest.fixture
def orchestrator(mock_session):
    session_factory = MagicMock()
    # Make the async context manager return our mock session
    session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    return MemoryOrchestrator(
        session_factory=session_factory,
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
