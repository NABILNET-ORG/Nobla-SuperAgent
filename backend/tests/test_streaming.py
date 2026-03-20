import asyncio
import pytest
from unittest.mock import AsyncMock
from nobla.brain.streaming import StreamSession, StreamState


@pytest.mark.asyncio
async def test_stream_session_sends_tokens():
    ws = AsyncMock()
    session = StreamSession(ws=ws, conversation_id="conv-1", model="gemini-2.0-flash")
    async def token_gen():
        yield "Hello"
        yield " world"
    await session.run(token_gen())
    calls = ws.send_json.call_args_list
    assert len(calls) == 4  # start + 2 tokens + end
    assert calls[0].args[0]["method"] == "chat.stream.start"
    assert calls[1].args[0]["method"] == "chat.stream.token"
    assert calls[1].args[0]["params"]["content"] == "Hello"
    assert calls[2].args[0]["params"]["content"] == " world"
    assert calls[3].args[0]["method"] == "chat.stream.end"


@pytest.mark.asyncio
async def test_stream_session_collects_full_text():
    ws = AsyncMock()
    session = StreamSession(ws=ws, conversation_id="conv-1", model="test")
    async def token_gen():
        yield "Hello"
        yield " world"
    await session.run(token_gen())
    assert session.full_text == "Hello world"
    assert session.token_count == 2


@pytest.mark.asyncio
async def test_stream_session_cancellation():
    ws = AsyncMock()
    session = StreamSession(ws=ws, conversation_id="conv-1", model="test")
    async def slow_stream():
        yield "Hello"
        await asyncio.sleep(10)
        yield "never reached"
    session.cancel()
    await session.run(slow_stream())
    assert session.full_text == ""
    assert session.state == StreamState.CANCELLED


@pytest.mark.asyncio
async def test_stream_session_error_handling():
    ws = AsyncMock()
    session = StreamSession(ws=ws, conversation_id="conv-1", model="test")
    async def error_stream():
        yield "partial"
        raise RuntimeError("Provider exploded")
    await session.run(error_stream())
    assert session.state == StreamState.ERROR
    assert session.full_text == "partial"
    last_call = ws.send_json.call_args_list[-1]
    assert last_call.args[0]["method"] == "chat.stream.error"
