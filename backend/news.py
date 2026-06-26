"""新闻抓取：从配置的 RSS 源拉取条目，清洗、按时间过滤、去重、归类。"""
from __future__ import annotations

import calendar
import html
import re
import socket
import threading
import time
from datetime import datetime, timedelta, timezone

import feedparser

from . import config

# 新闻抓取结果内存缓存：缓存到「次日早上 5 点」，每天过了 5 点的首次请求才重抓。
_cache: dict = {}

# 后台重抓的并发去重标志（避免一旦过期、多次 cached_items 各起一个抓取线程）。
_refreshing = False
_refresh_lock = threading.Lock()


def _expiry_5am(now: float) -> float:
    dt = datetime.fromtimestamp(now)
    five = dt.replace(hour=5, minute=0, second=0, microsecond=0)
    if dt >= five:
        five += timedelta(days=1)
    return five.timestamp()

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# feedparser 走 urllib，会自动读取 Windows 系统代理；这里设个 UA 和默认超时。
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NightRadio/1.0"


def _clean(text: str) -> str:
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _entry_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return None


def fetch_feed(feed: dict, fresh_hours: int, timeout: int = 12) -> list[dict]:
    """抓单个源，失败/超时返回空列表（不抛异常）。"""
    # feedparser 走 urllib，没有 per-request 超时入口，只能借全局默认；用完务必还原，
    # 否则会把这个超时永久泄漏给进程里所有其它网络调用（DeepSeek/网易云等）。
    prev_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        parsed = feedparser.parse(feed["url"], agent=_UA)
    except Exception:
        return []
    finally:
        socket.setdefaulttimeout(prev_timeout)

    now = datetime.now(timezone.utc)
    items: list[dict] = []
    for e in parsed.entries:
        title = _clean(e.get("title", ""))
        if not title:
            continue
        published = _entry_time(e)
        if published is not None and fresh_hours > 0:
            age_h = (now - published).total_seconds() / 3600
            if age_h > fresh_hours or age_h < -6:  # 太旧或时间异常（未来）跳过
                continue
        summary = _clean(e.get("summary", "") or e.get("description", ""))
        items.append(
            {
                "title": title,
                "summary": summary[:400],
                "link": e.get("link", ""),
                "source": feed["name"],
                "category": feed["category"],
                "region": feed["region"],
                "lang": "zh" if feed["region"] == "cn" else "en",
                "published": published.isoformat() if published else None,
                "_ts": published.timestamp() if published else 0,
            }
        )
    return items


def _norm_title(t: str) -> str:
    return re.sub(r"[\s\W_]+", "", t.lower())


def fetch_all(categories: list[str] | None = None, fresh_hours: int | None = None,
              per_feed_limit: int = 12, total_limit: int = 60,
              use_cache: bool = True) -> tuple[list[dict], list[str]]:
    """抓取所有匹配分类的源。返回 (候选条目, 失败的源名列表)。10 分钟内命中缓存直接返回。"""
    if fresh_hours is None:
        fresh_hours = config.NEWS_FRESH_HOURS
    cats = set(categories) if categories else set(config.CATEGORIES)

    cache_key = (tuple(sorted(cats)), fresh_hours, per_feed_limit, total_limit)
    now = time.time()
    if use_cache:
        hit = _cache.get(cache_key)
        # 仅复用「未过期且非空」的缓存；空结果（曾全网失败）绝不屏蔽重抓，否则自愈被废、
        # 新闻会一直空到次日 5 点。hit[1] = (results, failed)，hit[1][0] 即条目列表。
        if hit and now < hit[0] and hit[1][0]:
            return hit[1]

    seen: set[str] = set()
    results: list[dict] = []
    failed: list[str] = []

    for feed in config.FEEDS:
        if feed["category"] not in cats:
            continue
        items = fetch_feed(feed, fresh_hours)
        if not items:
            failed.append(feed["name"])
            continue
        kept = 0
        for it in items:
            key = _norm_title(it["title"])
            if not key or key in seen:
                continue
            seen.add(key)
            results.append(it)
            kept += 1
            if kept >= per_feed_limit:
                break

    # 最新的排前面，截断总量控制给 LLM 的 token
    results.sort(key=lambda x: x["_ts"], reverse=True)
    out = (results[:total_limit], failed)
    _cache[cache_key] = (_expiry_5am(now), out)
    return out


def _spawn_refresh(fn) -> None:
    threading.Thread(target=fn, daemon=True).start()


def _kick_refresh(refresher, spawn) -> bool:
    """去重地后台跑一次重抓：已有重抓在进行就跳过。返回是否真的起了一次。"""
    global _refreshing
    with _refresh_lock:
        if _refreshing:
            return False
        _refreshing = True

    def run():
        global _refreshing
        try:
            refresher()
        finally:
            with _refresh_lock:
                _refreshing = False

    spawn(run)
    return True


def cached_items(refresher=None, spawn=None) -> list[dict]:
    """返回缓存里的新闻条目。
    - 有未过期且非空的缓存 → 直接返回。
    - 过期 / 为空 → 触发一次后台重抓（去重，不阻塞调用方），同时返回现有(可能已过期)
      条目兜底；什么都没有就返回空列表。这样长期挂着的挂件跨过 5 点也能自愈，不再永久空。
    """
    now = time.time()
    newest_items: list[dict] = []
    newest_expiry = -1.0
    for expiry, (items, _failed) in _cache.values():
        if now < expiry and items:
            return items                       # 新鲜缓存：直接用，不重抓
        if expiry > newest_expiry:
            newest_expiry, newest_items = expiry, items
    _kick_refresh(refresher or fetch_all, spawn or _spawn_refresh)
    return newest_items


def digest(items: list[dict], n: int = 24) -> str:
    """把头条压成一小段给模型当上下文。"""
    return "\n".join(
        f"- [{it.get('category','')}] {it.get('title','')} ({it.get('source','')})"
        for it in items[:n]
    )
