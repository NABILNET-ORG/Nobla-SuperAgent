import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nobla.brain.providers.openai import OpenAIProvider
from nobla.brain.base_provider import LLMMessage


@pytest.fixture
def provider():
    with patch("nobla.brain.providers.openai.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        prov = OpenAIProvider(api_key="sk-test-key")
        prov._client = mock_client
        yield prov, mock_client


@pytest.mark.asyncio
async def test_generate(provider):
    prov, mock_client = provider
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hello from GPT"
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 20
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await prov.generate([LLMMessage(role="user", content="Hi")])

    assert result.content == "Hello from GPT"
    assert result.tokens_input == 10
    assert result.tokens_output == 20


@pytest.mark.asyncio
async def test_health_check(provider):
    prov, mock_client = provider
    mock_client.models.list = AsyncMock(return_value=[])
    assert await prov.health_check() is True


@pytest.mark.asyncio
async def test_health_check_failure(provider):
    prov, mock_client = provider
    mock_client.models.list = AsyncMock(side_effect=Exception("fail"))
    assert await prov.health_check() is False
