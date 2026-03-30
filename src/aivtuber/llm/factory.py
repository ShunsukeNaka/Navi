"""config の provider に応じて LLMClient を返す"""
from __future__ import annotations

from ..core.config import LLMConfig
from .base import LLMClient


def create_llm_client(cfg: LLMConfig) -> LLMClient:
    provider = cfg.provider.lower()

    if provider == "gemini":
        from .gemini import GeminiClient
        return GeminiClient(model=cfg.model)

    if provider == "groq":
        from .groq import GroqClient
        return GroqClient(model=cfg.model)

    if provider == "claude":
        from .claude import ClaudeClient
        return ClaudeClient(model=cfg.model)

    if provider == "ollama":
        from .ollama import OllamaClient
        return OllamaClient(model=cfg.model)

    raise ValueError(f"未対応のLLMプロバイダー: {provider!r}  (gemini/groq/claude/ollama)")
