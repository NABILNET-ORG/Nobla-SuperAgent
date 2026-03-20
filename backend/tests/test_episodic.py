import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from nobla.memory.episodic import EpisodicMemory


@pytest.fixture
def episodic():
    db_session = AsyncMock()
    # Mock the execute -> scalars -> all chain for SELECT queries
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.rowcount = 1
    db_session.execute.return_value = mock_result
    # Mock add as a sync method (not a coroutine)
    db_session.add = MagicMock()
    return EpisodicMemory(db_session=db_session)


@pytest.mark.asyncio
async def test_store_message(episodic):
    msg = await episodic.store_message(
        conversation_id=uuid.uuid4(),
        role="user",
        content="Hello world",
        metadata={"keywords": ["hello"], "entities": []},
    )
    assert msg is not None


@pytest.mark.asyncio
async def test_get_conversation_messages(episodic):
    conv_id = uuid.uuid4()
    messages = await episodic.get_messages(conv_id, limit=10)
    assert isinstance(messages, list)


@pytest.mark.asyncio
async def test_list_conversations(episodic):
    user_id = uuid.uuid4()
    conversations = await episodic.list_conversations(user_id, limit=20, offset=0)
    assert isinstance(conversations, list)


@pytest.mark.asyncio
async def test_create_conversation(episodic):
    conv = await episodic.create_conversation(
        user_id=uuid.uuid4(),
        title="Test conversation",
    )
    assert conv is not None


@pytest.mark.asyncio
async def test_archive_conversation(episodic):
    result = await episodic.archive_conversation(uuid.uuid4())
    assert isinstance(result, bool)
