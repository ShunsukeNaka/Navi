"""
YouTube Data API v3 を httpx で直接叩くライブチャット読み取りクラス。

APIクォータ: liveChat.messages.list は 5ユニット/回、上限10,000ユニット/日
  → APIが返す pollingIntervalMillis を必ず尊重すること（最低5秒のガード付き）
  → 6時間配信 + 15秒間隔 = 7,200ユニット（余裕あり）

.env に YOUTUBE_API_KEY を設定しておくこと。
"""
from __future__ import annotations

import random
from typing import AsyncIterator

import httpx

from ..core.config import YouTubeConfig


_VIDEOS_API = "https://www.googleapis.com/youtube/v3/videos"
_LIVE_CHAT_API = "https://www.googleapis.com/youtube/v3/liveChat/messages"


class YouTubeChatError(Exception):
    """YouTube API 関連のエラー基底クラス"""


class LiveStreamEndedError(YouTubeChatError):
    """配信が終了したか、チャットが無効なときに raise する"""


class QuotaExceededError(YouTubeChatError):
    """API クォータ超過 (403 quotaExceeded) のときに raise する"""


class YouTubeChatReader:
    """
    使い方:
        reader = YouTubeChatReader(config.youtube)
        await reader.initialize()   # live_chat_id を取得・初期化
        async for comment in reader.stream_comments():
            print(comment)
    """

    def __init__(self, config: YouTubeConfig):
        self._config = config
        self._live_chat_id: str | None = None
        self._page_token: str | None = None

    async def initialize(self) -> None:
        """video_id から live_chat_id を取得し、起動前の古いコメントを無視するため初回pageTokenを取得する"""
        self._live_chat_id = await self.get_live_chat_id(self._config.video_id)
        # 起動前に投稿された古いコメントを無視するため、現在の nextPageToken だけ取得する
        _, _, next_token = await self._fetch_messages(max_results=1)
        self._page_token = next_token

    async def get_live_chat_id(self, video_id: str) -> str:
        """
        動画IDから activeLiveChatId を取得する。

        GET https://www.googleapis.com/youtube/v3/videos
            ?part=liveStreamingDetails&id={video_id}&key={api_key}
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                _VIDEOS_API,
                params={
                    "part": "liveStreamingDetails",
                    "id": video_id,
                    "key": self._config.api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        items = data.get("items", [])
        if not items:
            raise YouTubeChatError(f"動画が見つかりません: video_id={video_id!r}")

        live_chat_id = (
            items[0]
            .get("liveStreamingDetails", {})
            .get("activeLiveChatId")
        )
        if not live_chat_id:
            raise LiveStreamEndedError(
                f"配信中でないか、チャットが無効です: video_id={video_id!r}"
            )
        return live_chat_id

    async def poll(self) -> tuple[list[str], float]:
        """
        ライブチャットを1回ポーリングしてコメントリストと次回待機秒数を返す。

        Returns:
            (comments, wait_sec):
                comments  - フィルタ済みコメントのリスト
                wait_sec  - 次回ポーリングまでの待機秒数（APIの推奨値、最低5秒）
        """
        if self._live_chat_id is None:
            raise RuntimeError("initialize() を先に呼び出してください")

        comments, polling_interval_ms, next_token = await self._fetch_messages(
            max_results=self._config.max_comments_per_poll
        )
        self._page_token = next_token

        # APIが返す推奨インターバルを尊重（最低5秒のガード）
        wait_sec = max(polling_interval_ms / 1000.0, 5.0)
        return comments, wait_sec

    async def stream_comments(self) -> AsyncIterator[str]:
        """
        無限ループでポーリングし、新着コメントがあればランダムに1件 yield する。

        - コメントなし → 待機のみ
        - コメントあり → ランダムに1件選択して yield
        - 一時的なAPIエラー → 指数バックオフ（2, 4, 8秒）で最大3回リトライ
        - LiveStreamEndedError → ループ終了
        - QuotaExceededError → re-raise（呼び出し元で終了処理）
        """
        import asyncio

        retry_count = 0
        max_retries = 3

        while True:
            try:
                comments, wait_sec = await self.poll()
                retry_count = 0  # 成功したらリセット

                if comments:
                    yield random.choice(comments)

                await asyncio.sleep(wait_sec)

            except LiveStreamEndedError:
                break

            except QuotaExceededError:
                raise

            except (httpx.HTTPError, YouTubeChatError) as e:
                retry_count += 1
                if retry_count > max_retries:
                    raise
                backoff = 2 ** retry_count
                print(f"\n[YouTube API エラー: {e}。{backoff}秒後にリトライ ({retry_count}/{max_retries})]")
                await asyncio.sleep(backoff)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _fetch_messages(
        self, max_results: int
    ) -> tuple[list[str], int, str | None]:
        """
        API を1回呼び出してコメントリスト・pollingIntervalMs・nextPageToken を返す。

        GET https://www.googleapis.com/youtube/v3/liveChat/messages
            ?liveChatId={id}&part=snippet,authorDetails
            &key={api_key}&pageToken={token}&maxResults={n}
        """
        params: dict = {
            "liveChatId": self._live_chat_id,
            "part": "snippet,authorDetails",
            "key": self._config.api_key,
            "maxResults": max_results,
        }
        if self._page_token:
            params["pageToken"] = self._page_token

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(_LIVE_CHAT_API, params=params)

            if resp.status_code == 403:
                errors = resp.json().get("error", {}).get("errors", [])
                if any(e.get("reason") == "quotaExceeded" for e in errors):
                    raise QuotaExceededError("YouTube Data API のクォータを超過しました")

            if resp.status_code == 404:
                raise LiveStreamEndedError("ライブチャットが見つかりません（配信終了の可能性）")

            resp.raise_for_status()
            data = resp.json()

        polling_interval_ms: int = data.get("pollingIntervalMillis", int(self._config.polling_interval_sec * 1000))
        next_token: str | None = data.get("nextPageToken")
        items: list[dict] = data.get("items", [])

        comments = self._extract_comments(items)
        return comments, polling_interval_ms, next_token

    def _extract_comments(self, items: list[dict]) -> list[str]:
        """
        items からテキストコメントを抽出する。

        除外対象:
          - スーパーチャット・スーパーステッカー（type != textMessageEvent）
          - Bot コメント（authorDetails.isChatBot == True）
          - 空テキスト
        """
        result = []
        for item in items:
            author = item.get("authorDetails", {})
            if author.get("isChatBot"):
                continue

            snippet = item.get("snippet", {})
            if snippet.get("type") != "textMessageEvent":
                continue

            text: str = snippet.get("textMessageDetails", {}).get("messageText", "").strip()
            if text:
                result.append(text)

        return result
