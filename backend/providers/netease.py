# backend/providers/netease.py
"""网易云音源 adapter：接用户自部署的 NeteaseCloudMusicApi 兼容服务（Enhanced 或 fork）。

只此一处懂网易云路由方言（/cloudsearch, /song/url, /song/url/match）。取址+解锁收口于
_play_url：免费全曲直用；VIP 试听片段或空地址 → 后端自带 /song/url/match 找回完整地址。
"""
from __future__ import annotations

import json
import random
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from .. import config
from .base import ProviderError, normalize_track


class NeteaseProvider:
    prefix = "ncm"
    provider_id = "netease-enhanced"

    # ---- HTTP 接缝 ----
    def _get(self, path: str, timeout: int = 15, **params) -> dict:
        base = config.MUSIC_API_BASE
        if not base:
            raise ProviderError("UNAVAILABLE", self.provider_id, "未配置 MUSIC_API_BASE")
        url = base + path + "?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8", "ignore"))
            except Exception:
                raise ProviderError("NETWORK", self.provider_id, f"HTTP {e.code}") from e
        except Exception as e:
            raise ProviderError("NETWORK", self.provider_id, str(e)) from e

    def is_up(self, timeout: float = 2) -> bool:
        base = config.MUSIC_API_BASE
        if not base:
            return False
        try:
            urllib.request.urlopen(base, timeout=timeout)
            return True
        except Exception:
            return False

    # ---- 取址 + 解锁 ----
    @staticmethod
    def _is_full(row: dict) -> bool:
        """/song/url 单曲响应是否为“完整可播”：有地址且非试听片段。"""
        if not row.get("url"):
            return False
        return not row.get("freeTrialInfo")   # 有试听信息 = 30s 片段，非完整歌

    def _unlock(self, raw_id) -> str:
        """打后端自带解锁 /song/url/match（不传 source），返回完整地址或 ""。"""
        try:
            d = self._get("/song/url/match", timeout=8, id=raw_id)
        except ProviderError:
            return ""
        u = d.get("data")
        return u if isinstance(u, str) and u.startswith("http") else ""

    # ---- 搜索 ----
    def _search_songs(self, keywords: str, limit: int, timeout: int) -> list[dict]:
        if not keywords:
            keywords = random.choice(config.FILLER_KEYWORDS)
        try:
            s = self._get("/cloudsearch", timeout=timeout,
                          keywords=keywords, limit=max(limit * 2, 20), type=1)
        except ProviderError as e:
            raise ProviderError(e.code, self.provider_id, f"搜索失败：{e}") from e
        songs = [x for x in ((s.get("result") or {}).get("songs") or []) if x.get("id") is not None]
        return songs[: max(limit * 2, 12)]

    def _url_rows(self, songs: list[dict], timeout: int) -> dict:
        params = {"id": ",".join(str(x["id"]) for x in songs)}
        try:
            u = self._get("/song/url", timeout=timeout, **params)
        except ProviderError as e:
            raise ProviderError(e.code, self.provider_id, f"取址失败：{e}") from e
        return {d["id"]: d for d in u.get("data", [])}

    def search(self, keywords: str, limit: int = 10) -> list[dict]:
        """开机铺垫：宽超时；完整免费直用，试听/空地址并发解锁。"""
        songs = self._search_songs(keywords, limit, timeout=15)
        if not songs:
            return []
        rows = self._url_rows(songs, timeout=15)
        results: list[dict | None] = [None] * len(songs)
        locked: list[int] = []
        for i, x in enumerate(songs):
            row = rows.get(x["id"]) or {}
            if self._is_full(row):
                results[i] = normalize_track(self.prefix, x, row["url"])
            else:
                locked.append(i)
        have = sum(1 for r in results if r)
        if have < limit and locked:
            attempt = locked[: (limit - have) + 1]
            with ThreadPoolExecutor(max_workers=8) as ex:
                futs = {ex.submit(self._unlock, songs[i]["id"]): i for i in attempt}
                for f in as_completed(futs):
                    i = futs[f]
                    url = f.result()
                    if url:
                        results[i] = normalize_track(self.prefix, songs[i], url, unlocked=True)
        return [r for r in results if r][:limit]

    def search_split(self, keywords: str, limit: int = 12, timeout: int = 8):
        """交互点歌快路径：ready 立即可播；头部被锁即时解一次定 track[0]，其余留 pending。"""
        songs = self._search_songs(keywords, limit, timeout=timeout)
        if not songs:
            return [], []
        rows = self._url_rows(songs, timeout=timeout)
        ready: list[dict] = []
        pending: list[dict] = []
        first_unlock_done = False
        for x in songs:
            row = rows.get(x["id"]) or {}
            if self._is_full(row):
                ready.append(normalize_track(self.prefix, x, row["url"]))
            elif not first_unlock_done:
                first_unlock_done = True
                url = self._unlock(x["id"])
                if url:
                    ready.append(normalize_track(self.prefix, x, url, unlocked=True))
                else:
                    pending.append(x)
            else:
                pending.append(x)
        if not ready:
            for x in list(pending):
                url = self._unlock(x["id"])
                if url:
                    ready.append(normalize_track(self.prefix, x, url, unlocked=True))
                    pending.remove(x)
                    break
        return ready[:limit], pending

    def resolve_pending(self, pending: list[dict], max_n: int = 12):
        """后台并发解锁 pending 里的原始歌曲对象，成功的逐首 yield（归一化 track）。"""
        songs = (pending or [])[:max_n]
        if not songs:
            return
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(self._unlock, x["id"]): x for x in songs}
            for f in as_completed(futs):
                x = futs[f]
                url = f.result()
                if url:
                    yield normalize_track(self.prefix, x, url, unlocked=True)
