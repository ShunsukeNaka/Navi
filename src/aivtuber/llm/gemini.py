"""
Google Gemini クライアント（新SDK: google-genai）

APIキー取得: https://aistudio.google.com/app/apikey
.env に GEMINI_API_KEY=... を追加

無料枠モデル:
  gemini-1.5-flash   （無料枠あり・安定）
  gemini-2.0-flash   （新しいが無料枠が地域によって異なる）
"""
from __future__ import annotations

import os
from typing import AsyncIterator

from .base import LLMClient


class GeminiClient(LLMClient):
    def __init__(self, model: str = "gemini-1.5-flash"):
        self._model = model

    def _get_client(self):
        from google import genai
        return genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def _to_contents(self, messages: list[dict]) -> list:
        """Claude形式 → Gemini形式に変換"""
        from google.genai import types
        contents = []
        for m in messages:
            role = "model" if m["role"] == "assistant" else "user"
            contents.append(types.Content(role=role, parts=[types.Part(text=m["content"])]))
        return contents

    async def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
    ) -> str:
        from google.genai import types
        client = self._get_client()
        resp = await client.aio.models.generate_content(
            model=self._model,
            contents=self._to_contents(messages),
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )
        return resp.text

    async def stream(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        from google.genai import types
        client = self._get_client()
        async for chunk in await client.aio.models.generate_content_stream(
            model=self._model,
            contents=self._to_contents(messages),
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        ):
            if chunk.text:
                yield chunk.text
