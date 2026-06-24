"""Bug6: 迷你态热键陷阱兜底。

迷你态全鼠标穿透后，唯一还原途径是全局热键 Ctrl+Alt+D。一旦热键没注册成功
(被别的程序占了)，用户就会卡死、只能杀进程。兜底：热键不可用时不进全穿透态，
保留磨砂 + 不穿透，让用户仍能点头像还原。
"""
from backend import config


def _make_api(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    import app
    return app, app.Api()


def _stub_win(monkeypatch, app, ct_calls, acrylic_calls):
    monkeypatch.setattr(app.win_effects, "find_hwnd", lambda title: 123)
    monkeypatch.setattr(app.win_effects, "window_rect", lambda h: (0, 0, 400, 800))
    monkeypatch.setattr(app.win_effects, "enable_acrylic",
                        lambda h, enable=True: acrylic_calls.append(enable))
    monkeypatch.setattr(app.win_effects, "set_clickthrough_key",
                        lambda h, on: ct_calls.append(on))
    monkeypatch.setattr(app.win_effects, "dock_right", lambda *a, **k: True)


def test_no_hotkey_keeps_clickable(monkeypatch, tmp_path):
    app, api = _make_api(monkeypatch, tmp_path)
    api._hotkey_ok = False
    ct, acrylic = [], []
    _stub_win(monkeypatch, app, ct, acrylic)

    r = api.enter_mini()
    assert r["mini"] is True
    assert r["clickthrough"] is False     # 不进全穿透
    assert ct == [False]                  # 不开鼠标穿透 → 头像可点回
    assert acrylic == [True]              # 保留磨砂，迷你条仍可见可点


def test_hotkey_enables_full_transparent_mini(monkeypatch, tmp_path):
    app, api = _make_api(monkeypatch, tmp_path)
    api._hotkey_ok = True
    ct, acrylic = [], []
    _stub_win(monkeypatch, app, ct, acrylic)

    r = api.enter_mini()
    assert r["clickthrough"] is True      # 热键可用 → 全透明穿透
    assert ct == [True]
    assert acrylic == [False]             # 关磨砂，真透出桌面


def test_default_hotkey_ok_is_false(monkeypatch, tmp_path):
    # 还没确认热键注册成功前，默认按"不可用"处理，宁可保守也不卡死
    app, api = _make_api(monkeypatch, tmp_path)
    assert api._hotkey_ok is False
