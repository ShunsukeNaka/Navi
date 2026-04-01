"""
アバターコントローラの基底クラス。

実装を差し替えるための抽象インタフェース。
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class AvatarController(ABC):
    """アバター制御の共通インタフェース"""

    @abstractmethod
    async def start(self) -> None:
        """サーバー起動・接続などの初期化処理"""

    @abstractmethod
    async def stop(self) -> None:
        """後片付け処理"""

    @abstractmethod
    async def set_emotion(self, emotion_name: str) -> None:
        """感情を切り替える（例: "happy", "sad", "neutral"）"""

    @abstractmethod
    async def set_mouth_open(self, value: float) -> None:
        """口の開き具合を設定する（0.0=閉じる, 1.0=最大に開く）"""


class NullAvatarController(AvatarController):
    """type="none" 用。何もしない。"""

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def set_emotion(self, emotion_name: str) -> None:
        pass

    async def set_mouth_open(self, value: float) -> None:
        pass
