"""
マイク入力 → STT → AI応答 → VOICEVOX音声出力

フルパイプライン。

使い方:
    python scripts/voice.py
    python scripts/voice.py --config config/character.yaml
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from aivtuber.core.brain import Brain
from aivtuber.core.config import load_config
from aivtuber.stt.faster_whisper import WhisperSTT
from aivtuber.tts.voicevox import VoicevoxClient


async def speak_stream(brain: Brain, tts: VoicevoxClient | None, user_input: str) -> None:
    char_name = brain._cfg.character.name
    print(f"{char_name}: ", end="", flush=True)

    tts_tasks: list[asyncio.Task] = []

    async for chunk in brain.respond_stream(user_input):
        if chunk.is_final:
            print(f"  [{chunk.emotion.name}]")
            break
        print(chunk.text, end="", flush=True)

        if tts:
            tts_params = brain._emotion_detector.get_tts_params(chunk.emotion)
            task = asyncio.create_task(_speak(tts, chunk.text, tts_params))
            tts_tasks.append(task)

    for task in tts_tasks:
        await task
    print()


async def _speak(tts: VoicevoxClient, text: str, tts_params: dict) -> None:
    import io
    import sounddevice as sd
    import soundfile as sf
    try:
        wav = await tts.synthesize(text, **tts_params)
        data, sr = sf.read(io.BytesIO(wav))
        sd.play(data, sr)
        sd.wait()
    except Exception as e:
        print(f"\n[TTS エラー: {e}]")


async def main(config_path: str) -> None:
    config = load_config(config_path)
    brain = Brain(config)

    tts = VoicevoxClient(config.tts)
    if not await tts.is_available():
        print("[警告] VOICEVOXが起動していません。テキストのみで動作します。")
        tts = None

    stt = WhisperSTT(config.stt)
    stt.load()

    # STTはブロッキングなのでスレッドで動かす
    loop = asyncio.get_event_loop()

    def stt_loop():
        for text in stt.listen():
            print(f"\nあなた: {text}")
            asyncio.run_coroutine_threadsafe(
                speak_stream(brain, tts, text), loop
            ).result()

    import threading
    t = threading.Thread(target=stt_loop, daemon=True)
    t.start()

    try:
        await asyncio.Event().wait()  # Ctrl+C まで待機
    except KeyboardInterrupt:
        print("\n終了します。")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/character.yaml")
    args = parser.parse_args()
    asyncio.run(main(args.config))
