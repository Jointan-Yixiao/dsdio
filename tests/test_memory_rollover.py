"""rollover：归并失败时绝不丢当天短期记忆（与「宁可不归并，也不丢数据进黑洞」的承诺一致）。

- 归并失败（断网 / 临时丢 key）→ 保留 stale 短期记忆、不重置，下次启动可重试。
- 归并成功 → 正常融进长期记忆并重置当天（happy path 不被破坏）。
"""
import json

from backend import memory


def _seed_stale(short_path):
    short_path.write_text(json.dumps({
        "date": "2000-01-01", "mood": "tired", "activities": ["coding all day"],
        "music": [], "chat_notes": "quiet"}), "utf-8")


def test_rollover_keeps_day_data_when_merge_fails(monkeypatch, tmp_path):
    short = tmp_path / "short.json"
    monkeypatch.setattr(memory, "SHORT_FILE", short)
    monkeypatch.setattr(memory, "LONG_FILE", tmp_path / "long.json")
    _seed_stale(short)

    def boom(long_data, short_data):
        raise RuntimeError("no api key / network down")
    monkeypatch.setattr(memory, "_summarize_into_long", boom)

    did = memory.rollover()

    assert did is False                                  # 没成功归并
    s = json.loads(short.read_text("utf-8"))
    assert s["mood"] == "tired"                          # 当天数据保住，没被冲空
    assert s["activities"] == ["coding all day"]
    assert s["date"] == "2000-01-01"                     # 仍是旧日期，下次启动重试归并


def test_rollover_merges_and_resets_on_success(monkeypatch, tmp_path):
    short = tmp_path / "short.json"
    long = tmp_path / "long.json"
    monkeypatch.setattr(memory, "SHORT_FILE", short)
    monkeypatch.setattr(memory, "LONG_FILE", long)
    _seed_stale(short)
    monkeypatch.setattr(memory, "_summarize_into_long",
                        lambda l, s: dict(memory._LONG_DEFAULT, genres=["lofi"]))

    did = memory.rollover()

    assert did is True
    s = json.loads(short.read_text("utf-8"))
    assert s["mood"] == ""                               # 成功归并后正常重置当天
    assert s["date"] == memory._today()
    assert "lofi" in json.loads(long.read_text("utf-8"))["genres"]   # 归并结果落盘
