"""
Groq クライアント（無料枠あり・高速）

APIキー取得: https://console.groq.com
.env に GROQ_API_KEY=... を追加

おすすめモデル:
  llama-3.1-70b-versatile  （高品質）
  llama-3.1-8b-instant     （超高速）
"""
from __future__ import annotations

import os
from typing import AsyncIterator

from .base import LLMClient


class GroqClient(LLMClient):
    def __init__(self, model: str = "llama-3.1-70b-versatile"):
        self._model = model

    def _get_client(self):
        from groq import AsyncGroq
        return AsyncGroq(api_key=os.environ["GROQ_API_KEY"])

    async def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
    ) -> str:
        client = self._get_client()
        resp = await client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system}] + messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content

    async def stream(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        client = self._get_client()
        stream = await client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system}] + messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        async for chunk in stream:
            text = chunk.choices[0].delta.content
            if text:
                yield text
