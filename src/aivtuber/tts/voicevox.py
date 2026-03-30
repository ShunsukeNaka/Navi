"""
VOICEVOX クライアント。

VOICEVOXはローカルで動かすTTSエンジン。
HTTP API の2ステップ（audio_query → synthesis）を叩くだけ。
"""
from __future__ import annotations

import httpx

from ..core.config import TTSConfig


class VoicevoxClient:
    """
    使い方:
        client = VoicevoxClient(config.tts)
        wav_bytes = await client.synthesize("こんにちは！", speed_scale=1.1)
    """

    def __init__(self, config: TTSConfig):
        self._base_url = config.voicevox.base_url
        self._speaker_id = config.voicevox.speaker_id
        self._default_prosody = config.voicevox.default_prosody

    async def synthesize(
        self,
        text: str,
        speed_scale: float | None = None,
        pitch_scale: float | None = None,
        intonation_scale: float | None = None,
        volume_scale: float | None = None,
    ) -> bytes:
        """
        テキストを音声（WAVバイト列）に変換する。
        prosodyパラメータが None の場合は config のデフォルト値を使う。
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: audio_query を取得
            query_resp = await client.post(
                f"{self._base_url}/audio_query",
                params={"text": text, "speaker": self._speaker_id},
            )
            query_resp.raise_for_status()
            query = query_resp.json()

            # Step 2: prosody を上書き
            p = self._default_prosody
            query["speedScale"]       = speed_scale      if speed_scale      is not None else p.speed_scale
            query["pitchScale"]       = pitch_scale      if pitch_scale      is not None else p.pitch_scale
            query["intonationScale"]  = intonation_scale if intonation_scale is not None else p.intonation_scale
            query["volumeScale"]      = volume_scale     if volume_scale     is not None else p.volume_scale

            # Step 3: 合成
            synth_resp = await client.post(
                f"{self._base_url}/synthesis",
                params={"speaker": self._speaker_id},
                json=query,
                headers={"Content-Type": "application/json"},
            )
            synth_resp.raise_for_status()
            return synth_resp.content

    async def is_available(self) -> bool:
        """VOICEVOXサーバーが起動しているか確認"""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self._base_url}/version")
                return resp.status_code == 200
        except Exception:
            return False
