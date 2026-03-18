from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_input: int
    tokens_output: int
    cost_usd: float
    latency_ms: int

    @property
    def total_tokens(self) -> int:
        return self.tokens_input + self.tokens_output


@dataclass
class LLMMessage:
    role: str
    content: str


class BaseLLMProvider(ABC):
    def __init__(
        self,
        name: str,
        model: str,
        is_local: bool = False,
        cost_per_input_token: float = 0.0,
        cost_per_output_token: float = 0.0,
    ):
        self.name = name
        self.model = model
        self.is_local = is_local
        self.cost_per_input_token = cost_per_input_token
        self.cost_per_output_token = cost_per_output_token

    @abstractmethod
    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse: ...

    @abstractmethod
    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]: ...

    @abstractmethod
    async def count_tokens(self, text: str) -> int: ...

    @abstractmethod
    async def health_check(self) -> bool: ...

    def estimate_cost(self, tokens_input: int, tokens_output: int) -> float:
        return (tokens_input * self.cost_per_input_token) + (tokens_output * self.cost_per_output_token)
