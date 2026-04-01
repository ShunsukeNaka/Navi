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
import random
import sys
import time
from pathlib import Path

# プロジェクトルートを sys.path に追加
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from aivtuber.utils.alsa import suppress_alsa_errors
suppress_alsa_errors()

from aivtuber.avatar import create_avatar_controller
from aivtuber.avatar.player import speak as avatar_speak
from aivtuber.core.brain import Brain
from aivtuber.core.config import load_config
from aivtuber.tts.voicevox import VoicevoxClient


async def _async_input(prompt: str) -> str:
    """input() を executor で非同期化する"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))


async def _run_small_talk(brain: Brain, tts: VoicevoxClient | None, avatar) -> None:
    """自発発話を生成して再生する"""
    tts_tasks: list[asyncio.Task] = []
    async for chunk in brain.generate_small_talk():
        if chunk.is_final:
            print(f"  [{chunk.emotion.name}]\n")
            break
        print(chunk.text, end="", flush=True)
        if tts:
            tts_params = brain._emotion_detector.get_tts_params(chunk.emotion)
            task = asyncio.create_task(avatar_speak(tts, chunk.text, tts_params, avatar, chunk.emotion.name))
            tts_tasks.append(task)
    for task in tts_tasks:
        await task


async def main(config_path: str, use_tts: bool) -> None:
    config = load_config(config_path)
    brain = Brain(config)
    st_cfg = config.small_talk

    tts = None
    if use_tts:
        tts = VoicevoxClient(config.tts)
        if not await tts.is_available():
            print("[警告] VOICEVOXが起動していません。テキストのみで動作します。")
            tts = None

    avatar = create_avatar_controller(config.avatar)
    await avatar.start()

    char_name = config.character.name
    print(f"=== {char_name} と話す === ('quit' で終了, 'reset' で記憶リセット)\n")
    if st_cfg.enabled:
        print(f"[雑談モード有効: {st_cfg.silence_timeout_sec:.0f}秒無入力で自発発話]\n")

    last_small_talk_time = 0.0

    try:
        while True:
            try:
                user_input = await asyncio.wait_for(
                    _async_input("あなた: "),
                    timeout=st_cfg.silence_timeout_sec if st_cfg.enabled else None,
                )
            except asyncio.TimeoutError:
                print("\r" + " " * 20 + "\r", end="", flush=True)
                now = time.monotonic()
                if (
                    (now - last_small_talk_time) >= st_cfg.min_interval_sec
                    and random.random() < st_cfg.trigger_probability
                ):
                    print(f"{char_name}: ", end="", flush=True)
                    await _run_small_talk(brain, tts, avatar)
                    last_small_talk_time = time.monotonic()
                continue
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

            tts_tasks: list[asyncio.Task] = []

            async for chunk in brain.respond_stream(user_input):
                if chunk.is_final:
                    print(f"  [{chunk.emotion.name}]\n")
                    break
                print(chunk.text, end="", flush=True)

                if tts:
                    tts_params = brain._emotion_detector.get_tts_params(chunk.emotion)
                    task = asyncio.create_task(avatar_speak(tts, chunk.text, tts_params, avatar, chunk.emotion.name))
                    tts_tasks.append(task)

            for task in tts_tasks:
                await task
    finally:
        await avatar.stop()


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
