"""
Anthropic Claude クライアント

.env に ANTHROPIC_API_KEY=... を追加
"""
from __future__ import annotations

from typing import AsyncIterator

import anthropic

from .base import LLMClient


class ClaudeClient(LLMClient):
    def __init__(self, model: str = "claude-opus-4-5"):
        self._model = model
        self._client = anthropic.AsyncAnthropic()

    async def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
    ) -> str:
        msg = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        )
        return msg.content[0].text

    async def stream(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        ) as s:
            async for text in s.text_stream:
                yield text
