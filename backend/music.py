# backend/music.py
"""音乐门面：对外保持稳定函数，内部委托当前音源 provider。

历史上直连本地 NeteaseCloudMusicApi；现经 provider 抽象层（backend/providers/），
音源由用户自部署、config.MUSIC_API_BASE 注入。app.py / 前端零改动。
"""
from __future__ import annotations

import random

from . import config
from .providers import default_provider
from .providers.base import ProviderError


class MusicError(Exception):
    pass


def _p():
    return default_provider()


def is_up(timeout: float = 2) -> bool:
    return _p().is_up(timeout)


def search_playable(keywords: str, limit: int = 10) -> list[dict]:
    """搜索并返回可播放曲目（免费全曲直用，被锁的交后端解锁）。"""
    try:
        return _p().search(keywords, limit)
    except ProviderError as e:
        raise MusicError(str(e)) from e


def search_split(keywords: str, limit: int = 12, timeout: int = 8):
    """交互点歌快路径：返回 (ready, pending)。"""
    try:
        return _p().search_split(keywords, limit, timeout)
    except ProviderError as e:
        raise MusicError(str(e)) from e


def resolve_pending(songs: list[dict], max_n: int = 12):
    """后台续解 pending（逐首 yield 归一化 track）。"""
    yield from _p().resolve_pending(songs, max_n)


def something(limit: int = 12) -> list[dict]:
    """随便来点能放的（泛请求）。"""
    for kw in random.sample(config.FILLER_KEYWORDS, len(config.FILLER_KEYWORDS)):
        tracks = search_playable(kw, limit)
        if tracks:
            return tracks
    return []
