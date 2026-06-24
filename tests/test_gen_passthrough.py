"""Bug7: 统一前后端 gen 计数器。

前端把自己的 gen 传进 chat()/startup_mix()，后端就用这个 gen（不再各自 +1），
逐句推送与后台续解的 gen 都来自同一真相源，消除跨桥错位导致解锁歌被误丢。
"""
from backend import config


def _make_api(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    import app
    return app, app.Api()


def test_chat_uses_passed_gen(monkeypatch, tmp_path):
    app, api = _make_api(monkeypatch, tmp_path)
    monkeypatch.setattr(app.news, "cached_items", lambda *a, **k: [])
    monkeypatch.setattr(app.news, "digest", lambda items, n=16: "")
    monkeypatch.setattr(app.memory, "context_blurb", lambda: "")
    monkeypatch.setattr(app.host, "stream_reply", lambda *a, **k: iter(["Hello there. "]))
    monkeypatch.setattr(api, "_remember", lambda *a, **k: None)   # 别真起记忆提炼后台线程

    # 流式路径走 _SentencePipeline → _push_sentence；这里换成真合成的轻量替身，捕获 gen
    monkeypatch.setattr(api, "_synth_voice", lambda sentence, s: ("voice", []))
    emitted_gens = []
    monkeypatch.setattr(api, "_push_sentence",
                        lambda win, gen, idx, sent, voice, words: emitted_gens.append(gen))

    res = api.chat("hi", 42)
    assert res["ok"] is True
    assert api._gen == 42                          # 后端采用前端传来的 gen
    assert emitted_gens and all(g == 42 for g in emitted_gens)


def test_startup_mix_uses_passed_gen(monkeypatch, tmp_path):
    app, api = _make_api(monkeypatch, tmp_path)
    monkeypatch.setattr(app.memory, "rollover", lambda: False)
    monkeypatch.setattr(app.music, "is_up", lambda: True)
    monkeypatch.setattr(app.weather, "current", lambda: {"ok": False})
    monkeypatch.setattr(app.config, "get_api_key", lambda: "")   # 跳过开场白生成
    monkeypatch.setattr(app.music, "something", lambda limit=12: [])

    res = api.startup_mix(7)
    assert res["ok"] is True
    assert api._gen == 7
