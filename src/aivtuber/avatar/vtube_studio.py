"""
VTube Studio アバターコントローラ。

pyvts ライブラリ経由で VTube Studio WebSocket API に接続し、
感情ホットキーのトリガーと口パクパラメータ（MouthOpen）を制御する。

接続手順:
  1. VTube Studio を起動し、API を有効化（設定 → Plugins → Enable API）
  2. config/character.yaml の avatar.type を "vtube_studio" に設定
  3. 起動後、VTube Studio 側で認証ポップアップを許可
  4. 2回目以降はトークンファイル（vts_token.txt）で自動認証

ホットキー名はモデル依存なので character.yaml の avatar.vtube_studio.hotkeys で設定する。
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .base import AvatarController

if TYPE_CHECKING:
    from ..core.config import AvatarConfig


class VTubeStudioController(AvatarController):

    def __init__(self, config: AvatarConfig) -> None:
        self._config = config
        self._vts_cfg = config.vtube_studio
        self._vts = None
        self._connected = False
        self._lock = None  # asyncio.Lock は event loop 内で生成する

    async def start(self) -> None:
        try:
            import pyvts
        except ImportError:
            print("[VTS] pyvts がインストールされていません: pip install pyvts")
            return

        self._vts = pyvts.vts(
            plugin_info={
                "plugin_name": self._vts_cfg.plugin_name,
                "developer": self._vts_cfg.developer,
                "authentication_token_path": self._vts_cfg.token_path,
            },
            vts_api_info={
                "version": "1.0",
                "name": "VTubeStudioPublicAPI",
                "host": self._config.host,
                "port": self._vts_cfg.port,
            },
        )

        self._lock = asyncio.Lock()

        try:
            await self._vts.connect()
        except Exception as e:
            print(f"[VTS] 接続失敗（VTube Studio が起動していない可能性）: {e}")
            return

        try:
            await self._vts.request_authenticate_token()
            await self._vts.request_authenticate()
            self._connected = True
            print("[VTS] VTube Studio に接続しました")
        except Exception as e:
            print(f"[VTS] 認証失敗: {e}")
            await self._vts.close()

    async def stop(self) -> None:
        if self._vts and self._connected:
            await self._vts.close()
            self._connected = False

    async def set_emotion(self, emotion_name: str) -> None:
        if not self._connected or self._lock is None:
            return
        hotkey = self._vts_cfg.hotkeys.get(emotion_name)
        if not hotkey:
            return
        async with self._lock:
            try:
                await self._vts.request(
                    self._vts.vts_request.requestTriggerHotKey(hotkeyID=hotkey)
                )
            except Exception as e:
                print(f"[VTS] ホットキー失敗 ({hotkey}): {e}")
                self._connected = False

    async def set_mouth_open(self, value: float) -> None:
        if not self._connected or self._lock is None:
            return
        value = max(0.0, min(1.0, value))
        async with self._lock:
            try:
                await self._vts.request(
                    self._vts.vts_request.requestSetParameterValue(
                        parameter=self._vts_cfg.mouth_param,
                        value=value,
                    )
                )
            except Exception as e:
                print(f"[VTS] パラメータ設定失敗: {e}")
                self._connected = False
