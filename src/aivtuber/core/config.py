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


# ── SmallTalk ─────────────────────────────────────────────────────────────────

class SmallTalkConfig(BaseModel):
    enabled: bool = True
    silence_timeout_sec: float = 30.0   # 無入力でトリガーする秒数
    trigger_probability: float = 0.7    # 実際に発話する確率（0.0〜1.0）
    min_interval_sec: float = 60.0      # 連続発話を防ぐ最小インターバル（秒）
    topics: list[str] = Field(default_factory=lambda: [
        "最近流行ってるゲーム",
        "アニメや漫画の話題",
        "今日の天気や季節のこと",
        "おすすめの食べ物・料理",
        "日常のちょっとした出来事",
    ])


# ── YouTube ───────────────────────────────────────────────────────────────────

class YouTubeConfig(BaseModel):
    api_key: str = Field(default_factory=lambda: os.environ.get("YOUTUBE_API_KEY", ""))
    video_id: str = ""
    polling_interval_sec: float = 10.0   # APIが返す interval がない場合のフォールバック（秒）
    max_comments_per_poll: int = 20       # 1ポーリングで取得するコメントの上限


# ── Avatar ────────────────────────────────────────────────────────────────────

class VTubeStudioConfig(BaseModel):
    port: int = 8001
    token_path: str = "./vts_token.txt"
    plugin_name: str = "AIVTuber"
    developer: str = "AIVTuber"
    hotkeys: dict[str, str] = Field(default_factory=lambda: {
        "neutral":  "Neutral",
        "happy":    "Happy",
        "sad":      "Sad",
        "excited":  "Excited",
        "thinking": "Thinking",
        "angry":    "Angry",
    })
    mouth_param: str = "MouthOpen"

class AvatarConfig(BaseModel):
    type: str = "none"       # none | browser | vtube_studio | vmc
    host: str = "localhost"
    port: int = 8765
    image_dir: str = ""      # 空 → CSS/SVG プレースホルダー使用
    vtube_studio: VTubeStudioConfig = Field(default_factory=VTubeStudioConfig)


# ── Root ──────────────────────────────────────────────────────────────────────

class Config(BaseModel):
    character: CharacterConfig = Field(default_factory=CharacterConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    small_talk: SmallTalkConfig = Field(default_factory=SmallTalkConfig)
    youtube: YouTubeConfig = Field(default_factory=YouTubeConfig)
    avatar: AvatarConfig = Field(default_factory=AvatarConfig)


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
