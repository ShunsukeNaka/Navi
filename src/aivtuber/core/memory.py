"""会話メモリの管理"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["user", "assistant"]


@dataclass
class Turn:
    role: Role
    content: str
    emotion: str = "neutral"  # assistantターンのみ有効


class ConversationMemory:
    """
    短期記憶：直近 N ターンの会話を保持する。
    Claude Messages API の形式（role/content の交互リスト）に変換できる。
    """

    def __init__(self, max_turns: int = 10):
        self.max_turns = max_turns
        self._turns: deque[Turn] = deque()

    def add_user(self, content: str) -> None:
        self._turns.append(Turn(role="user", content=content))
        self._trim()

    def add_assistant(self, content: str, emotion: str = "neutral") -> None:
        self._turns.append(Turn(role="assistant", content=content, emotion=emotion))
        self._trim()

    def _trim(self) -> None:
        # max_turns は「ユーザー + アシスタント」のペア数なので2倍
        max_messages = self.max_turns * 2
        while len(self._turns) > max_messages:
            self._turns.popleft()

    def to_messages(self) -> list[dict]:
        """Claude Messages API 用のリストに変換"""
        return [{"role": t.role, "content": t.content} for t in self._turns]

    def clear(self) -> None:
        self._turns.clear()

    def __len__(self) -> int:
        return len(self._turns)

    def last_emotion(self) -> str:
        """直近のアシスタントターンの感情を返す"""
        for turn in reversed(self._turns):
            if turn.role == "assistant":
                return turn.emotion
        return "neutral"
