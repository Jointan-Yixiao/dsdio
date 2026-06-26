"""点歌板块的健壮性：泛请求不破坏全局状态、脏搜索结果不致命。

- something() 选填充关键词时不能原地打乱模块级 FILLER_KEYWORDS（多线程并发会互相搅动）。
- 搜索结果里偶发缺 id 的脏条目应被跳过，而不是在拼 id 参数时抛 KeyError 把整次点歌带崩。
"""
from backend import music


def test_something_does_not_mutate_global_keywords(monkeypatch):
    original = list(music.FILLER_KEYWORDS)
    # 让"打乱"确定性地改变顺序，避免依赖随机；同时把搜索打掉只验证副作用。
    monkeypatch.setattr(music.random, "shuffle", lambda seq: seq.reverse())
    monkeypatch.setattr(music, "search_playable", lambda kw, limit=12: [])
    music.something()
    assert music.FILLER_KEYWORDS == original


def test_search_playable_skips_songs_without_id(monkeypatch):
    def fake_get(path, timeout=15, **params):
        if path == "/cloudsearch":
            return {"result": {"songs": [
                {"name": "no-id"},                                  # 脏条目：缺 id
                {"id": 2, "name": "B", "ar": [{"name": "y"}], "al": {}},
            ]}}
        if path == "/song/url/v1":
            return {"data": [{"id": 2, "url": "http://free/2"}]}
        return {}
    monkeypatch.setattr(music, "_get", fake_get)
    tracks = music.search_playable("hi", limit=5)
    assert {t["id"] for t in tracks} == {2}                        # 不抛 KeyError，脏条目被丢


def test_interactive_search_uses_tighter_timeout_than_startup(monkeypatch):
    """点歌（chat 走 search_split）给搜索请求设更短超时上限，避免极端慢网下 chat() 长挂；
    而开机铺垫（startup 走 search_playable）保持宽松默认，宁可多等也别铺不出歌单。"""
    seen: dict[str, int] = {}

    def fake_get(path, timeout=15, **params):
        seen[path] = timeout
        if path == "/cloudsearch":
            return {"result": {"songs": [{"id": 1, "name": "A", "ar": [{"name": "x"}], "al": {}}]}}
        if path == "/song/url/v1":
            return {"data": [{"id": 1, "url": "http://free/1"}]}
        return {}
    monkeypatch.setattr(music, "_get", fake_get)

    music.search_split("hi", limit=3)                         # 交互路径
    assert seen["/cloudsearch"] < 15
    assert seen["/song/url/v1"] < 15

    seen.clear()
    music.search_playable("hi", limit=3)                      # 开机铺垫路径
    assert seen["/cloudsearch"] == 15
    assert seen["/song/url/v1"] == 15


def test_search_split_skips_songs_without_id(monkeypatch):
    def fake_get(path, timeout=15, **params):
        if path == "/cloudsearch":
            return {"result": {"songs": [
                {"name": "no-id"},                                  # 脏条目：缺 id
                {"id": 7, "name": "C", "ar": [{"name": "z"}], "al": {}},
            ]}}
        if path == "/song/url/v1":
            return {"data": [{"id": 7, "url": "http://free/7"}]}
        return {}
    monkeypatch.setattr(music, "_get", fake_get)
    ready, pending = music.search_split("hi", limit=5)
    assert {t["id"] for t in ready} == {7}                         # 不抛 KeyError，脏条目被丢
