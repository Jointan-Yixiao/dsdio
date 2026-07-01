"""点歌板块健壮性：泛请求不破坏全局状态、脏搜索结果不致命、交互路径超时更紧。"""
import pytest
from backend import config, music
from backend.providers.base import ProviderError
from backend.providers.netease import NeteaseProvider


def test_something_does_not_mutate_global_keywords(monkeypatch):
    original = list(config.FILLER_KEYWORDS)
    monkeypatch.setattr(music.random, "shuffle", lambda seq: seq.reverse())
    monkeypatch.setattr(music, "search_playable", lambda kw, limit=12: [])
    music.something()
    assert config.FILLER_KEYWORDS == original


def test_search_playable_skips_songs_without_id(monkeypatch):
    def fake_get(self, path, timeout=15, **params):
        if path == "/cloudsearch":
            return {"result": {"songs": [
                {"name": "no-id"},
                {"id": 2, "name": "B", "ar": [{"name": "y"}], "al": {}},
            ]}}
        if path == "/song/url":
            return {"data": [{"id": 2, "url": "http://free/2"}]}
        return {}
    monkeypatch.setattr(NeteaseProvider, "_get", fake_get)
    tracks = music.search_playable("hi", limit=5)
    assert {t["id"] for t in tracks} == {"ncm:2"}      # 脏条目被丢，不抛 KeyError


def test_interactive_search_uses_tighter_timeout_than_startup(monkeypatch):
    seen: dict[str, int] = {}

    def fake_get(self, path, timeout=15, **params):
        seen[path] = timeout
        if path == "/cloudsearch":
            return {"result": {"songs": [{"id": 1, "name": "A", "ar": [{"name": "x"}], "al": {}}]}}
        if path == "/song/url":
            return {"data": [{"id": 1, "url": "http://free/1"}]}
        return {}
    monkeypatch.setattr(NeteaseProvider, "_get", fake_get)

    music.search_split("hi", limit=3)                  # 交互路径：紧超时
    assert seen["/cloudsearch"] < 15
    assert seen["/song/url"] < 15

    seen.clear()
    music.search_playable("hi", limit=3)               # 开机铺垫：宽默认
    assert seen["/cloudsearch"] == 15
    assert seen["/song/url"] == 15


def test_search_split_skips_songs_without_id(monkeypatch):
    def fake_get(self, path, timeout=15, **params):
        if path == "/cloudsearch":
            return {"result": {"songs": [
                {"name": "no-id"},
                {"id": 7, "name": "C", "ar": [{"name": "z"}], "al": {}},
            ]}}
        if path == "/song/url":
            return {"data": [{"id": 7, "url": "http://free/7"}]}
        return {}
    monkeypatch.setattr(NeteaseProvider, "_get", fake_get)
    ready, pending = music.search_split("hi", limit=5)
    assert {t["id"] for t in ready} == {"ncm:7"}


def test_resolve_pending_converges_provider_error(monkeypatch):
    # 门面约束：对外错误统一 MusicError，ProviderError 不得冒泡
    def boom(self, pending, max_n=12):
        raise ProviderError("NETWORK", "netease-enhanced", "boom")
    monkeypatch.setattr(NeteaseProvider, "resolve_pending", boom)
    with pytest.raises(music.MusicError):
        list(music.resolve_pending([{"id": 1}]))
