"""
VMC (VirtualMotionCapture) プロトコル アバターコントローラ（スタブ）。

TODO: python-osc ライブラリを使って実装する。
  pip install python-osc
  https://github.com/attwad/python-osc

VMC プロトコルは OSC (Open Sound Control) ベース。
VSeeFace, 3tene, Luppet など多くの 3D アバターアプリが対応している。

OSC アドレス例:
  /VMC/Ext/Blend/Val  → ブレンドシェイプ（表情・口パク）の送信
  引数: (string name, float value)
    "A" / "I" / "U" / "E" / "O"  → 母音の口形
    "Joy" / "Sorrow" / "Angry" / "Fun"  → 感情表現
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import AvatarController

if TYPE_CHECKING:
    from ..core.config import AvatarConfig


class VMCController(AvatarController):

    def __init__(self, config: AvatarConfig) -> None:
        self._config = config

    async def start(self) -> None:
        # TODO: python-osc で UDP ソケットを開く
        raise NotImplementedError("VMC 連携は未実装です。vmc.py を参照してください。")

    async def stop(self) -> None:
        pass

    async def set_emotion(self, emotion_name: str) -> None:
        # TODO: /VMC/Ext/Blend/Val で感情ブレンドシェイプを送信
        pass

    async def set_mouth_open(self, value: float) -> None:
        # TODO: /VMC/Ext/Blend/Val で "A" ブレンドシェイプを送信
        pass
