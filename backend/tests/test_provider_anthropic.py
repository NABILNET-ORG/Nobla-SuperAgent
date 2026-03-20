import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nobla.brain.providers.anthropic import AnthropicProvider
from nobla.brain.base_provider import LLMMessage


@pytest.fixture
def provider():
    with patch("nobla.brain.providers.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        prov = AnthropicProvider(api_key="sk-ant-test")
        prov._client = mock_client
        yield prov, mock_client


@pytest.mark.asyncio
async def test_generate(provider):
    prov, mock_client = provider
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hello from Claude")]
    mock_response.usage.input_tokens = 15
    mock_response.usage.output_tokens = 25
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    result = await prov.generate([LLMMessage(role="user", content="Hi")])

    assert result.content == "Hello from Claude"
    assert result.tokens_input == 15
    assert result.tokens_output == 25


@pytest.mark.asyncio
async def test_system_message_extraction(provider):
    prov, mock_client = provider
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="OK")]
    mock_response.usage.input_tokens = 5
    mock_response.usage.output_tokens = 1
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    msgs = [
        LLMMessage(role="system", content="Be helpful"),
        LLMMessage(role="user", content="Hi"),
    ]
    await prov.generate(msgs)

    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs.kwargs["system"] == "Be helpful"
