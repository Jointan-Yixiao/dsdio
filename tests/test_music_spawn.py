"""start_music_server 的可选本地 spawn 决策：只在 baseUrl 指向本机、且本地 music-api/ 存在时才起。"""
import types
import pytest

import app as app_module
from backend import config, music


def _api(monkeypatch, base, up=False, server_exists=True):
    monkeypatch.setattr(config, "MUSIC_API_BASE", base)
    monkeypatch.setattr(music, "is_up", lambda timeout=2: up)
    # 假 MUSIC_API_DIR：其 (dir/"server.js").exists() 由 server_exists 决定
    class _P:
        def __truediv__(self, _): return self
        def exists(self): return server_exists
    monkeypatch.setattr(config, "MUSIC_API_DIR", _P())
    spawned = {}
    def fake_spawn(self, work_dir, env_extra=None):
        spawned["called"] = True; spawned["env"] = env_extra; return object()
    monkeypatch.setattr(app_module.Api, "_spawn_node", fake_spawn)
    api = app_module.Api.__new__(app_module.Api)   # 不跑 __init__
    api._music_proc = None
    return api, spawned


def test_spawns_when_localhost_and_dir_exists(monkeypatch):
    api, spawned = _api(monkeypatch, "http://localhost:3000", up=False, server_exists=True)
    api.start_music_server()
    assert spawned.get("called") and spawned["env"]["NCM_PORT"] == "3000"


def test_no_spawn_for_remote_base(monkeypatch):
    api, spawned = _api(monkeypatch, "http://music.example.com", up=False, server_exists=True)
    api.start_music_server()
    assert not spawned.get("called")


def test_no_spawn_when_dir_missing(monkeypatch):
    api, spawned = _api(monkeypatch, "http://127.0.0.1:3000", up=False, server_exists=False)
    api.start_music_server()
    assert not spawned.get("called")


def test_no_spawn_when_base_empty(monkeypatch):
    api, spawned = _api(monkeypatch, "", up=False, server_exists=True)
    api.start_music_server()
    assert not spawned.get("called")
