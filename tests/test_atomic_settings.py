"""Bug5: 配置/记忆文件原子写 + 并发加锁。

- 并发 save_settings 不丢更新（read-modify-write 临界区被锁串行化）。
- 写入中途失败时，原文件完好、不留半截内容；临时文件清理掉。
"""
import threading
import time

from backend import config, memory


def test_concurrent_saves_do_not_lose_updates(tmp_path, monkeypatch):
    f = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_FILE", f)
    config.save_settings({})  # 建初始文件

    # 让 load 变慢：无锁时所有线程都先读到初始态再各自写 → 互相覆盖（确定性暴露竞态）。
    real_load = config.load_settings
    def slow_load():
        time.sleep(0.03)
        return real_load()
    monkeypatch.setattr(config, "load_settings", slow_load)

    keys = [f"k{i}" for i in range(20)]
    barrier = threading.Barrier(len(keys))
    def worker(k):
        barrier.wait()
        config.save_settings({k: 1})
    threads = [threading.Thread(target=worker, args=(k,)) for k in keys]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    data = real_load()
    missing = [k for k in keys if data.get(k) != 1]
    assert not missing, f"并发丢了这些键: {missing}"


def test_save_settings_keeps_original_on_write_failure(tmp_path, monkeypatch):
    f = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_FILE", f)
    config.save_settings({"persona": "good"})
    original = f.read_text("utf-8")

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(config.os, "replace", boom)
    try:
        config.save_settings({"persona": "bad"})
    except OSError:
        pass

    assert f.read_text("utf-8") == original           # 原文件未被破坏
    assert not (tmp_path / "settings.json.tmp").exists()  # 临时文件清掉了


def test_memory_write_keeps_original_on_failure(tmp_path, monkeypatch):
    f = tmp_path / "long_memory.json"
    memory._write(f, {"a": 1})
    original = f.read_text("utf-8")

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(config.os, "replace", boom)
    try:
        memory._write(f, {"a": 999})
    except OSError:
        pass

    assert f.read_text("utf-8") == original
    assert not (tmp_path / "long_memory.json.tmp").exists()
