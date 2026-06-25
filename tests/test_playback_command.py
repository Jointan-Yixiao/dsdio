"""本地播放控制命令解析（阶段 A）。

把"下一首 / 上一首 / 暂停 / 继续"这类直接命令在进 DeepSeek 之前拦下，就地操作播放器，
绝不误伤正常对话 / 点歌。match_playback 是纯函数，行为全部在这里钉死：
命中返回 {"action": ..., "say": <非空英文短语>}，否则 None。
"""
import pytest

from backend import commands


@pytest.mark.parametrize("text", [
    "下一首", "下一首吧", "下一首歌", "放下一首", "来下一首", "切下一首",
    "切歌", "换一首", "换个", "下一个", "下一曲",
    "跳过", "跳过这首", "跳过这首歌", "我要下一首", "帮我切下一首",
    "next", "Next", "next song", "Next song!", "next track",
    "skip", "skip it", "skip this",
])
def test_next_variants(text):
    r = commands.match_playback(text)
    assert r is not None, f"应识别为切下一首: {text!r}"
    assert r["action"] == "next"
    assert r["say"]


@pytest.mark.parametrize("text", [
    "上一首", "上一首吧", "上一个", "上一曲", "前一首",
    "返回上一首", "回上一首", "放上一首",
    "prev", "previous", "previous song", "go back", "back",
])
def test_prev_variants(text):
    r = commands.match_playback(text)
    assert r is not None, f"应识别为上一首: {text!r}"
    assert r["action"] == "prev"
    assert r["say"]


@pytest.mark.parametrize("text", [
    "暂停", "暂停一下", "暂停播放", "停一下", "停一停", "先暂停",
    "别放了", "安静一下",
    "pause", "Pause", "pause it", "stop", "hold on", "wait",
])
def test_pause_variants(text):
    r = commands.match_playback(text)
    assert r is not None, f"应识别为暂停: {text!r}"
    assert r["action"] == "pause"
    assert r["say"]


@pytest.mark.parametrize("text", [
    "继续", "继续吧", "继续放", "继续播放", "接着放", "接着听",
    "恢复", "恢复播放",
    "resume", "Resume", "unpause", "keep playing", "play on", "go on",
])
def test_resume_variants(text):
    r = commands.match_playback(text)
    assert r is not None, f"应识别为继续: {text!r}"
    assert r["action"] == "resume"
    assert r["say"]


def test_api_playback_command_proxies(monkeypatch, tmp_path):
    """js_api 桥：命中返回 action+say（前端据此就地切歌、不发 DeepSeek）；未命中 action=None。"""
    from backend import config as cfg
    monkeypatch.setattr(cfg, "SETTINGS_FILE", tmp_path / "settings.json")
    import app
    api = app.Api()

    hit = api.playback_command("下一首")
    assert hit["ok"] is True and hit["action"] == "next" and hit["say"]

    miss = api.playback_command("你觉得这首歌怎么样")
    assert miss["ok"] is True and miss["action"] is None


@pytest.mark.parametrize("text", [
    "",
    "   ",
    "我不想听下一首这种歌",            # 含"下一首"但是真心话 → 绝不拦
    "下一首歌的歌词是什么意思",        # 在问问题，不是命令
    "放点周杰伦的歌",                  # 点歌，交给 DeepSeek
    "给我来点轻音乐",                  # 点歌
    "你觉得这首歌怎么样",
    "聊聊今天有什么新闻",
    "讲个笑话吧",
    "继续给我讲讲刚才那个故事",         # 含"继续"但是对话
    "停车场在哪里",                    # 含"停"但无关
])
def test_non_command_passes_through(text):
    assert commands.match_playback(text) is None, f"不该被当成播放命令: {text!r}"
