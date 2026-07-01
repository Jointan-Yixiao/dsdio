"""音源 provider 契约：归一化模型 + id 前缀 + 错误模型。

播放器只依赖这里的接口与归一化 dict，不感知任何具体音源后端。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


class ProviderError(Exception):
    """provider 对外统一错误；禁止让原始 urllib/HTTP 错误冒泡到上层。"""

    def __init__(self, code: str, provider_id: str, message: str):
        super().__init__(message)
        self.code = code            # NETWORK / NOT_FOUND / UNAVAILABLE / UNKNOWN
        self.provider_id = provider_id


def pack_id(prefix: str, raw_id) -> str:
    """把某音源的原始 id 打成带前缀的全局 id，如 pack_id('ncm', 123) -> 'ncm:123'。"""
    return f"{prefix}:{raw_id}"


def unpack_id(track_id: str) -> tuple[str, str]:
    """拆分带前缀 id，返回 (prefix, raw_id)；缺前缀抛 ValueError。"""
    prefix, sep, raw = track_id.partition(":")
    if not sep:
        raise ValueError(f"id 缺 provider 前缀: {track_id!r}")
    return prefix, raw


def normalize_track(prefix: str, x: dict, url: str,
                    unlocked: bool = False, source: str = "") -> dict:
    """把某音源的原始歌曲对象归一化成统一 track dict（id 带前缀）。"""
    al = x.get("al") or x.get("album") or {}
    ar = x.get("ar") or x.get("artists") or []
    return {
        "id": pack_id(prefix, x["id"]),
        "name": x.get("name", ""),
        "artist": "、".join(a.get("name", "") for a in ar) or "Unknown",
        "album": al.get("name", ""),
        "cover": al.get("picUrl", ""),
        "duration": x.get("dt", 0) or x.get("duration", 0),
        "url": url,
        "unlocked": unlocked,   # 是否经后端解锁找回
        "source": source,       # 解锁来源；后端不回传时为空
    }


@runtime_checkable
class MusicProvider(Protocol):
    prefix: str

    def is_up(self, timeout: float = 2) -> bool: ...
    def search(self, keywords: str, limit: int) -> list[dict]: ...
    def search_split(self, keywords: str, limit: int, timeout: int) -> tuple[list[dict], list[dict]]: ...
    def resolve_pending(self, pending: list[dict], max_n: int): ...
