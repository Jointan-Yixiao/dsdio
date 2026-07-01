# backend/providers/__init__.py
"""音源 provider 层：装配默认 registry（本期只注册网易云）。"""
from .base import MusicProvider, ProviderError, normalize_track, pack_id, unpack_id
from .netease import NeteaseProvider
from .registry import Registry

_registry = Registry()
_registry.register(NeteaseProvider())


def registry() -> Registry:
    return _registry


def default_provider() -> MusicProvider:
    """当前活跃 provider（本期唯一：网易云）。将来多源时按 id 前缀 resolve。"""
    return _registry.get("ncm")
