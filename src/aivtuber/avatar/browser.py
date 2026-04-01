"""
ブラウザベースのアバターコントローラ。

WebSocket サーバーと HTTP サーバーを起動し、ブラウザでアバターを表示する。
起動時に表示される URL をブラウザで開くだけで使える。
OBS の Browser Source にも同じ URL を設定できる。
"""
from __future__ import annotations

import asyncio
import functools
import http.server
import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import websockets
from websockets.server import WebSocketServerProtocol

from .base import AvatarController

if TYPE_CHECKING:
    from ..core.config import AvatarConfig

# static/ ディレクトリの絶対パス（このファイルから3階層上）
_STATIC_DIR = Path(__file__).parent.parent.parent.parent / "static"


class BrowserAvatarController(AvatarController):
    """
    使い方:
        controller = BrowserAvatarController(config.avatar)
        await controller.start()   # WebSocket + HTTP サーバー起動
        await controller.set_emotion("happy")
        await controller.set_mouth_open(0.8)
        await controller.stop()
    """

    def __init__(self, config: AvatarConfig) -> None:
        self._config = config
        self._clients: set[WebSocketServerProtocol] = set()
        self._server = None
        self._http_server: http.server.HTTPServer | None = None
        self._http_thread: threading.Thread | None = None

    async def start(self) -> None:
        # HTTP サーバー（static/ を配信）
        http_port = self._config.port + 1  # WebSocket の次のポート（例: 8766）
        handler = functools.partial(
            http.server.SimpleHTTPRequestHandler,
            directory=str(_STATIC_DIR),
        )
        self._http_server = http.server.HTTPServer(("localhost", http_port), handler)
        self._http_thread = threading.Thread(
            target=self._http_server.serve_forever, daemon=True
        )
        self._http_thread.start()

        # WebSocket サーバー
        self._server = await websockets.serve(
            self._handler, self._config.host, self._config.port
        )
        print(f"[Avatar] アバターURL: http://localhost:{http_port}/avatar.html")

    async def stop(self) -> None:
        if self._http_server:
            self._http_server.shutdown()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def set_emotion(self, emotion_name: str) -> None:
        await self._broadcast({"type": "emotion", "value": emotion_name})

    async def set_mouth_open(self, value: float) -> None:
        await self._broadcast({"type": "mouth", "value": round(value, 2)})

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _handler(self, ws: WebSocketServerProtocol) -> None:
        self._clients.add(ws)
        try:
            await ws.wait_closed()
        finally:
            self._clients.discard(ws)

    async def _broadcast(self, msg: dict) -> None:
        if not self._clients:
            return
        payload = json.dumps(msg)
        await asyncio.gather(
            *[c.send(payload) for c in self._clients],
            return_exceptions=True,
        )
