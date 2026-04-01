# AIVTuber

AIを使ったVTuberシステム。キャラクター人格・感情・会話記憶をバックエンドで管理し、テキスト/音声で対話できる。

## 構成

```
AIVTuber/
├── config/
│   └── character.yaml      # キャラクター・LLM・TTSの設定（チューニングはここだけ）
├── scripts/
│   ├── chat.py             # テキスト入力で動作確認
│   ├── voice.py            # マイク入力フルパイプライン
│   └── youtube.py          # YouTube Live コメント読み取りパイプライン
└── src/aivtuber/
    ├── core/
    │   ├── brain.py        # 中心ロジック（LLM・記憶・感情を統合）
    │   ├── memory.py       # 会話履歴管理
    │   ├── emotion.py      # 感情検出・TTSパラメータ変換
    │   └── config.py       # YAML設定の読み込み・バリデーション
    ├── llm/                # LLMプロバイダー（差し替え可能）
    │   ├── groq.py
    │   ├── gemini.py
    │   ├── claude.py
    │   └── ollama.py
    ├── tts/
    │   └── voicevox.py     # VOICEVOX クライアント
    ├── stt/
    │   └── faster_whisper.py  # 音声認識
    └── chat/
        └── youtube.py      # YouTube Live チャット読み取り
```

## セットアップ

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
```

`.env` にAPIキーを設定：

```
GROQ_API_KEY=gsk_...
```

## 起動

### テキストモード（動作確認用）

```bash
python scripts/chat.py --no-tts
```

### 音声出力あり（VOICEVOXが必要）

[VOICEVOX](https://voicevox.hiroshiba.jp/) を起動してから：

```bash
python scripts/chat.py
```

### マイク入力フルパイプライン

```bash
python scripts/voice.py
```

### YouTube Live モード

`.env` に `YOUTUBE_API_KEY` を設定してから：

```bash
python scripts/youtube.py --video-id <VIDEO_ID>

# TTS なし（テキストのみ）
python scripts/youtube.py --video-id <VIDEO_ID> --no-tts
```

`video_id` は `config/character.yaml` の `youtube.video_id` に書いておくことも可能。

#### スーパーチャット対応

スーパーチャットを受信すると、通常コメントとは異なる専用の応答を返す：

- 送信者の名前・金額を含む感謝プロンプトを自動生成し、LLMに渡す
- AI発話中であっても割り込んで優先処理される
- 同一ポーリングに複数のメッセージがある場合、スーパーチャットが優先選択される

## LLMプロバイダーの切り替え

`config/character.yaml` の `llm` セクションを変更するだけ：

| プロバイダー | 無料 | APIキー取得先 |
|---|---|---|
| Groq（推奨） | 無料枠あり | https://console.groq.com |
| Gemini | 無料枠あり | https://aistudio.google.com/app/apikey |
| Ollama | 完全無料（ローカル） | https://ollama.com |
| Claude | 有料 | https://console.anthropic.com/settings/keys |

```yaml
llm:
  provider: "groq"
  model: "llama-3.3-70b-versatile"
```

## チューニング

すべて `config/character.yaml` で設定できる。コードを触る必要はない。

| 変更したいもの | 設定キー |
|---|---|
| キャラクターの人格 | `character.persona` |
| 返答の長さ | `character.response_style.max_sentences` |
| 感情ごとの声の速さ・高さ | `character.emotions.*.tts_speed/tts_pitch` |
| LLMの創造性 | `llm.temperature` |
| 会話の記憶量 | `llm.memory.short_term_turns` |
| VOICEVOXの話者 | `tts.voicevox.speaker_id` |

## 依存関係

- Python 3.10+
- [VOICEVOX](https://voicevox.hiroshiba.jp/)（音声出力を使う場合）
- [Ollama](https://ollama.com)（ローカルLLMを使う場合）
