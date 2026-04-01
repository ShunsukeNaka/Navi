"""
YouTube Live コメント → AI応答 → VOICEVOX音声出力

YouTube Liveのライブチャットコメントを取得し、VTuberが応答する。
複数コメントが来た場合はランダムに1件選んで応答。
沈黙が続いた場合は自発発話（雑談機能）も動作する。

使い方:
    python scripts/youtube.py --video-id <VIDEO_ID>
    python scripts/youtube.py --video-id <VIDEO_ID> --no-tts
    python scripts/youtube.py --config config/character.yaml --video-id <VIDEO_ID>

事前準備:
    .env に YOUTUBE_API_KEY を設定すること
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from aivtuber.utils.alsa import suppress_alsa_errors
suppress_alsa_errors()

from aivtuber.avatar import create_avatar_controller
from aivtuber.avatar.player import speak as avatar_speak
from aivtuber.chat.youtube import ChatMessage, LiveStreamEndedError, QuotaExceededError, YouTubeChatReader
from aivtuber.core.brain import Brain
from aivtuber.core.config import SmallTalkConfig, load_config
from aivtuber.tts.voicevox import VoicevoxClient


async def speak_response(
    brain: Brain,
    tts: VoicevoxClient | None,
    comment: str,
    is_speaking: asyncio.Event,
    avatar,
) -> None:
    """コメントに対してストリーム応答しTTSで再生する"""
    char_name = brain._cfg.character.name
    print(f"\nコメント: 「{comment}」")
    print(f"{char_name}: ", end="", flush=True)

    is_speaking.set()
    tts_tasks: list[asyncio.Task] = []
    try:
        async for chunk in brain.respond_stream(comment):
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
        is_speaking.clear()
    print()


async def speak_superchat_response(
    brain: Brain,
    tts: VoicevoxClient | None,
    author: str,
    amount: str,
    comment: str,
    is_speaking: asyncio.Event,
    avatar,
) -> None:
    """スーパーチャットに対して興奮気味の感謝応答をTTSで再生する"""
    char_name = brain._cfg.character.name
    sc_label = f"スーパーチャット {amount} from {author}"
    print(f"\n[{sc_label}]" + (f" 「{comment}」" if comment else ""))
    print(f"{char_name}: ", end="", flush=True)

    is_speaking.set()
    tts_tasks: list[asyncio.Task] = []
    try:
        async for chunk in brain.respond_superchat_stream(author, amount, comment):
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
        is_speaking.clear()
    print()


async def _speak_small_talk(
    brain: Brain,
    tts: VoicevoxClient | None,
    avatar,
) -> None:
    """自発発話を生成・再生する"""
    char_name = brain._cfg.character.name
    print(f"\n{char_name}: ", end="", flush=True)

    tts_tasks: list[asyncio.Task] = []
    try:
        async for chunk in brain.generate_small_talk():
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
        raise


async def fill_comment_queue(
    reader: YouTubeChatReader,
    queue: asyncio.Queue,
) -> None:
    """YouTube コメントをキューに流し込む。配信終了で終わる。"""
    async for msg in reader.stream_comments():
        await queue.put(msg)
    print("\n[配信が終了しました]")


async def response_loop(
    brain: Brain,
    tts: VoicevoxClient | None,
    avatar,
    cfg: SmallTalkConfig,
    queue: asyncio.Queue,
    last_interaction: list[float],
) -> None:
    """
    コメントキューを順番に処理し、空のときは自発発話する。
    コメントはスキップせずキューに溜まる。
    """
    is_speaking = asyncio.Event()
    last_small_talk_time = 0.0

    while True:
        # キューにコメントがあれば優先処理
        try:
            msg = queue.get_nowait()
        except asyncio.QueueEmpty:
            msg = None

        if msg is not None:
            last_interaction[0] = time.monotonic()
            if msg.is_superchat:
                await speak_superchat_response(
                    brain, tts, msg.author, msg.amount, msg.text, is_speaking, avatar
                )
            else:
                await speak_response(brain, tts, msg.text, is_speaking, avatar)
            last_interaction[0] = time.monotonic()
        else:
            # キューが空 → 自発発話チェック
            now = time.monotonic()
            if (
                cfg.enabled
                and now - last_interaction[0] >= cfg.silence_timeout_sec
                and now - last_small_talk_time >= cfg.min_interval_sec
                and random.random() < cfg.trigger_probability
            ):
                is_speaking.set()
                try:
                    await _speak_small_talk(brain, tts, avatar)
                    last_small_talk_time = time.monotonic()
                    # last_interaction は更新しない → 即次の発話へ続く
                except asyncio.CancelledError:
                    pass
                finally:
                    is_speaking.clear()
            else:
                await asyncio.sleep(0.3)


async def main(config_path: str, video_id_override: str | None, use_tts: bool) -> None:
    config = load_config(config_path)
    brain = Brain(config)
    st_cfg = config.small_talk
    yt_cfg = config.youtube

    if video_id_override:
        yt_cfg = yt_cfg.model_copy(update={"video_id": video_id_override})

    if not yt_cfg.api_key:
        print("[エラー] YOUTUBE_API_KEY が設定されていません。.env を確認してください。")
        return
    if not yt_cfg.video_id:
        print("[エラー] video_id が設定されていません。--video-id または config を確認してください。")
        return

    tts = None
    if use_tts:
        tts = VoicevoxClient(config.tts)
        if not await tts.is_available():
            print("[警告] VOICEVOXが起動していません。テキストのみで動作します。")
            tts = None

    avatar = create_avatar_controller(config.avatar)
    await avatar.start()

    char_name = config.character.name
    print(f"=== {char_name} の YouTube Live セッション ===")
    print(f"[YouTube Live] video_id={yt_cfg.video_id} の配信に接続中...")

    reader = YouTubeChatReader(yt_cfg)
    try:
        await reader.initialize()
    except Exception as e:
        print(f"[エラー] 初期化失敗: {e}")
        await avatar.stop()
        return

    print(f"[YouTube Live] 接続完了。コメント待機中...")
    if st_cfg.enabled:
        print(f"[雑談モード有効: {st_cfg.silence_timeout_sec:.0f}秒の沈黙で自発発話]")
    print()

    last_interaction: list[float] = [time.monotonic()]
    comment_queue: asyncio.Queue = asyncio.Queue()

    fill_task = asyncio.create_task(
        fill_comment_queue(reader, comment_queue)
    )
    resp_task = asyncio.create_task(
        response_loop(brain, tts, avatar, st_cfg, comment_queue, last_interaction)
    )

    try:
        await asyncio.gather(fill_task, resp_task)
    except QuotaExceededError:
        print("\n[エラー] YouTube API のクォータを超過しました。明日まで待ってください。")
    except KeyboardInterrupt:
        print("\n終了します。")
    finally:
        fill_task.cancel()
        resp_task.cancel()
        await avatar.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/character.yaml", help="設定ファイルのパス")
    parser.add_argument("--video-id", default=None, help="YouTube Live の動画ID")
    parser.add_argument("--no-tts", action="store_true", help="音声合成を無効にする")
    args = parser.parse_args()

    asyncio.run(main(args.config, args.video_id, use_tts=not args.no_tts))
