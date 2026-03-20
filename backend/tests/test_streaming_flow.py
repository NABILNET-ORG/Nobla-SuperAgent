import pytest
from unittest.mock import AsyncMock
from nobla.brain.streaming import StreamSession, StreamState


@pytest.mark.asyncio
async def test_full_stream_lifecycle():
    ws = AsyncMock()
    session = StreamSession(
        ws=ws, conversation_id="test-conv", model="gemini-2.0-flash"
    )

    async def mock_provider_stream():
        yield "The"
        yield " answer"
        yield " is"
        yield " 42"

    await session.run(mock_provider_stream())
    assert session.state == StreamState.COMPLETED
    assert session.full_text == "The answer is 42"
    assert session.token_count == 4

    calls = ws.send_json.call_args_list
    methods = [c.args[0]["method"] for c in calls]
    assert methods[0] == "chat.stream.start"
    assert methods[-1] == "chat.stream.end"
    assert all(m == "chat.stream.token" for m in methods[1:-1])
    end_params = calls[-1].args[0]["params"]
    assert end_params["tokens_output"] == 4
    assert end_params["model"] == "gemini-2.0-flash"
