"""
マイク入力 → STT → AI応答 → VOICEVOX音声出力

フルパイプライン。

使い方:
    python scripts/voice.py
    python scripts/voice.py --config config/character.yaml
"""
from __future__ import annotations

import asyncio
import random
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from aivtuber.utils.alsa import suppress_alsa_errors
suppress_alsa_errors()

from aivtuber.avatar import create_avatar_controller
from aivtuber.avatar.player import speak as avatar_speak
from aivtuber.core.brain import Brain
from aivtuber.core.config import SmallTalkConfig, load_config
from aivtuber.stt.faster_whisper import WhisperSTT
from aivtuber.tts.voicevox import VoicevoxClient


class VoiceSessionState:
    """voice.py のセッション全体の状態管理"""
    def __init__(self):
        self.is_ai_speaking = threading.Event()      # AI発話中フラグ
        self.user_spoke = threading.Event()           # ユーザー割り込みフラグ
        self.last_interaction_time: float = time.monotonic()
        self.last_small_talk_time: float = 0.0
        self.small_talk_task: asyncio.Task | None = None


async def speak_stream(
    brain: Brain,
    tts: VoicevoxClient | None,
    user_input: str,
    state: VoiceSessionState,
    avatar,
) -> None:
    char_name = brain._cfg.character.name
    print(f"{char_name}: ", end="", flush=True)

    state.is_ai_speaking.set()
    tts_tasks: list[asyncio.Task] = []
    try:
        async for chunk in brain.respond_stream(user_input):
            if chunk.is_final:
                print(f"  [{chunk.emotion.name}]")
                break
            print(chunk.text, end="", flush=True)
            if tts:
                tts_params = brain._emotion_detector.get_tts_params(chunk.emotion)
                task = asyncio.create_task(avatar_speak(tts, chunk.text, tts_params, avatar, chunk.emotion.name))
                tts_tasks.append(task)
        for task in tts_tasks:
            await task
    finally:
        state.is_ai_speaking.clear()
    print()


async def _speak_small_talk(
    brain: Brain,
    tts: VoicevoxClient | None,
    state: VoiceSessionState,
    avatar,
) -> None:
    """自発発話を生成・再生する。ユーザー割り込みで即中断。"""
    char_name = brain._cfg.character.name
    print(f"\n{char_name}: ", end="", flush=True)

    tts_tasks: list[asyncio.Task] = []
    try:
        async for chunk in brain.generate_small_talk():
            if state.user_spoke.is_set():
                raise asyncio.CancelledError()
            if chunk.is_final:
                print(f"  [{chunk.emotion.name}]")
                break
            print(chunk.text, end="", flush=True)
            if tts:
                tts_params = brain._emotion_detector.get_tts_params(chunk.emotion)
                task = asyncio.create_task(avatar_speak(tts, chunk.text, tts_params, avatar, chunk.emotion.name))
                tts_tasks.append(task)
        for task in tts_tasks:
            await task
    except asyncio.CancelledError:
        for task in tts_tasks:
            task.cancel()
        print("\n[自発発話を中断しました]")
        raise


async def silence_monitor(
    brain: Brain,
    tts: VoicevoxClient | None,
    state: VoiceSessionState,
    cfg: SmallTalkConfig,
    avatar,
) -> None:
    """5秒ごとに沈黙時間をチェックし、閾値を超えたら自発発話する"""
    while True:
        await asyncio.sleep(5.0)

        if not cfg.enabled or state.is_ai_speaking.is_set():
            continue

        now = time.monotonic()
        if (
            now - state.last_interaction_time >= cfg.silence_timeout_sec
            and now - state.last_small_talk_time >= cfg.min_interval_sec
            and random.random() < cfg.trigger_probability
        ):
            state.is_ai_speaking.set()
            state.user_spoke.clear()
            state.small_talk_task = asyncio.create_task(
                _speak_small_talk(brain, tts, state, avatar)
            )
            try:
                await state.small_talk_task
                state.last_small_talk_time = time.monotonic()
                state.last_interaction_time = time.monotonic()
            except asyncio.CancelledError:
                pass
            finally:
                state.is_ai_speaking.clear()
                state.small_talk_task = None


async def main(config_path: str) -> None:
    config = load_config(config_path)
    brain = Brain(config)
    st_cfg = config.small_talk

    tts = VoicevoxClient(config.tts)
    if not await tts.is_available():
        print("[警告] VOICEVOXが起動していません。テキストのみで動作します。")
        tts = None

    stt = WhisperSTT(config.stt)
    stt.load()

    avatar = create_avatar_controller(config.avatar)
    await avatar.start()

    state = VoiceSessionState()
    loop = asyncio.get_event_loop()

    def stt_loop():
        for text in stt.listen():
            print(f"\nあなた: {text}")
            state.last_interaction_time = time.monotonic()
            state.user_spoke.set()

            # 自発発話中なら中断させる
            if state.is_ai_speaking.is_set() and state.small_talk_task:
                loop.call_soon_threadsafe(state.small_talk_task.cancel)
                # 中断完了を待つ（最大1秒）
                for _ in range(20):
                    if not state.is_ai_speaking.is_set():
                        break
                    time.sleep(0.05)

            state.user_spoke.clear()
            asyncio.run_coroutine_threadsafe(
                speak_stream(brain, tts, text, state, avatar), loop
            ).result()
            state.last_interaction_time = time.monotonic()

    if st_cfg.enabled:
        print(f"[雑談モード有効: {st_cfg.silence_timeout_sec:.0f}秒の沈黙で自発発話]\n")

    t = threading.Thread(target=stt_loop, daemon=True)
    t.start()

    monitor_task = asyncio.create_task(silence_monitor(brain, tts, state, st_cfg, avatar))

    try:
        await asyncio.Event().wait()  # Ctrl+C まで待機
    except KeyboardInterrupt:
        print("\n終了します。")
    finally:
        monitor_task.cancel()
        await avatar.stop()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/character.yaml")
    args = parser.parse_args()
    asyncio.run(main(args.config))
