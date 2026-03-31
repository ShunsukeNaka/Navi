"""
感情状態の検出と管理。

LLMの応答テキストから感情を推定し、
TTS（音声合成）やアバターへ渡すパラメータに変換する。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .config import CharacterConfig, EmotionStyle


# 感情を判定するキーワードルール（設定より軽量な補助手段）
_EMOTION_KEYWORDS: dict[str, list[str]] = {
    "happy":   ["嬉しい", "よかった", "やった", "ありがとう", "最高", "楽しい", "わーい", "！"],
    "excited": ["すごい", "信じられない", "マジ", "えー！", "わあ", "ほんとに？", "びっくり"],
    "sad":     ["悲しい", "つらい", "残念", "ごめん", "申し訳", "しょんぼり"],
    "angry":   ["むかつく", "ひどい", "なんで", "いやだ", "ちょっと待って"],
    "thinking":["うーん", "えーと", "そうだなあ", "難しい", "考えて", "んー"],
}


@dataclass
class EmotionResult:
    name: str                  # 感情名（config.character.emotions のキー）
    style: EmotionStyle        # 対応するスタイル設定
    confidence: float = 1.0    # 0.0–1.0


class EmotionDetector:
    """
    テキストから感情を検出する。

    優先順位:
    1. LLM が明示的に感情タグを返した場合（<emotion>happy</emotion>）
    2. キーワードマッチ
    3. デフォルト（neutral）
    """

    def __init__(self, character_config: CharacterConfig):
        self._emotions = character_config.emotions
        self._ensure_neutral()

    def _ensure_neutral(self) -> None:
        if "neutral" not in self._emotions:
            self._emotions["neutral"] = EmotionStyle(
                description="普通の状態",
                speech_style="普通に話す",
                tts_speed=1.0,
                tts_pitch=0.0,
            )

    def detect(self, text: str) -> EmotionResult:
        # thinking ブロックを除去してから判定
        text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.IGNORECASE | re.DOTALL)

        # 1. 明示的な感情タグ <emotion>happy</emotion>
        tag_match = re.search(r"<emotion>(.*?)</emotion>", text, re.IGNORECASE)
        if tag_match:
            name = tag_match.group(1).strip().lower()
            if name in self._emotions:
                return EmotionResult(name=name, style=self._emotions[name], confidence=1.0)

        # 1b. 短縮形タグ <happy>, <sad>text</sad> など
        for emotion_name in self._emotions:
            if re.search(rf"<{re.escape(emotion_name)}\b", text, re.IGNORECASE):
                return EmotionResult(name=emotion_name, style=self._emotions[emotion_name], confidence=1.0)

        # 2. キーワードマッチ
        scores: dict[str, int] = {}
        for emotion, keywords in _EMOTION_KEYWORDS.items():
            if emotion not in self._emotions:
                continue
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[emotion] = score

        if scores:
            best = max(scores, key=lambda k: scores[k])
            confidence = min(scores[best] / 3.0, 1.0)
            return EmotionResult(
                name=best,
                style=self._emotions[best],
                confidence=confidence,
            )

        # 3. デフォルト
        return EmotionResult(
            name="neutral",
            style=self._emotions["neutral"],
            confidence=0.5,
        )

    def strip_emotion_tags(self, text: str) -> str:
        """LLMが出力した感情タグ・thinkingブロックをテキストから除去する"""
        # <thinking>...</thinking> ブロックを除去（qwen2.5等のCoTモデル対策）
        text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.IGNORECASE | re.DOTALL)
        # <emotion>name</emotion> タグを除去
        text = re.sub(r"<emotion>.*?</emotion>", "", text, flags=re.IGNORECASE)
        # 短縮形タグ <happy>, </happy> 等を除去
        emotion_names = "|".join(re.escape(name) for name in self._emotions)
        text = re.sub(rf"</?(?:{emotion_names})\b[^>]*>", "", text, flags=re.IGNORECASE)
        return text.strip()

    def get_tts_params(self, emotion: EmotionResult) -> dict:
        """VOICEVOX に渡すprosodyパラメータを返す"""
        return {
            "speed_scale": emotion.style.tts_speed,
            "pitch_scale": emotion.style.tts_pitch,
        }
