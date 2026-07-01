"""按 id 前缀把请求路由到对应 provider。本期只注册网易云；多源时即插。"""
from __future__ import annotations

from .base import MusicProvider, ProviderError, unpack_id


class Registry:
    def __init__(self):
        self._by_prefix: dict[str, MusicProvider] = {}

    def register(self, provider: MusicProvider) -> None:
        if provider.prefix in self._by_prefix:
            raise ValueError(f"prefix 冲突: {provider.prefix}")
        self._by_prefix[provider.prefix] = provider

    def get(self, prefix: str) -> MusicProvider:
        p = self._by_prefix.get(prefix)
        if p is None:
            raise ProviderError("NOT_FOUND", "registry", f"未知 provider 前缀: {prefix}")
        return p

    def resolve(self, track_id: str) -> MusicProvider:
        prefix, _ = unpack_id(track_id)
        return self.get(prefix)

    def list(self) -> list[str]:
        return list(self._by_prefix)
