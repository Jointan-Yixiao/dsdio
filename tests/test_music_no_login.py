"""用户决策: 彻底删除网易云登录，只留 nodeapi + UNM。

- 登录相关接口(扫码/手机号/cookie/REAL_IP)应全部移除。
- 搜索取址在无 cookie 下仍正常：网易云有免费地址的直接用，被锁的交 UNM 解锁。
"""
from backend import music


def test_login_surface_removed():
    for gone in ("saved_cookie", "qr_key", "qr_create", "qr_check",
                 "send_captcha", "login_cellphone", "login_nickname", "REAL_IP"):
        assert not hasattr(music, gone), f"{gone} 应已删除（登录已下线）"


def test_search_playable_works_without_cookie(monkeypatch):
    def fake_get(path, timeout=15, **params):
        if path == "/cloudsearch":
            return {"result": {"songs": [
                {"id": 1, "name": "A", "ar": [{"name": "x"}], "al": {}},
                {"id": 2, "name": "B", "ar": [{"name": "y"}], "al": {}},
            ]}}
        if path == "/song/url":
            assert "cookie" not in params           # 不再带 cookie
            return {"data": [{"id": 1, "url": "http://free/1"}, {"id": 2, "url": None}]}
        return {}
    monkeypatch.setattr(music, "_get", fake_get)
    monkeypatch.setattr(music, "unm_match", lambda sid: ("http://unm/2", "kuwo"))

    tracks = music.search_playable("hi", limit=2)
    by_id = {t["id"]: t for t in tracks}
    assert set(by_id) == {1, 2}
    assert by_id[1]["url"] == "http://free/1"        # 免费地址直接用
    assert by_id[2]["url"] == "http://unm/2"          # 被锁的 UNM 解锁
    assert by_id[2]["unlocked"] is True


def test_search_playable_signature_has_no_cookie_param():
    import inspect
    assert "cookie" not in inspect.signature(music.search_playable).parameters
