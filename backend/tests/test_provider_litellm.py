import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nobla.brain.providers.litellm_proxy import LiteLLMProvider
from nobla.brain.base_provider import LLMMessage


@pytest.mark.asyncio
async def test_generate():
    with patch("nobla.brain.providers.litellm_proxy.litellm") as mock_litellm:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "LiteLLM response"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 15
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)

        prov = LiteLLMProvider(model="together_ai/meta-llama/Llama-3-70b")
        result = await prov.generate([LLMMessage(role="user", content="Hi")])

        assert result.content == "LiteLLM response"
        assert result.tokens_input == 10
        assert result.tokens_output == 15


@pytest.mark.asyncio
async def test_health_check_success():
    with patch("nobla.brain.providers.litellm_proxy.litellm") as mock_litellm:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "pong"
        mock_response.usage.prompt_tokens = 1
        mock_response.usage.completion_tokens = 1
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)

        prov = LiteLLMProvider(model="together_ai/meta-llama/Llama-3-70b")
        assert await prov.health_check() is True
