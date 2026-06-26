"""Bug1: 新闻跨过期点自动重抓。

cached_items():
- 有未过期且非空的缓存 → 直接返回，不重抓。
- 缓存过期 / 为空 → 触发一次后台重抓（去重），同时把现有(可能已过期)的条目当兜底返回。
"""
import time

from backend import news


def setup_function(_):
    news._cache.clear()
    news._refreshing = False


def test_returns_fresh_cache_without_refetch():
    now = time.time()
    news._cache[("k",)] = (now + 1000, (["fresh"], []))
    calls = []
    items = news.cached_items(refresher=lambda: calls.append(1), spawn=lambda fn: fn())
    assert items == ["fresh"]
    assert calls == []          # 新鲜缓存不该触发重抓


def test_refetches_when_expired_and_returns_stopgap():
    now = time.time()
    news._cache[("k",)] = (now - 10, (["stale"], []))   # 已过期
    calls = []
    items = news.cached_items(refresher=lambda: calls.append(1), spawn=lambda fn: fn())
    assert calls == [1]         # 过期 → 触发重抓
    assert items == ["stale"]   # 重抓完成前先用旧条目兜底


def test_refetches_when_cache_empty():
    calls = []
    items = news.cached_items(refresher=lambda: calls.append(1), spawn=lambda fn: fn())
    assert calls == [1]         # 空缓存 → 触发重抓
    assert items == []          # 没有任何兜底条目


def test_refetch_is_deduped_while_in_flight():
    # spawn 只记录不执行 → _refreshing 保持 True，模拟重抓仍在进行
    spawned = []
    spawn = lambda fn: spawned.append(fn)
    news.cached_items(refresher=lambda: None, spawn=spawn)
    news.cached_items(refresher=lambda: None, spawn=spawn)
    assert len(spawned) == 1    # 第二次调用被去重，不重复起线程


def test_cached_empty_does_not_block_refetch(monkeypatch):
    """全网失败缓存了空结果后，未到过期点也应忽略空缓存重抓——否则自愈被废、新闻空到次日5点。"""
    monkeypatch.setattr(news, "fetch_feed", lambda feed, fresh: [])
    first, _ = news.fetch_all()
    assert first == []                                   # 全失败 → 缓存了空结果（未过期）
    monkeypatch.setattr(news, "fetch_feed", lambda feed, fresh: [
        {"title": f"T-{feed['name']}", "summary": "", "link": "", "source": feed["name"],
         "category": feed["category"], "region": feed["region"], "lang": "en",
         "published": None, "_ts": 0}])
    second, _ = news.fetch_all()
    assert second, "空缓存不应屏蔽重抓——网络恢复后应抓到新条目"
