"""
faster-whisper を使った音声認識。

インストール: pip install faster-whisper sounddevice
"""
from __future__ import annotations

import io
import queue
import threading
from typing import Iterator

import numpy as np

from ..core.config import STTConfig


class WhisperSTT:
    """
    マイクからリアルタイムで音声を取得し、テキストに変換する。

    使い方:
        stt = WhisperSTT(config.stt)
        stt.load()

        for text in stt.listen():
            print("認識:", text)
    """

    def __init__(self, config: STTConfig):
        self._cfg = config
        self._model = None

    def load(self) -> None:
        """モデルをロード（初回は時間がかかる）"""
        from faster_whisper import WhisperModel
        print(f"[STT] モデルをロード中: {self._cfg.model_size} ({self._cfg.device})")
        self._model = WhisperModel(
            self._cfg.model_size,
            device=self._cfg.device,
            compute_type="int8" if self._cfg.device == "cpu" else "float16",
        )
        print("[STT] ロード完了")

    def transcribe_file(self, audio_path: str) -> str:
        """音声ファイルを文字起こし（テスト・開発用）"""
        assert self._model, "load() を先に呼んでください"
        segments, _ = self._model.transcribe(
            audio_path,
            language=self._cfg.language,
            beam_size=5,
        )
        return "".join(s.text for s in segments).strip()

    def transcribe_bytes(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        """WAVバイト列を文字起こし"""
        assert self._model, "load() を先に呼んでください"
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self._model.transcribe(
            audio_array,
            language=self._cfg.language,
            beam_size=5,
        )
        return "".join(s.text for s in segments).strip()

    def listen(self) -> Iterator[str]:
        """
        マイクから音声を取得し、発話単位でテキストを yield する。
        VAD（音声区間検出）で発話の開始・終了を判定する。

        Ctrl+C で停止。
        """
        import sounddevice as sd

        assert self._model, "load() を先に呼んでください"

        SAMPLE_RATE = 16000
        BLOCK_SIZE  = 1024   # ~64ms per block
        SILENCE_THRESHOLD = 0.01
        silence_ms = self._cfg.vad.silence_threshold_ms if self._cfg.vad.enabled else 9999
        silence_blocks = int(silence_ms / (BLOCK_SIZE / SAMPLE_RATE * 1000))

        audio_buffer: list[np.ndarray] = []
        silent_blocks = 0
        recording = False

        q: queue.Queue[np.ndarray] = queue.Queue()

        def callback(indata: np.ndarray, frames: int, time, status):
            q.put(indata.copy())

        print("[STT] 聞いています... (Ctrl+C で停止)")

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=BLOCK_SIZE,
            callback=callback,
        ):
            while True:
                block = q.get()
                amplitude = np.abs(block).mean()
                is_speech = amplitude > SILENCE_THRESHOLD

                if is_speech:
                    if not recording:
                        recording = True
                        print("[STT] 発話開始")
                    audio_buffer.append(block)
                    silent_blocks = 0
                elif recording:
                    audio_buffer.append(block)
                    silent_blocks += 1
                    if silent_blocks >= silence_blocks:
                        # 発話終了 → 文字起こし
                        print("[STT] 発話終了、認識中...")
                        audio_array = np.concatenate(audio_buffer, axis=0).flatten()
                        segments, _ = self._model.transcribe(
                            audio_array,
                            language=self._cfg.language,
                            beam_size=5,
                        )
                        text = "".join(s.text for s in segments).strip()
                        audio_buffer.clear()
                        silent_blocks = 0
                        recording = False
                        if text:
                            yield text
