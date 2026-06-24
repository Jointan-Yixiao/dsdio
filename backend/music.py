"""网易云音乐客户端：调用本地 NeteaseCloudMusicApi（Node 服务）搜索并取可播放地址。

灰色/VIP 歌网易云没免费地址时，转交本地 UNM 服务（@unblockneteasemusic/server）从酷我/QQ/
咪咕/B站/pyncmd 等源找回原版可播放地址 —— 免登录、免风控，等效拿到完整曲库。"""
from __future__ import annotations

import json
import random
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import config

# 免登录时用来「随便放点」的关键词（这些类目可免登录播放的比例较高）
FILLER_KEYWORDS = ["纯音乐", "轻音乐", "钢琴", "白噪音", "民谣", "爵士", "lo-fi 中文"]


class MusicError(Exception):
    pass


def _get(path: str, timeout: int = 15, **params) -> dict:
    url = config.NCM_BASE + path + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # 网易云接口常用「非 200 状态码 + JSON body」返回错误（验证码错误/风控/频率限制等），
        # urlopen 默认直接抛异常，这里把 body 读出来解析，拿到真实的 code/message。
        try:
            return json.loads(e.read().decode("utf-8", "ignore"))
        except Exception:
            raise e


def is_up(timeout: int = 2) -> bool:
    try:
        urllib.request.urlopen(config.NCM_BASE, timeout=timeout)
        return True
    except Exception:
        return False


def _track(x: dict, url: str, unlocked: bool = False, source: str = "") -> dict:
    al = x.get("al") or x.get("album") or {}
    ar = x.get("ar") or x.get("artists") or []
    return {
        "id": x["id"],
        "name": x.get("name", ""),
        "artist": "、".join(a.get("name", "") for a in ar) or "Unknown",
        "album": al.get("name", ""),
        "cover": al.get("picUrl", ""),
        "duration": x.get("dt", 0) or x.get("duration", 0),
        "url": url,
        "unlocked": unlocked,   # 是否经 UNM 从其它源解锁
        "source": source,       # 解锁来源（kuwo/pyncmd/…），免费曲为空
    }


def unm_match(song_id) -> tuple[str, str]:
    """调本地 UNM 服务，给网易云歌曲 id 找回可播放地址。返回 (url, source)，失败返回 ("","")。"""
    try:
        url = config.UNM_BASE + "/match?" + urllib.parse.urlencode({"id": song_id})
        with urllib.request.urlopen(url, timeout=8) as r:
            d = json.load(r)
        return (d.get("url") or "", d.get("source") or "") if d.get("ok") else ("", "")
    except Exception:
        return "", ""


def _attach_urls(songs: list[dict], limit: int) -> list[dict]:
    """给搜索结果取播放地址：网易云有免费地址的直接用，没有的（VIP/灰色）交给 UNM 解锁。
    保持搜索相关性顺序；UNM 解锁并发执行、限量、带超时，避免拖慢。"""
    if not songs:
        return []
    songs = songs[: max(limit * 2, 12)]  # 只考虑前若干条，省得给一长串都去解锁
    params = {"id": ",".join(str(x["id"]) for x in songs), "level": "standard"}
    try:
        u = _get("/song/url/v1", **params)
    except Exception as e:
        raise MusicError(f"取播放地址失败：{e}") from e
    url_map = {d["id"]: d.get("url") for d in u.get("data", [])}

    results: list[dict | None] = [None] * len(songs)
    locked: list[int] = []
    for i, x in enumerate(songs):
        free = url_map.get(x["id"])
        if free:
            results[i] = _track(x, free)
        else:
            locked.append(i)

    # 不够 limit 就用 UNM 解锁被锁的（按相关性优先解前面的，限量 + 并发）
    have = sum(1 for r in results if r)
    if have < limit and locked:
        attempt = locked[: (limit - have) + 1]  # 多解 1 首兜底失败，别解太多拖慢
        with ThreadPoolExecutor(max_workers=8) as ex:  # 一波并发解完
            futs = {ex.submit(unm_match, songs[i]["id"]): i for i in attempt}
            for f in as_completed(futs):
                i = futs[f]
                url, src = f.result()
                if url:
                    results[i] = _track(songs[i], url, unlocked=True, source=src)

    out = [r for r in results if r]
    return out[:limit]


def search_playable(keywords: str, limit: int = 10) -> list[dict]:
    """搜索并返回可播放的曲目列表（免登录：免费地址直接用，被锁的交 UNM 解锁）。"""
    if not keywords:
        keywords = random.choice(FILLER_KEYWORDS)
    try:
        s = _get("/cloudsearch", keywords=keywords, limit=max(limit * 2, 20), type=1)
    except Exception as e:
        raise MusicError(f"搜索失败（音乐服务在线吗？）：{e}") from e
    songs = (s.get("result") or {}).get("songs") or []
    return _attach_urls(songs, limit)


def _search_raw(keywords: str, limit: int):
    """搜索 + 批量取网易云免费地址。返回 (songs, url_map)。"""
    if not keywords:
        keywords = random.choice(FILLER_KEYWORDS)
    try:
        s = _get("/cloudsearch", keywords=keywords, limit=max(limit * 2, 20), type=1)
    except Exception as e:
        raise MusicError(f"搜索失败（音乐服务在线吗？）：{e}") from e
    songs = ((s.get("result") or {}).get("songs") or [])[: max(limit * 2, 12)]
    if not songs:
        return [], {}
    params = {"id": ",".join(str(x["id"]) for x in songs), "level": "standard"}
    try:
        u = _get("/song/url/v1", **params)
    except Exception as e:
        raise MusicError(f"取播放地址失败：{e}") from e
    return songs, {d["id"]: d.get("url") for d in u.get("data", [])}


def search_split(keywords: str, limit: int = 12):
    """快路径：返回 (ready, pending)。ready 保持搜索相关性顺序、立刻可播；只为"头部第一首被锁的歌"
    即时解锁一次以定下 track[0]，其余被锁的歌作为 pending 交后台慢慢解，让点歌近乎秒起。"""
    songs, url_map = _search_raw(keywords, limit)
    if not songs:
        return [], []
    ready: list[dict] = []
    pending: list[dict] = []
    first_unlock_done = False
    for x in songs:
        free = url_map.get(x["id"])
        if free:
            ready.append(_track(x, free))
        elif not first_unlock_done:
            first_unlock_done = True          # 头部被锁：立刻解锁一次，定下最相关的 track[0]
            url, src = unm_match(x["id"])
            if url:
                ready.append(_track(x, url, unlocked=True, source=src))
            else:
                pending.append(x)
        else:
            pending.append(x)
    if not ready:                              # 一首都没有就多试两首兜底
        for x in list(pending):
            url, src = unm_match(x["id"])
            if url:
                ready.append(_track(x, url, unlocked=True, source=src))
                pending.remove(x)
                break
    return ready[:limit], pending


def resolve_pending(songs: list[dict], max_n: int = 12):
    """后台并发解锁 pending 里被锁的歌，成功的逐首产出（按完成先后）。"""
    songs = (songs or [])[:max_n]
    if not songs:
        return
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(unm_match, x["id"]): x for x in songs}
        for f in as_completed(futs):
            x = futs[f]
            url, src = f.result()
            if url:
                yield _track(x, url, unlocked=True, source=src)


def something(limit: int = 12) -> list[dict]:
    """随便来点能放的（用于「放点音乐」这类泛请求）。"""
    random.shuffle(FILLER_KEYWORDS)
    for kw in FILLER_KEYWORDS:
        tracks = search_playable(kw, limit)
        if tracks:
            return tracks
    return []
