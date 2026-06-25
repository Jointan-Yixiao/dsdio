"""语言一致性：无论用户/新闻用什么语言，Dsdio 回复必须是英文。

埋在长系统提示词中间的一句英文-only 指令，会被 DeepSeek 的"语言镜像"先验、结尾的
中文 user 消息、以及中文新闻标题盖过。修复：在拼好的 messages 末尾、最后一条 user
消息之后，再追加一条强约束语言指令（近因位），把语言锁死成英文。
"""
from backend import host


class _FakeClient:
    """捕获传给 chat.completions.create 的 messages；create 返回空流。"""

    def __init__(self, capture):
        self._capture = capture
        self.chat = self
        self.completions = self

    def create(self, *, model, messages, **kwargs):
        self._capture["messages"] = messages
        return iter([])


def test_stream_reply_appends_english_directive_after_user(monkeypatch):
    capture = {}
    monkeypatch.setattr(host, "_client", lambda: _FakeClient(capture))

    list(host.stream_reply(
        history=[{"role": "assistant", "content": "你好"}],
        user_text="你好，放点音乐",
        news_digest="- [news] 某中文标题 (某源)",
    ))

    messages = capture["messages"]
    last = messages[-1]
    # 末尾必须是一条强约束英文指令（system）
    assert last["role"] == "system"
    assert "english" in last["content"].lower()
    # 且位于最后一条 user 消息之后（近因），否则会被中文上下文/历史盖过
    user_indices = [i for i, m in enumerate(messages) if m["role"] == "user"]
    assert user_indices and user_indices[-1] < len(messages) - 1
