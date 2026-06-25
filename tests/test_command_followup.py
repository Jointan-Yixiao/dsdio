"""命令后的"第二段 DJ 回应"。

切歌/暂停等命令命中、固定短语已脱口而出之后，再走一次 DeepSeek 让 Dsdio 用 DJ 口吻
自然补一句——靠 prompt 引导"别重复刚说的、别重新打招呼"，并把刚切到的新歌名告诉她。
"""
import pytest

from backend import commands, host


# ---------- commands: action -> 人类可读情境 ----------
@pytest.mark.parametrize("action,frag", [
    ("next", "next"),
    ("prev", "previous"),
    ("pause", "pause"),
    ("resume", "resum"),
])
def test_followup_action_desc(action, frag):
    assert frag in commands.followup_action_desc(action).lower()


def test_followup_action_desc_unknown():
    assert commands.followup_action_desc("xyz") == ""


# ---------- host.command_followup: prompt 拼装 + 返回 ----------
class _FakeResp:
    def __init__(self, text):
        msg = type("M", (), {"content": text})()
        self.choices = [type("C", (), {"message": msg})()]


class _FakeClient:
    def __init__(self, capture, text="This one's a slow burner."):
        self._cap = capture
        self._text = text
        self.chat = self
        self.completions = self

    def create(self, *, model, messages, **kw):
        self._cap["messages"] = messages
        self._cap["kw"] = kw
        return _FakeResp(self._text)


def test_command_followup_builds_prompt(monkeypatch):
    cap = {}
    monkeypatch.setattr(host, "_client", lambda: _FakeClient(cap))

    text = host.command_followup(
        history=[{"role": "user", "content": "hey"}],
        action="next",
        said="You got it — next one.",
        now_playing="夜空中最亮的星 — 逃跑计划",
        memory_ctx="",
    )
    assert text == "This one's a slow burner."

    msgs = cap["messages"]
    blob = "\n".join(m["content"] for m in msgs)
    assert "You got it — next one." in blob          # 告诉它已脱口的固定短语
    assert "夜空中最亮的星 — 逃跑计划" in blob          # 新歌名
    assert "next track" in blob.lower()              # 情境
    assert "repeat" in blob.lower()                  # 别重复
    assert "greet" in blob.lower()                   # 别重新打招呼
    assert cap["kw"].get("stream") in (None, False)  # 非流式
    # 末尾语言锁（英文）
    assert msgs[-1]["role"] == "system"
    assert "english" in msgs[-1]["content"].lower()


def test_command_followup_without_now_playing(monkeypatch):
    cap = {}
    monkeypatch.setattr(host, "_client", lambda: _FakeClient(cap))
    text = host.command_followup([], "pause", "Paused.", "", "")
    assert text == "This one's a slow burner."
    blob = "\n".join(m["content"] for m in cap["messages"])
    assert "pause" in blob.lower()


# ---------- Api.command_followup: 桥 + 降级 ----------
def _make_api(monkeypatch, tmp_path):
    from backend import config as cfg
    monkeypatch.setattr(cfg, "SETTINGS_FILE", tmp_path / "settings.json")
    import app
    monkeypatch.setattr(app.memory, "context_blurb", lambda: "")
    return app, app.Api()


def test_api_command_followup_ok(monkeypatch, tmp_path):
    app, api = _make_api(monkeypatch, tmp_path)
    seen = {}

    def fake(history, action, say, now_playing, memory_ctx):
        seen.update(action=action, say=say, now=now_playing)
        return "Nice pick."

    monkeypatch.setattr(app.host, "command_followup", fake)

    r = api.command_followup("next", "You got it.", "Song — Artist")
    assert r["ok"] is True and r["text"] == "Nice pick."
    assert seen == {"action": "next", "say": "You got it.", "now": "Song — Artist"}


def test_api_command_followup_degrades_on_error(monkeypatch, tmp_path):
    app, api = _make_api(monkeypatch, tmp_path)

    def boom(*a, **k):
        raise RuntimeError("deepseek down")

    monkeypatch.setattr(app.host, "command_followup", boom)
    r = api.command_followup("next", "x", "")
    assert r["ok"] is False
