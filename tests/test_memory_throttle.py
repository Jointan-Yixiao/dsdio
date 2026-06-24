"""Opt9: 记忆提炼每 10 轮节流。

observe() 每轮只做廉价的入缓冲；攒够 10 轮才真正发一次 DeepSeek 提炼，
且这一次把 10 轮全部喂进去（不丢信号）。把每条消息额外一次 API 调用降到每 10 条一次。
"""
from backend import memory


def test_observe_runs_only_every_10_turns(monkeypatch):
    calls = []
    monkeypatch.setattr(memory, "_run_observe", lambda batch: calls.append(len(batch)))
    memory._turn_buffer.clear()

    for i in range(9):
        assert memory.observe([], f"u{i}", f"r{i}") is False
    assert calls == []                       # 前 9 轮不提炼

    assert memory.observe([], "u9", "r9") is True
    assert calls == [10]                      # 第 10 轮提炼一次，含全部 10 轮


def test_observe_buffer_resets_after_extraction(monkeypatch):
    calls = []
    monkeypatch.setattr(memory, "_run_observe", lambda batch: calls.append(len(batch)))
    memory._turn_buffer.clear()

    for i in range(20):
        memory.observe([], f"u{i}", f"r{i}")
    assert calls == [10, 10]                   # 第 10、第 20 轮各提炼一次
