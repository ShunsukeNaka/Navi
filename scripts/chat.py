"""
テキスト入力 → AI応答 → VOICEVOX音声出力

一番シンプルなエントリーポイント。
マイク・アバターなし。動作確認とチューニングに使う。

使い方:
    python scripts/chat.py
    python scripts/chat.py --config config/character.yaml
    python scripts/chat.py --no-tts  # テキストのみ（VOICEVOXなし）
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# プロジェクトルートを sys.path に追加
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from aivtuber.core.brain import Brain
from aivtuber.core.config import load_config
from aivtuber.tts.voicevox import VoicevoxClient


async def play_wav(wav_bytes: bytes) -> None:
    """WAVバイト列を再生する"""
    import io
    import sounddevice as sd
    import soundfile as sf
    data, samplerate = sf.read(io.BytesIO(wav_bytes))
    sd.play(data, samplerate)
    sd.wait()


async def main(config_path: str, use_tts: bool) -> None:
    config = load_config(config_path)
    brain = Brain(config)

    tts = None
    if use_tts:
        tts = VoicevoxClient(config.tts)
        if not await tts.is_available():
            print("[警告] VOICEVOXが起動していません。テキストのみで動作します。")
            tts = None

    char_name = config.character.name
    print(f"=== {char_name} と話す === ('quit' で終了, 'reset' で記憶リセット)\n")

    while True:
        try:
            user_input = input("あなた: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n終了します。")
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            break
        if user_input.lower() == "reset":
            brain.reset_memory()
            print("[記憶をリセットしました]\n")
            continue

        print(f"{char_name}: ", end="", flush=True)

        # ストリーミングで応答を受け取る
        full_text = ""
        current_emotion = "neutral"
        tts_tasks: list[asyncio.Task] = []

        async for chunk in brain.respond_stream(user_input):
            if chunk.is_final:
                current_emotion = chunk.emotion.name
                break
            print(chunk.text, end="", flush=True)
            full_text += chunk.text

            # TTSは文単位で非同期に開始
            if tts:
                tts_params = brain._emotion_detector.get_tts_params(chunk.emotion)
                task = asyncio.create_task(
                    _speak(tts, chunk.text, tts_params)
                )
                tts_tasks.append(task)

        print(f"  [{current_emotion}]\n")

        # TTS タスクを順番に待つ（音声が重ならないように）
        for task in tts_tasks:
            await task


async def _speak(tts: VoicevoxClient, text: str, tts_params: dict) -> None:
    try:
        wav = await tts.synthesize(text, **tts_params)
        await play_wav(wav)
    except Exception as e:
        print(f"\n[TTS エラー: {e}]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="config/character.yaml",
        help="設定ファイルのパス",
    )
    parser.add_argument(
        "--no-tts",
        action="store_true",
        help="音声合成を無効にする",
    )
    args = parser.parse_args()

    asyncio.run(main(args.config, use_tts=not args.no_tts))
