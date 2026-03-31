"""
ALSA エラーメッセージの抑制（WSL2環境向け）

'ALSA lib pcm.c:8772:(snd_pcm_recover) underrun occurred' などの
ノイジーなALSAログをサイレントにする。

使い方:
    from aivtuber.utils.alsa import suppress_alsa_errors
    suppress_alsa_errors()  # sounddevice の import より前に呼ぶ
"""
from __future__ import annotations


# モジュールレベルで参照を保持し、GCによる解放を防ぐ
_alsa_error_handler = None


def suppress_alsa_errors() -> None:
    """ALSA のエラーハンドラを無効化してログ出力を抑制する"""
    global _alsa_error_handler
    try:
        import ctypes
        from ctypes import CFUNCTYPE, c_char_p, c_int
        asound = ctypes.cdll.LoadLibrary("libasound.so.2")
        # コールバックをモジュール変数に保存してGCで解放されないようにする
        _alsa_error_handler = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)(lambda *_: None)
        asound.snd_lib_error_set_handler(_alsa_error_handler)
    except OSError:
        pass  # libasound が見つからない環境（macOS等）では何もしない
