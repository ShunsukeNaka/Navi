"""Avatar コントローラのファクトリ"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import AvatarController, NullAvatarController

if TYPE_CHECKING:
    from ..core.config import AvatarConfig


def create_avatar_controller(config: AvatarConfig) -> AvatarController:
    """
    config.avatar.type に応じたコントローラを返す。

    type:
        "none"          → NullAvatarController（何もしない）
        "browser"       → BrowserAvatarController（WebSocket）
        "vtube_studio"  → VTubeStudioController（未実装スタブ）
        "vmc"           → VMCController（未実装スタブ）
    """
    if config.type == "browser":
        from .browser import BrowserAvatarController
        return BrowserAvatarController(config)
    elif config.type == "vtube_studio":
        from .vtube_studio import VTubeStudioController
        return VTubeStudioController(config)
    elif config.type == "vmc":
        from .vmc import VMCController
        return VMCController(config)
    return NullAvatarController()


__all__ = ["AvatarController", "NullAvatarController", "create_avatar_controller"]
