"""設定ファイルの読み込みとバリデーション"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


# ── TTS ───────────────────────────────────────────────────────────────────────

class VoicevoxProsody(BaseModel):
    speed_scale: float = 1.0
    pitch_scale: float = 0.0
    intonation_scale: float = 1.2
    volume_scale: float = 1.0

class VoicevoxConfig(BaseModel):
    base_url: str = "http://localhost:50021"
    speaker_id: int = 3
    default_prosody: VoicevoxProsody = Field(default_factory=VoicevoxProsody)

class TTSConfig(BaseModel):
    provider: str = "voicevox"
    voicevox: VoicevoxConfig = Field(default_factory=VoicevoxConfig)


# ── STT ───────────────────────────────────────────────────────────────────────

class VADConfig(BaseModel):
    enabled: bool = True
    silence_threshold_ms: int = 800

class STTConfig(BaseModel):
    provider: str = "faster_whisper"
    model_size: str = "small"
    device: str = "cpu"
    language: str = "ja"
    vad: VADConfig = Field(default_factory=VADConfig)


# ── LLM ───────────────────────────────────────────────────────────────────────

class MemoryConfig(BaseModel):
    short_term_turns: int = 10
    long_term_enabled: bool = False

class LLMConfig(BaseModel):
    provider: str = "gemini"   # "claude" | "gemini" | "groq" | "ollama"
    model: str = "gemini-1.5-flash"
    temperature: float = 0.85
    max_tokens: int = 300
    max_sentences: int = 3
    memory: MemoryConfig = Field(default_factory=MemoryConfig)


# ── Character ─────────────────────────────────────────────────────────────────

class EmotionStyle(BaseModel):
    description: str = ""
    speech_style: str = ""
    tts_speed: float = 1.0
    tts_pitch: float = 0.0

class CharacterConfig(BaseModel):
    name: str = "AI"
    persona: str = "あなたはAIアシスタントです。"
    personality_traits: list[str] = Field(default_factory=list)
    emotions: dict[str, EmotionStyle] = Field(default_factory=dict)


# ── Root ──────────────────────────────────────────────────────────────────────

class Config(BaseModel):
    character: CharacterConfig = Field(default_factory=CharacterConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    stt: STTConfig = Field(default_factory=STTConfig)


def _deep_merge(base: dict, override: dict) -> dict:
    """override の内容を base に再帰的にマージする"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(*paths: str | Path) -> Config:
    """
    複数のYAMLファイルを順番にマージして Config を返す。
    後から渡したファイルの値が優先される。

    例:
        config = load_config("config/default.yaml", "config/characters/kizuna.yaml")
    """
    merged: dict[str, Any] = {}
    for path in paths:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        merged = _deep_merge(merged, data)

    return Config(**merged)
