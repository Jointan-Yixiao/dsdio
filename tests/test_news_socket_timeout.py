"""Bug4: fetch_feed 不该污染进程全局 socket 默认超时。

原实现 socket.setdefaulttimeout(timeout) 改的是全局默认，抓完新闻后所有后续未显式
设超时的网络调用都被钉死。修复后：调用前后全局默认不变。
"""
import socket

from backend import news


def test_fetch_feed_restores_global_socket_timeout(monkeypatch):
    # feedparser.parse 不联网：返回一个没有条目的假对象
    class _Fake:
        entries = []
    monkeypatch.setattr(news.feedparser, "parse", lambda *a, **k: _Fake())

    socket.setdefaulttimeout(None)              # 已知初始状态
    feed = {"name": "x", "url": "http://x", "category": "Tech", "region": "intl"}
    news.fetch_feed(feed, fresh_hours=24, timeout=7)

    assert socket.getdefaulttimeout() is None   # 全局默认不被污染


def test_fetch_feed_restores_preexisting_timeout(monkeypatch):
    class _Fake:
        entries = []
    monkeypatch.setattr(news.feedparser, "parse", lambda *a, **k: _Fake())

    socket.setdefaulttimeout(3.0)               # 之前已有人设过
    try:
        feed = {"name": "x", "url": "http://x", "category": "Tech", "region": "intl"}
        news.fetch_feed(feed, fresh_hours=24, timeout=7)
        assert socket.getdefaulttimeout() == 3.0  # 还原成原值，而非 7
    finally:
        socket.setdefaulttimeout(None)
