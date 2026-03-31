"""
AIVTuber の「脳」。

キャラクター人格・記憶・感情を統合して、
ユーザーの発言に対する応答を生成する。
LLMプロバイダーは config.llm.provider で切り替え可能。
"""
from __future__ import annotations

import re
from typing import AsyncIterator

from .config import Config
from .emotion import EmotionDetector, EmotionResult
from .memory import ConversationMemory


class Brain:
    """
    使い方:
        brain = Brain(config)
        response = await brain.respond("こんにちは！")
        print(response.text, response.emotion.name)

        # ストリーミング（文単位）
        async for chunk in brain.respond_stream("今日は何してたの？"):
            if not chunk.is_final:
                print(chunk.text)

        # 自発発話（雑談）
        async for chunk in brain.generate_small_talk():
            if not chunk.is_final:
                print(chunk.text)
    """

    def __init__(self, config: Config):
        from ..llm.factory import create_llm_client
        self._cfg = config
        self._llm = create_llm_client(config.llm)
        self._memory = ConversationMemory(max_turns=config.llm.memory.short_term_turns)
        self._emotion_detector = EmotionDetector(config.character)
        self._system_prompt = self._build_system_prompt()

    # ── Public API ────────────────────────────────────────────────────────────

    async def respond(self, user_input: str) -> "BrainResponse":
        """全文生成して返す"""
        self._memory.add_user(user_input)
        raw_text = await self._llm.complete(
            system=self._system_prompt,
            messages=self._memory.to_messages(),
            max_tokens=self._cfg.llm.max_tokens,
            temperature=self._cfg.llm.temperature,
        )
        emotion = self._emotion_detector.detect(raw_text)
        clean_text = self._emotion_detector.strip_emotion_tags(raw_text)
        self._memory.add_assistant(clean_text, emotion.name)
        return BrainResponse(text=clean_text, emotion=emotion, raw=raw_text)

    async def respond_stream(self, user_input: str) -> AsyncIterator["StreamChunk"]:
        """
        ストリーミング応答。文（。！？）単位で yield する。
        TTS に早期に渡せるため体感レイテンシが下がる。
        """
        self._memory.add_user(user_input)
        full_text = ""
        final_emotion = "neutral"
        async for chunk in self._stream_chunks(self._system_prompt, self._memory.to_messages()):
            if not chunk.is_final:
                full_text += chunk.text
            else:
                final_emotion = chunk.emotion.name
            yield chunk
        self._memory.add_assistant(full_text, final_emotion)

    async def generate_small_talk(self) -> AsyncIterator["StreamChunk"]:
        """
        自発発話（雑談）を生成する。
        ユーザー入力なしで呼び出し、特別なシステムプロンプトを使う。
        メモリには追加しない（APIのrole交互制約を回避するため）。
        """
        messages = self._memory.to_messages() or [{"role": "user", "content": "(配信開始)"}]
        async for chunk in self._stream_chunks(self._build_small_talk_prompt(), messages):
            yield chunk

    def reset_memory(self) -> None:
        self._memory.clear()

    def update_persona(self, new_persona: str) -> None:
        """ランタイムでペルソナを変更（チューニング用）"""
        self._cfg.character.persona = new_persona
        self._system_prompt = self._build_system_prompt()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        char = self._cfg.character
        llm = self._cfg.llm

        traits_text = ""
        if char.personality_traits:
            traits_text = "性格の特徴: " + "、".join(char.personality_traits) + "\n"

        emotion_instruction = ""
        if char.emotions:
            names = "、".join(char.emotions.keys())
            emotion_instruction = (
                f"\n感情を表現したいときは <emotion>感情名</emotion> タグを文中に埋め込んでください。"
                f"使える感情: {names}"
            )

        return (
            f"あなたは今ライブ配信中のVTuberです。返答は必ず日本語で話してください。\n\n"
            f"## キャラクター設定\n"
            f"名前: {char.name}\n"
            f"{traits_text}"
            f"{char.persona}"
            f"{emotion_instruction}"
            f"\n返答は必ず{llm.max_sentences}文以内にしてください。"
        )

    def _build_small_talk_prompt(self) -> str:
        topics = "、".join(self._cfg.small_talk.topics)
        return (
            self._system_prompt
            + f"\n\n## 自発発話モード\n"
              f"しばらく沈黙が続きました。視聴者に向けて自分から話しかけてください。\n"
              f"話題の候補: {topics}\n"
              f"ユーザーの返答を待たずに、自然に話しかけてください。"
        )

    async def _stream_chunks(
        self, system: str, messages: list[dict]
    ) -> AsyncIterator["StreamChunk"]:
        """
        thinking除去 + 文単位分割の共通ストリーミングロジック。
        respond_stream() と generate_small_talk() の両方から使う。
        """
        buffer = ""
        raw = ""
        full_text = ""
        processed = 0
        in_thinking = False

        async for token in self._llm.stream(
            system=system,
            messages=messages,
            max_tokens=self._cfg.llm.max_tokens,
            temperature=self._cfg.llm.temperature,
        ):
            raw += token
            full_text += token

            while processed < len(raw):
                if in_thinking:
                    end = raw.lower().find("</thinking>", processed)
                    if end == -1:
                        break
                    processed = end + len("</thinking>")
                    in_thinking = False
                else:
                    start = raw.lower().find("<thinking>", processed)
                    if start == -1:
                        buffer += raw[processed:]
                        processed = len(raw)
                    else:
                        buffer += raw[processed:start]
                        processed = start + len("<thinking>")
                        in_thinking = True

            if in_thinking:
                continue

            sentences, buffer = _split_sentences(buffer)
            for sentence in sentences:
                clean = self._emotion_detector.strip_emotion_tags(sentence).strip()
                if clean:
                    emotion = self._emotion_detector.detect(sentence)
                    yield StreamChunk(text=clean, emotion=emotion, is_final=False)

        # バッファ残りを flush
        if buffer.strip():
            clean = self._emotion_detector.strip_emotion_tags(buffer).strip()
            if clean:
                emotion = self._emotion_detector.detect(buffer)
                yield StreamChunk(text=clean, emotion=emotion, is_final=False)

        emotion = self._emotion_detector.detect(full_text)
        full_text_clean = self._emotion_detector.strip_emotion_tags(full_text)
        yield StreamChunk(text="", emotion=emotion, is_final=True)


# ── Data classes ──────────────────────────────────────────────────────────────

class BrainResponse:
    def __init__(self, text: str, emotion: EmotionResult, raw: str):
        self.text = text
        self.emotion = emotion
        self.raw = raw

    def __repr__(self) -> str:
        return f"BrainResponse(text={self.text!r}, emotion={self.emotion.name!r})"


class StreamChunk:
    def __init__(self, text: str, emotion: EmotionResult, is_final: bool):
        self.text = text
        self.emotion = emotion
        self.is_final = is_final


# ── Helpers ───────────────────────────────────────────────────────────────────

_SENTENCE_END = re.compile(r"(?<=[。！？!?])")

def _split_sentences(text: str) -> tuple[list[str], str]:
    parts = _SENTENCE_END.split(text)
    if len(parts) <= 1:
        return [], text
    return parts[:-1], parts[-1]
