"""Opt11: TTS 合成并行管线。

_SentencePipeline 让句子的 TTS 合成在线程池里并行跑（不再卡住 DeepSeek 流的消费），
但推给前端时严格按 idx 顺序 —— 既不阻塞流式生成，又不打乱播放次序。
"""
import threading
import time

import app


def test_pipeline_pushes_in_order_and_synth_runs_parallel():
    push_order = []

    def synth(text):
        time.sleep(0.05)                 # 模拟合成耗时
        return (f"voice:{text}", [{"w": text}])

    def push(idx, text, voice, words):
        push_order.append((idx, text, voice))

    p = app._SentencePipeline(synth, push, max_workers=3)
    t0 = time.time()
    for i, seg in enumerate(["a", "b", "c"]):
        p.submit(i, seg)                 # 提交不应阻塞在合成上
    submit_elapsed = time.time() - t0
    p.close()
    total_elapsed = time.time() - t0

    assert [x[0] for x in push_order] == [0, 1, 2]            # 按 idx 顺序推送
    assert [x[1] for x in push_order] == ["a", "b", "c"]
    assert [x[2] for x in push_order] == ["voice:a", "voice:b", "voice:c"]
    assert submit_elapsed < 0.03                              # 提交不等合成
    assert total_elapsed < 0.12                              # 3×50ms 串行=150ms；并行应明显更短


def test_pipeline_push_order_holds_when_later_synth_finishes_first():
    # 第 0 句合成最慢，仍必须最先推送（顺序由 idx 决定，不由完成先后决定）
    push_order = []
    delays = {"a": 0.08, "b": 0.01, "c": 0.01}

    def synth(text):
        time.sleep(delays[text])
        return (f"v:{text}", [])

    def push(idx, text, voice, words):
        push_order.append(idx)

    p = app._SentencePipeline(synth, push, max_workers=3)
    for i, seg in enumerate(["a", "b", "c"]):
        p.submit(i, seg)
    p.close()
    assert push_order == [0, 1, 2]


def test_pipeline_synth_failure_does_not_break_order():
    push_order = []

    def synth(text):
        if text == "b":
            raise RuntimeError("synth boom")
        return (f"v:{text}", [])

    def push(idx, text, voice, words):
        push_order.append((idx, voice))

    p = app._SentencePipeline(synth, push, max_workers=3)
    for i, seg in enumerate(["a", "b", "c"]):
        p.submit(i, seg)
    p.close()
    # 失败的句子也按序推送（空语音兜底），不卡死后续
    assert [x[0] for x in push_order] == [0, 1, 2]
    assert push_order[1][1] == ""        # b 合成失败 → 空 voice
