import pytest
from backend import config
from backend.providers.netease import NeteaseProvider


@pytest.fixture(autouse=True)
def _base(monkeypatch):
    monkeypatch.setattr(config, "MUSIC_API_BASE", "http://x")  # 非空即“已配置”


def _mk(monkeypatch, songs, url_rows, unlock_url="http://unm/full"):
    """注入 HTTP 接缝：/cloudsearch 返回 songs；/song/url 返回 url_rows；/song/url/match 返回 unlock_url。"""
    def fake_get(self, path, timeout=15, **params):
        if path == "/cloudsearch":
            return {"result": {"songs": songs}}
        if path == "/song/url":
            return {"data": url_rows}
        if path == "/song/url/match":
            return {"code": 200, "data": unlock_url}
        return {}
    monkeypatch.setattr(NeteaseProvider, "_get", fake_get)


def test_is_full_detects_trial_and_empty():
    assert NeteaseProvider._is_full({"url": "http://u"}) is True
    assert NeteaseProvider._is_full({"url": "http://u", "freeTrialInfo": {"x": 1}}) is False  # 试听
    assert NeteaseProvider._is_full({"url": None}) is False


def test_free_full_song_used_directly(monkeypatch):
    _mk(monkeypatch,
        songs=[{"id": 1, "name": "A", "ar": [{"name": "x"}], "al": {}}],
        url_rows=[{"id": 1, "url": "http://free/1"}])
    tracks = NeteaseProvider().search("hi", limit=1)
    assert tracks[0]["id"] == "ncm:1"
    assert tracks[0]["url"] == "http://free/1" and tracks[0]["unlocked"] is False


def test_trial_clip_gets_unlocked(monkeypatch):
    # /song/url 给了 url 但带 freeTrialInfo（30s 试听）→ 必须走解锁拿完整地址
    _mk(monkeypatch,
        songs=[{"id": 2, "name": "B", "ar": [{"name": "y"}], "al": {}}],
        url_rows=[{"id": 2, "url": "http://trial/2", "freeTrialInfo": {"start": 0}}],
        unlock_url="http://full/2")
    tracks = NeteaseProvider().search("hi", limit=1)
    assert tracks[0]["url"] == "http://full/2" and tracks[0]["unlocked"] is True


def test_empty_url_gets_unlocked(monkeypatch):
    _mk(monkeypatch,
        songs=[{"id": 3, "name": "C", "ar": [{"name": "z"}], "al": {}}],
        url_rows=[{"id": 3, "url": None}],
        unlock_url="http://full/3")
    tracks = NeteaseProvider().search("hi", limit=1)
    assert tracks[0]["url"] == "http://full/3" and tracks[0]["unlocked"] is True


def test_search_split_first_locked_unlocked_rest_pending(monkeypatch):
    _mk(monkeypatch,
        songs=[{"id": 1, "name": "A", "ar": [{"name": "x"}], "al": {}},
               {"id": 2, "name": "B", "ar": [{"name": "y"}], "al": {}}],
        url_rows=[{"id": 1, "url": "http://trial/1", "freeTrialInfo": {"s": 0}},
                  {"id": 2, "url": "http://trial/2", "freeTrialInfo": {"s": 0}}],
        unlock_url="http://full/x")
    ready, pending = NeteaseProvider().search_split("hi", limit=5, timeout=8)
    assert ready and ready[0]["unlocked"] is True     # 头部被锁即时解一次定 track[0]
    assert [p["id"] for p in pending] == [2]           # 其余留 pending（原始对象）


def test_baseurl_empty_is_down(monkeypatch):
    monkeypatch.setattr(config, "MUSIC_API_BASE", "")
    assert NeteaseProvider().is_up() is False
