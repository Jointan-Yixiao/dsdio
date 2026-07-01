"""用户决策: 彻底删除网易云登录，只留自部署后端 + 后端自带解锁。

- 登录相关接口应全部移除。
- 搜索取址在无 cookie 下正常：免费全曲直用，被锁（试听/空）交后端解锁。
"""
import inspect

from backend import music
from backend.providers.netease import NeteaseProvider


def test_login_surface_removed():
    for gone in ("saved_cookie", "qr_key", "qr_create", "qr_check",
                 "send_captcha", "login_cellphone", "login_nickname", "REAL_IP"):
        assert not hasattr(music, gone), f"{gone} 应已删除（登录已下线）"


def test_search_playable_works_without_cookie(monkeypatch):
    def fake_get(self, path, timeout=15, **params):
        if path == "/cloudsearch":
            return {"result": {"songs": [
                {"id": 1, "name": "A", "ar": [{"name": "x"}], "al": {}},
                {"id": 2, "name": "B", "ar": [{"name": "y"}], "al": {}},
            ]}}
        if path == "/song/url":
            assert "cookie" not in params           # 不带 cookie
            return {"data": [{"id": 1, "url": "http://free/1"}, {"id": 2, "url": None}]}
        return {}
    monkeypatch.setattr(NeteaseProvider, "_get", fake_get)
    monkeypatch.setattr(NeteaseProvider, "_unlock", lambda self, sid: "http://unm/2")

    tracks = music.search_playable("hi", limit=2)
    by_id = {t["id"]: t for t in tracks}
    assert set(by_id) == {"ncm:1", "ncm:2"}
    assert by_id["ncm:1"]["url"] == "http://free/1"      # 免费直用
    assert by_id["ncm:2"]["url"] == "http://unm/2"        # 被锁的解锁
    assert by_id["ncm:2"]["unlocked"] is True


def test_search_playable_signature_has_no_cookie_param():
    assert "cookie" not in inspect.signature(music.search_playable).parameters
