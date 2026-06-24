"""Bug3: 对话版已不读的死设置键应从设置里移出。

- categories / fresh_hours：新闻抓取实际用 config.CATEGORIES / config.NEWS_FRESH_HOURS，
  这两个用户键从不被读取。
- count：聊新闻条数，对话版 host 自行决定，只有(将删的)llm.py 用过 → 也死了。
"""
from backend import config

DEAD = ("categories", "fresh_hours", "count")


def test_default_settings_drops_dead_keys():
    for k in DEAD:
        assert k not in config.DEFAULT_SETTINGS, f"{k} 仍在 DEFAULT_SETTINGS"


def test_get_state_settings_omits_dead_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    import app
    monkeypatch.setattr(app.music, "is_up", lambda: False)
    monkeypatch.setattr(app.autostart, "is_enabled", lambda: False)
    api = app.Api()
    settings = api.get_state()["settings"]
    assert "count" not in settings
    assert "categories" not in settings
