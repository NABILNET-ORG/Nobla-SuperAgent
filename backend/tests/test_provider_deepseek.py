import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nobla.brain.providers.deepseek import DeepSeekProvider
from nobla.brain.base_provider import LLMMessage


@pytest.fixture
def provider():
    with patch("nobla.brain.providers.deepseek.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        prov = DeepSeekProvider(api_key="sk-test")
        prov._client = mock_client
        yield prov, mock_client


@pytest.mark.asyncio
async def test_generate(provider):
    prov, mock_client = provider
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "DeepSeek response"
    mock_response.usage.prompt_tokens = 8
    mock_response.usage.completion_tokens = 12
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await prov.generate([LLMMessage(role="user", content="Hi")])

    assert result.content == "DeepSeek response"
    assert result.tokens_input == 8
    assert result.tokens_output == 12


@pytest.mark.asyncio
async def test_uses_deepseek_base_url():
    with patch("nobla.brain.providers.deepseek.AsyncOpenAI") as mock_cls:
        DeepSeekProvider(api_key="sk-test")
        call_kwargs = mock_cls.call_args
        assert call_kwargs.kwargs["base_url"] == "https://api.deepseek.com"
