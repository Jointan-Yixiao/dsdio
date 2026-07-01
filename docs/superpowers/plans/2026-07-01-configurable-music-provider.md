# 可配置音源 provider 层 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把网易云 Node/UNM 代码物料清出公开仓，音源改为用户自部署 + `.env` 注入 `MUSIC_API_BASE`，播放器经薄 provider 层解耦、预留多源。

**Architecture:** 新增 `backend/providers/`（base 契约 + registry 前缀路由 + netease adapter），`backend/music.py` 降为委托当前 provider 的薄门面（对外函数签名不变，`app.py`/前端零改动）。取址+解锁收口于 netease adapter：免费全曲直用；**VIP 试听片段或空地址** → 后端自带 `/song/url/match` 找回完整地址。

**Tech Stack:** Python 3.10+、stdlib（urllib/concurrent.futures）、pytest。无新增第三方依赖。

## Global Constraints

- **公开仓零 NCM/UNM 代码物料**：不 import、不作依赖、`package.json` 不出现 `NeteaseCloudMusicApi*` / `@neteasecloudmusicapienhanced/*` / `@unblockneteasemusic/*`。
- **零硬编码后端地址**：`MUSIC_API_BASE` 由 `.env` 注入，无默认；留空则点歌不可用，聊天/新闻照常降级。
- **TDD 强制**：先写失败测试再实现（含 GUI 接缝 mock）。
- **原子写配置**：沿用 `config.atomic_write_text`（本计划不改 settings 写盘路径）。
- **`.bat` 含中文必须存 GBK/cp936**，有 `tests/test_bat_encoding.py` 守卫。
- **provider js_api 无关**：本计划不动 pywebview 桥；`Api` 内部属性仍 `_` 前缀。
- **id 带 provider 前缀**：归一化 track 的 `id` 形如 `"ncm:123"`；前端仅用它做去重（`app.js:530`），字符串前缀安全。

**衔接上一轮未提交改动**：工作区已有上一轮把 `music-api` 换 Enhanced、`music.py` 切 `/song/url`、改测试等改动（均未提交）。本计划在其之上继续：`music.py` 的 `/song/url` 逻辑迁入 netease adapter（保留）；`music-api/`+`unm-api/` 目录被 `git rm --cached` 移出仓库（本地保留作可选 spawn 目录）；`tests/test_music_source_enhanced.py` 换向为版权守卫。

---

## Task 1: providers/base.py — 归一化模型 + id 前缀 + 错误 + Protocol

**Files:**
- Create: `backend/providers/__init__.py`（本任务先留空占位，Task 5 再装配）
- Create: `backend/providers/base.py`
- Test: `tests/test_providers_base.py`

**Interfaces:**
- Produces: `pack_id(prefix:str, raw_id)->str`、`unpack_id(track_id:str)->tuple[str,str]`、`normalize_track(prefix:str, x:dict, url:str, unlocked:bool=False, source:str="")->dict`、`ProviderError(code:str, provider_id:str, message:str)`、`MusicProvider`(Protocol，属性 `prefix:str`，方法 `is_up/search/search_split/resolve_pending`)。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_providers_base.py
import pytest
from backend.providers import base


def test_pack_unpack_roundtrip():
    tid = base.pack_id("ncm", 123)
    assert tid == "ncm:123"
    assert base.unpack_id(tid) == ("ncm", "123")


def test_unpack_without_prefix_raises():
    with pytest.raises(ValueError):
        base.unpack_id("123")


def test_normalize_track_shape_and_prefixed_id():
    x = {"id": 7, "name": "A", "ar": [{"name": "x"}], "al": {"name": "Al", "picUrl": "c"}, "dt": 1000}
    t = base.normalize_track("ncm", x, "http://u", unlocked=True, source="")
    assert t["id"] == "ncm:7"
    assert t["name"] == "A" and t["artist"] == "x" and t["album"] == "Al"
    assert t["cover"] == "c" and t["duration"] == 1000
    assert t["url"] == "http://u" and t["unlocked"] is True and t["source"] == ""


def test_provider_error_attrs():
    e = base.ProviderError("NETWORK", "netease-enhanced", "boom")
    assert e.code == "NETWORK" and e.provider_id == "netease-enhanced"
    assert "boom" in str(e)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python -m pytest tests/test_providers_base.py -q`
Expected: FAIL（`ModuleNotFoundError: backend.providers` 或 `base` 不存在）

- [ ] **Step 3: 建空 `backend/providers/__init__.py`**

```python
# backend/providers/__init__.py
# 音源 provider 层：Task 5 在此装配 registry。
```

- [ ] **Step 4: 写 `backend/providers/base.py`**

```python
# backend/providers/base.py
"""音源 provider 契约：归一化模型 + id 前缀 + 错误模型。

播放器只依赖这里的接口与归一化 dict，不感知任何具体音源后端。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


class ProviderError(Exception):
    """provider 对外统一错误；禁止让原始 urllib/HTTP 错误冒泡到上层。"""

    def __init__(self, code: str, provider_id: str, message: str):
        super().__init__(message)
        self.code = code            # NETWORK / NOT_FOUND / UNAVAILABLE / UNKNOWN
        self.provider_id = provider_id


def pack_id(prefix: str, raw_id) -> str:
    """把某音源的原始 id 打成带前缀的全局 id，如 pack_id('ncm', 123) -> 'ncm:123'。"""
    return f"{prefix}:{raw_id}"


def unpack_id(track_id: str) -> tuple[str, str]:
    """拆分带前缀 id，返回 (prefix, raw_id)；缺前缀抛 ValueError。"""
    prefix, sep, raw = track_id.partition(":")
    if not sep:
        raise ValueError(f"id 缺 provider 前缀: {track_id!r}")
    return prefix, raw


def normalize_track(prefix: str, x: dict, url: str,
                    unlocked: bool = False, source: str = "") -> dict:
    """把某音源的原始歌曲对象归一化成统一 track dict（id 带前缀）。"""
    al = x.get("al") or x.get("album") or {}
    ar = x.get("ar") or x.get("artists") or []
    return {
        "id": pack_id(prefix, x["id"]),
        "name": x.get("name", ""),
        "artist": "、".join(a.get("name", "") for a in ar) or "Unknown",
        "album": al.get("name", ""),
        "cover": al.get("picUrl", ""),
        "duration": x.get("dt", 0) or x.get("duration", 0),
        "url": url,
        "unlocked": unlocked,   # 是否经后端解锁找回
        "source": source,       # 解锁来源；后端不回传时为空
    }


@runtime_checkable
class MusicProvider(Protocol):
    prefix: str

    def is_up(self, timeout: float = 2) -> bool: ...
    def search(self, keywords: str, limit: int) -> list[dict]: ...
    def search_split(self, keywords: str, limit: int, timeout: int) -> tuple[list[dict], list[dict]]: ...
    def resolve_pending(self, pending: list[dict], max_n: int): ...
```

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv\Scripts\python -m pytest tests/test_providers_base.py -q`
Expected: PASS（4 passed）

- [ ] **Step 6: 提交**

```bash
git add backend/providers/__init__.py backend/providers/base.py tests/test_providers_base.py
git commit -m "音源解耦：新增 provider 契约层（归一化模型 + id 前缀 + 错误）"
```

---

## Task 2: providers/registry.py — 按前缀路由

**Files:**
- Create: `backend/providers/registry.py`
- Test: `tests/test_providers_registry.py`

**Interfaces:**
- Consumes: `base.MusicProvider`、`base.ProviderError`、`base.unpack_id`。
- Produces: `Registry`（`register(p)`、`get(prefix)->MusicProvider`、`resolve(track_id)->MusicProvider`、`list()->list[str]`）。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_providers_registry.py
import pytest
from backend.providers.registry import Registry
from backend.providers.base import ProviderError


class FakeProvider:
    def __init__(self, prefix): self.prefix = prefix
    def is_up(self, timeout=2): return True
    def search(self, k, l): return []
    def search_split(self, k, l, t): return [], []
    def resolve_pending(self, p, max_n): yield from ()


def test_register_and_get():
    r = Registry()
    p = FakeProvider("ncm")
    r.register(p)
    assert r.get("ncm") is p
    assert r.list() == ["ncm"]


def test_resolve_by_id_prefix():
    r = Registry()
    p = FakeProvider("ncm")
    r.register(p)
    assert r.resolve("ncm:123") is p


def test_get_unknown_prefix_raises_not_found():
    r = Registry()
    with pytest.raises(ProviderError) as ei:
        r.get("qq")
    assert ei.value.code == "NOT_FOUND"


def test_duplicate_prefix_raises():
    r = Registry()
    r.register(FakeProvider("ncm"))
    with pytest.raises(ValueError):
        r.register(FakeProvider("ncm"))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python -m pytest tests/test_providers_registry.py -q`
Expected: FAIL（`registry` 模块不存在）

- [ ] **Step 3: 写 `backend/providers/registry.py`**

```python
# backend/providers/registry.py
"""按 id 前缀把请求路由到对应 provider。本期只注册网易云；多源时即插。"""
from __future__ import annotations

from .base import MusicProvider, ProviderError, unpack_id


class Registry:
    def __init__(self):
        self._by_prefix: dict[str, MusicProvider] = {}

    def register(self, provider: MusicProvider) -> None:
        if provider.prefix in self._by_prefix:
            raise ValueError(f"prefix 冲突: {provider.prefix}")
        self._by_prefix[provider.prefix] = provider

    def get(self, prefix: str) -> MusicProvider:
        p = self._by_prefix.get(prefix)
        if p is None:
            raise ProviderError("NOT_FOUND", "registry", f"未知 provider 前缀: {prefix}")
        return p

    def resolve(self, track_id: str) -> MusicProvider:
        prefix, _ = unpack_id(track_id)
        return self.get(prefix)

    def list(self) -> list[str]:
        return list(self._by_prefix)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv\Scripts\python -m pytest tests/test_providers_registry.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/providers/registry.py tests/test_providers_registry.py
git commit -m "音源解耦：新增 provider registry（按 id 前缀路由）"
```

---

## Task 3: config 加 MUSIC_API_BASE/FILLER_KEYWORDS + providers/netease.py（含试听检测）

**Files:**
- Modify: `backend/config.py`（加 `MUSIC_API_BASE`、`FILLER_KEYWORDS`；本任务不删旧 NCM/UNM 常量，Task 5 再删）
- Create: `backend/providers/netease.py`
- Test: `tests/test_providers_netease.py`

**Interfaces:**
- Consumes: `config.MUSIC_API_BASE`、`config.FILLER_KEYWORDS`、`base.normalize_track`、`base.ProviderError`。
- Produces: `NeteaseProvider`（`prefix="ncm"`；`is_up`、`search`、`search_split`、`resolve_pending`；内部 `_get`、`_unlock`、`_is_full`）。

- [ ] **Step 1: 写失败测试（试听检测是重点）**

```python
# tests/test_providers_netease.py
import pytest
from backend import config
from backend.providers.netease import NeteaseProvider


@pytest.fixture(autouse=True)
def _base(monkeypatch):
    monkeypatch.setattr(config, "MUSIC_API_BASE", "http://x")  # 非空即“已配置”


def _mk(monkeypatch, songs, url_rows, unlock_url="http://unm/full"):
    """注入 HTTP 接缝：/cloudsearch 返回 songs；/song/url 返回 url_rows；/song/url/match 返回 unlock_url。"""
    def fake_get(self, path, timeout=15, **params):
        if path == "/cloudsearch":
            return {"result": {"songs": songs}}
        if path == "/song/url":
            return {"data": url_rows}
        if path == "/song/url/match":
            return {"code": 200, "data": unlock_url}
        return {}
    monkeypatch.setattr(NeteaseProvider, "_get", fake_get)


def test_is_full_detects_trial_and_empty():
    assert NeteaseProvider._is_full({"url": "http://u"}) is True
    assert NeteaseProvider._is_full({"url": "http://u", "freeTrialInfo": {"x": 1}}) is False  # 试听
    assert NeteaseProvider._is_full({"url": None}) is False


def test_free_full_song_used_directly(monkeypatch):
    _mk(monkeypatch,
        songs=[{"id": 1, "name": "A", "ar": [{"name": "x"}], "al": {}}],
        url_rows=[{"id": 1, "url": "http://free/1"}])
    tracks = NeteaseProvider().search("hi", limit=1)
    assert tracks[0]["id"] == "ncm:1"
    assert tracks[0]["url"] == "http://free/1" and tracks[0]["unlocked"] is False


def test_trial_clip_gets_unlocked(monkeypatch):
    # /song/url 给了 url 但带 freeTrialInfo（30s 试听）→ 必须走解锁拿完整地址
    _mk(monkeypatch,
        songs=[{"id": 2, "name": "B", "ar": [{"name": "y"}], "al": {}}],
        url_rows=[{"id": 2, "url": "http://trial/2", "freeTrialInfo": {"start": 0}}],
        unlock_url="http://full/2")
    tracks = NeteaseProvider().search("hi", limit=1)
    assert tracks[0]["url"] == "http://full/2" and tracks[0]["unlocked"] is True


def test_empty_url_gets_unlocked(monkeypatch):
    _mk(monkeypatch,
        songs=[{"id": 3, "name": "C", "ar": [{"name": "z"}], "al": {}}],
        url_rows=[{"id": 3, "url": None}],
        unlock_url="http://full/3")
    tracks = NeteaseProvider().search("hi", limit=1)
    assert tracks[0]["url"] == "http://full/3" and tracks[0]["unlocked"] is True


def test_search_split_first_locked_unlocked_rest_pending(monkeypatch):
    _mk(monkeypatch,
        songs=[{"id": 1, "name": "A", "ar": [{"name": "x"}], "al": {}},
               {"id": 2, "name": "B", "ar": [{"name": "y"}], "al": {}}],
        url_rows=[{"id": 1, "url": "http://trial/1", "freeTrialInfo": {"s": 0}},
                  {"id": 2, "url": "http://trial/2", "freeTrialInfo": {"s": 0}}],
        unlock_url="http://full/x")
    ready, pending = NeteaseProvider().search_split("hi", limit=5, timeout=8)
    assert ready and ready[0]["unlocked"] is True     # 头部被锁即时解一次定 track[0]
    assert [p["id"] for p in pending] == [2]           # 其余留 pending（原始对象）


def test_baseurl_empty_is_down(monkeypatch):
    monkeypatch.setattr(config, "MUSIC_API_BASE", "")
    assert NeteaseProvider().is_up() is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python -m pytest tests/test_providers_netease.py -q`
Expected: FAIL（`netease` 模块不存在）

- [ ] **Step 3: config.py 加 MUSIC_API_BASE / FILLER_KEYWORDS**

在 `backend/config.py` 把音源那段（现为 `# ---- 网易云音乐 API（NeteaseCloudMusicApi Enhanced 分支…` 起、到 `UNM_SOURCES = ...` 止）**保留旧常量不动**，并在其上方紧接插入：

```python
# ---- 音源（用户自部署的 NeteaseCloudMusicApi 兼容服务，运行时注入）----
MUSIC_API_BASE = os.getenv("MUSIC_API_BASE", "").strip().rstrip("/")  # 空=点歌不可用
# MUSIC_API_DIR 已在下方定义，作可选本地 spawn 目录（gitignore，不随仓发布）

# 泛请求“随便放点”的关键词（可免登录播放比例较高的类目）
FILLER_KEYWORDS = ["纯音乐", "轻音乐", "钢琴", "白噪音", "民谣", "爵士", "lo-fi 中文"]
```

（注：`import os` 已在文件顶部存在，无需新增。旧 `NCM_PORT/NCM_BASE/MUSIC_API_DIR/UNM_*` 常量此步保留，Task 5 删。）

- [ ] **Step 4: 写 `backend/providers/netease.py`**

```python
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
            raise ProviderError("NETWORK", self.provider_id, f"搜索失败：{e}") from e
        songs = [x for x in ((s.get("result") or {}).get("songs") or []) if x.get("id") is not None]
        return songs[: max(limit * 2, 12)]

    def _url_rows(self, songs: list[dict], timeout: int) -> dict:
        params = {"id": ",".join(str(x["id"]) for x in songs)}
        try:
            u = self._get("/song/url", timeout=timeout, **params)
        except ProviderError as e:
            raise ProviderError("NETWORK", self.provider_id, f"取址失败：{e}") from e
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
```

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv\Scripts\python -m pytest tests/test_providers_netease.py -q`
Expected: PASS（7 passed）

- [ ] **Step 6: 提交**

```bash
git add backend/config.py backend/providers/netease.py tests/test_providers_netease.py
git commit -m "音源解耦：网易云 adapter（试听检测 + 后端自带解锁）"
```

---

## Task 4: 装配 registry + 把 music.py 改为薄门面 + 迁移旧测试

**Files:**
- Modify: `backend/providers/__init__.py`（装配默认 registry）
- Modify: `backend/music.py`（整文件替换为薄门面）
- Modify: `tests/test_music_no_login.py`（迁到 provider 接缝）
- Modify: `tests/test_music_robustness.py`（迁到 provider 接缝）

**Interfaces:**
- Consumes: `NeteaseProvider`、`Registry`、`base.ProviderError`。
- Produces: `providers.registry()->Registry`、`providers.default_provider()->MusicProvider`；`music.MusicError`、`music.is_up`、`music.search_playable`、`music.search_split`、`music.resolve_pending`、`music.something`、`music.FILLER_KEYWORDS`（对外签名不变）。

- [ ] **Step 1: 装配 `backend/providers/__init__.py`**

```python
# backend/providers/__init__.py
"""音源 provider 层：装配默认 registry（本期只注册网易云）。"""
from .base import MusicProvider, ProviderError, normalize_track, pack_id, unpack_id
from .netease import NeteaseProvider
from .registry import Registry

_registry = Registry()
_registry.register(NeteaseProvider())


def registry() -> Registry:
    return _registry


def default_provider() -> MusicProvider:
    """当前活跃 provider（本期唯一：网易云）。将来多源时按 id 前缀 resolve。"""
    return _registry.get("ncm")
```

- [ ] **Step 2: 迁移 `tests/test_music_no_login.py`（先改测试→应失败）**

整文件替换为：

```python
"""用户决策: 彻底删除网易云登录，只留自部署后端 + 后端自带解锁。

- 登录相关接口应全部移除。
- 搜索取址在无 cookie 下正常：免费全曲直用，被锁（试听/空）交后端解锁。
"""
import inspect

from backend import music
from backend.providers.netease import NeteaseProvider


def test_login_surface_removed():
    for gone in ("saved_cookie", "qr_key", "qr_create", "qr_check",
                 "send_captcha", "login_cellphone", "login_nickname", "REAL_IP"):
        assert not hasattr(music, gone), f"{gone} 应已删除（登录已下线）"


def test_search_playable_works_without_cookie(monkeypatch):
    def fake_get(self, path, timeout=15, **params):
        if path == "/cloudsearch":
            return {"result": {"songs": [
                {"id": 1, "name": "A", "ar": [{"name": "x"}], "al": {}},
                {"id": 2, "name": "B", "ar": [{"name": "y"}], "al": {}},
            ]}}
        if path == "/song/url":
            assert "cookie" not in params           # 不带 cookie
            return {"data": [{"id": 1, "url": "http://free/1"}, {"id": 2, "url": None}]}
        return {}
    monkeypatch.setattr(NeteaseProvider, "_get", fake_get)
    monkeypatch.setattr(NeteaseProvider, "_unlock", lambda self, sid: "http://unm/2")

    tracks = music.search_playable("hi", limit=2)
    by_id = {t["id"]: t for t in tracks}
    assert set(by_id) == {"ncm:1", "ncm:2"}
    assert by_id["ncm:1"]["url"] == "http://free/1"      # 免费直用
    assert by_id["ncm:2"]["url"] == "http://unm/2"        # 被锁的解锁
    assert by_id["ncm:2"]["unlocked"] is True


def test_search_playable_signature_has_no_cookie_param():
    assert "cookie" not in inspect.signature(music.search_playable).parameters
```

- [ ] **Step 3: 迁移 `tests/test_music_robustness.py`（先改测试）**

整文件替换为：

```python
"""点歌板块健壮性：泛请求不破坏全局状态、脏搜索结果不致命、交互路径超时更紧。"""
from backend import config, music
from backend.providers.netease import NeteaseProvider


def test_something_does_not_mutate_global_keywords(monkeypatch):
    original = list(config.FILLER_KEYWORDS)
    monkeypatch.setattr(music.random, "shuffle", lambda seq: seq.reverse())
    monkeypatch.setattr(music, "search_playable", lambda kw, limit=12: [])
    music.something()
    assert config.FILLER_KEYWORDS == original


def test_search_playable_skips_songs_without_id(monkeypatch):
    def fake_get(self, path, timeout=15, **params):
        if path == "/cloudsearch":
            return {"result": {"songs": [
                {"name": "no-id"},
                {"id": 2, "name": "B", "ar": [{"name": "y"}], "al": {}},
            ]}}
        if path == "/song/url":
            return {"data": [{"id": 2, "url": "http://free/2"}]}
        return {}
    monkeypatch.setattr(NeteaseProvider, "_get", fake_get)
    tracks = music.search_playable("hi", limit=5)
    assert {t["id"] for t in tracks} == {"ncm:2"}      # 脏条目被丢，不抛 KeyError


def test_interactive_search_uses_tighter_timeout_than_startup(monkeypatch):
    seen: dict[str, int] = {}

    def fake_get(self, path, timeout=15, **params):
        seen[path] = timeout
        if path == "/cloudsearch":
            return {"result": {"songs": [{"id": 1, "name": "A", "ar": [{"name": "x"}], "al": {}}]}}
        if path == "/song/url":
            return {"data": [{"id": 1, "url": "http://free/1"}]}
        return {}
    monkeypatch.setattr(NeteaseProvider, "_get", fake_get)

    music.search_split("hi", limit=3)                  # 交互路径：紧超时
    assert seen["/cloudsearch"] < 15
    assert seen["/song/url"] < 15

    seen.clear()
    music.search_playable("hi", limit=3)               # 开机铺垫：宽默认
    assert seen["/cloudsearch"] == 15
    assert seen["/song/url"] == 15


def test_search_split_skips_songs_without_id(monkeypatch):
    def fake_get(self, path, timeout=15, **params):
        if path == "/cloudsearch":
            return {"result": {"songs": [
                {"name": "no-id"},
                {"id": 7, "name": "C", "ar": [{"name": "z"}], "al": {}},
            ]}}
        if path == "/song/url":
            return {"data": [{"id": 7, "url": "http://free/7"}]}
        return {}
    monkeypatch.setattr(NeteaseProvider, "_get", fake_get)
    ready, pending = music.search_split("hi", limit=5)
    assert {t["id"] for t in ready} == {"ncm:7"}
```

- [ ] **Step 4: 跑迁移后的测试确认失败**

Run: `.venv\Scripts\python -m pytest tests/test_music_no_login.py tests/test_music_robustness.py -q`
Expected: FAIL（旧 `music.py` 仍是老实现：`music._get`/`music.unm_match` 还在、id 无前缀、`config.FILLER_KEYWORDS` 可能未被 `something` 使用）

- [ ] **Step 5: 整文件替换 `backend/music.py` 为薄门面**

```python
# backend/music.py
"""音乐门面：对外保持稳定函数，内部委托当前音源 provider。

历史上直连本地 NeteaseCloudMusicApi；现经 provider 抽象层（backend/providers/），
音源由用户自部署、config.MUSIC_API_BASE 注入。app.py / 前端零改动。
"""
from __future__ import annotations

import random

from . import config
from .providers import default_provider
from .providers.base import ProviderError


class MusicError(Exception):
    pass


def _p():
    return default_provider()


def is_up(timeout: float = 2) -> bool:
    return _p().is_up(timeout)


def search_playable(keywords: str, limit: int = 10) -> list[dict]:
    """搜索并返回可播放曲目（免费全曲直用，被锁的交后端解锁）。"""
    try:
        return _p().search(keywords, limit)
    except ProviderError as e:
        raise MusicError(str(e)) from e


def search_split(keywords: str, limit: int = 12, timeout: int = 8):
    """交互点歌快路径：返回 (ready, pending)。"""
    try:
        return _p().search_split(keywords, limit, timeout)
    except ProviderError as e:
        raise MusicError(str(e)) from e


def resolve_pending(songs: list[dict], max_n: int = 12):
    """后台续解 pending（逐首 yield 归一化 track）。"""
    yield from _p().resolve_pending(songs, max_n)


def something(limit: int = 12) -> list[dict]:
    """随便来点能放的（泛请求）。"""
    for kw in random.sample(config.FILLER_KEYWORDS, len(config.FILLER_KEYWORDS)):
        tracks = search_playable(kw, limit)
        if tracks:
            return tracks
    return []
```

- [ ] **Step 6: 跑测试确认通过**

Run: `.venv\Scripts\python -m pytest tests/test_music_no_login.py tests/test_music_robustness.py tests/test_providers_netease.py -q`
Expected: PASS（全绿）

- [ ] **Step 7: 提交**

```bash
git add backend/providers/__init__.py backend/music.py tests/test_music_no_login.py tests/test_music_robustness.py
git commit -m "音源解耦：music.py 降为委托 provider 的薄门面，迁移测试到 provider 接缝"
```

---

## Task 5: app.py 可选本地 spawn + 删除旧 NCM/UNM 配置常量

**Files:**
- Modify: `app.py`（`start_music_server`、`_stop_music_server`、删 `_unm_up`、删 `_unm_proc`、确保 `import urllib.parse`）
- Modify: `backend/config.py`（删 `NCM_PORT/NCM_BASE/UNM_PORT/UNM_BASE/UNM_API_DIR/UNM_SOURCES`，保留 `MUSIC_API_DIR`）
- Test: `tests/test_music_spawn.py`

**Interfaces:**
- Consumes: `config.MUSIC_API_BASE`、`config.MUSIC_API_DIR`、`music.is_up`。
- Produces: `Api.start_music_server()`（仅本机 baseUrl + 本地目录存在时 spawn 单个 node）。

- [ ] **Step 1: 写失败测试（决策逻辑，mock 掉 spawn/exists）**

```python
# tests/test_music_spawn.py
"""start_music_server 的可选本地 spawn 决策：只在 baseUrl 指向本机、且本地 music-api/ 存在时才起。"""
import types
import pytest

import app as app_module
from backend import config, music


def _api(monkeypatch, base, up=False, server_exists=True):
    monkeypatch.setattr(config, "MUSIC_API_BASE", base)
    monkeypatch.setattr(music, "is_up", lambda timeout=2: up)
    # 假 MUSIC_API_DIR：其 (dir/"server.js").exists() 由 server_exists 决定
    class _P:
        def __truediv__(self, _): return self
        def exists(self): return server_exists
    monkeypatch.setattr(config, "MUSIC_API_DIR", _P())
    spawned = {}
    def fake_spawn(self, work_dir, env_extra=None):
        spawned["called"] = True; spawned["env"] = env_extra; return object()
    monkeypatch.setattr(app_module.Api, "_spawn_node", fake_spawn)
    api = app_module.Api.__new__(app_module.Api)   # 不跑 __init__
    api._music_proc = None
    return api, spawned


def test_spawns_when_localhost_and_dir_exists(monkeypatch):
    api, spawned = _api(monkeypatch, "http://localhost:3000", up=False, server_exists=True)
    api.start_music_server()
    assert spawned.get("called") and spawned["env"]["NCM_PORT"] == "3000"


def test_no_spawn_for_remote_base(monkeypatch):
    api, spawned = _api(monkeypatch, "http://music.example.com", up=False, server_exists=True)
    api.start_music_server()
    assert not spawned.get("called")


def test_no_spawn_when_dir_missing(monkeypatch):
    api, spawned = _api(monkeypatch, "http://127.0.0.1:3000", up=False, server_exists=False)
    api.start_music_server()
    assert not spawned.get("called")


def test_no_spawn_when_base_empty(monkeypatch):
    api, spawned = _api(monkeypatch, "", up=False, server_exists=True)
    api.start_music_server()
    assert not spawned.get("called")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python -m pytest tests/test_music_spawn.py -q`
Expected: FAIL（现 `start_music_server` 仍是旧的双服务 spawn，会尝试 UNM，逻辑不符）

- [ ] **Step 3: 改 `app.py` 音源那段（约 495–548 行）**

把 `start_music_server`、`_unm_up`、`_stop_music_server` 三处替换为：

```python
    def start_music_server(self) -> None:
        # 可选便利：仅当 baseUrl 指向本机、且本地存在（gitignore 的）music-api/ 时，帮用户 spawn。
        # 否则只连不 spawn（远程后端 / 未放本地目录 → 用户自己跑）。
        base = config.MUSIC_API_BASE
        if not base or music.is_up():
            return
        parts = urllib.parse.urlsplit(base)
        if parts.hostname not in ("localhost", "127.0.0.1", "::1"):
            return
        if not (config.MUSIC_API_DIR / "server.js").exists():
            return
        port = parts.port or 3000
        self._music_proc = self._spawn_node(config.MUSIC_API_DIR, {"NCM_PORT": str(port)})

    def _stop_music_server(self) -> None:
        proc = self._music_proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
```

删除整段 `@staticmethod def _unm_up(...)`（约 533–540 行）。同时：
- app.py 顶部 import 段（第 8–17 行）当前**没有** urllib（原 `_unm_up` 用的是函数内局部 `import urllib.request`）。在 `import time` 后新增一行 `import urllib.parse`。
- 删除 `__init__` 里第 89 行 `self._unm_proc: subprocess.Popen | None = None`（保留第 88 行 `self._music_proc`）。
- 原 `_stop_music_server`（约 542–548 行）遍历 `(self._music_proc, self._unm_proc)`，已由上面新版替换（只处理 `_music_proc`）。

- [ ] **Step 4: 删 `backend/config.py` 旧常量**

删除这几行（Task 3 保留的旧块）：`NCM_PORT`、`NCM_BASE`、`UNM_PORT`、`UNM_BASE`、`UNM_API_DIR`、`UNM_SOURCES` 及其上方 `# ---- 网易云音乐 API…` / `# ---- UNM 解锁服务…` 注释。**保留** `MUSIC_API_DIR = BASE_DIR / "music-api"`（挪到 MUSIC_API_BASE 附近，注释改为“可选本地 spawn 目录”）。

- [ ] **Step 5: 跑测试确认通过（含全套回归）**

Run: `.venv\Scripts\python -m pytest tests/test_music_spawn.py -q`
Expected: PASS（4 passed）
Run: `.venv\Scripts\python -m pytest -q`
Expected: PASS（全绿；确认删常量没漏引用）

- [ ] **Step 6: 提交**

```bash
git add app.py backend/config.py tests/test_music_spawn.py
git commit -m "音源解耦：app 仅本机+本地目录时可选 spawn，删除 UNM/NCM 旧常量"
```

---

## Task 6: 版权清理 — 移出 Node 目录 + 换向守卫测试 + run.bat

**Files:**
- Modify: `.gitignore`
- Delete from repo (保留本地): `music-api/`、`unm-api/`（`git rm -r --cached`）
- Modify: `run.bat`（删 Node 依赖自动安装块，保持 GBK）
- Modify: `tests/test_music_source_enhanced.py`（换向为版权守卫）

**Interfaces:** 无代码接口；产出“git 跟踪文件无 NCM/UNM 依赖”的守卫。

- [ ] **Step 1: 换向守卫测试（先写→应失败，因目录还被跟踪）**

整文件替换 `tests/test_music_source_enhanced.py`：

```python
"""版权守卫：公开仓不得出现网易云 Node / UNM 的代码物料。

音源改为用户自部署 + MUSIC_API_BASE 注入；仓库里任何被 git 跟踪的 package.json
都不得声明 NeteaseCloudMusicApi / Enhanced / UNM 依赖，music-api/ 与 unm-api/
目录也不得被跟踪。踩线即红。
"""
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
BANNED = ("neteasecloudmusicapi", "@neteasecloudmusicapienhanced", "@unblockneteasemusic")


def _tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    return out.stdout.splitlines()


def test_no_music_source_dirs_tracked():
    tracked = _tracked_files()
    bad = [f for f in tracked if f.startswith("music-api/") or f.startswith("unm-api/")]
    assert not bad, f"这些音源目录文件不应被 git 跟踪（版权风险）：{bad[:5]}"


def test_no_tracked_packagejson_declares_ncm_or_unm():
    offenders = []
    for f in _tracked_files():
        if f.endswith("package.json"):
            text = (ROOT / f).read_text("utf-8", errors="ignore").lower()
            if any(b in text for b in BANNED):
                offenders.append(f)
    assert not offenders, f"这些被跟踪的 package.json 含 NCM/UNM 依赖，不能上仓：{offenders}"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python -m pytest tests/test_music_source_enhanced.py -q`
Expected: FAIL（`music-api/`、`unm-api/` 仍被跟踪）

- [ ] **Step 3: `.gitignore` 追加音源目录**

在 `# ---- Node 依赖…` 块后追加：

```
# ---- 音源后端目录（用户自部署，含 NCM/UNM，绝不上仓）----
music-api/
unm-api/
```

- [ ] **Step 4: 取消跟踪两目录（本地文件保留）**

```bash
git rm -r --cached music-api unm-api
```

- [ ] **Step 5: 改 run.bat（删 Node 自动安装块，保持 GBK）**

用支持 GBK/ANSI 的编辑器打开 `run.bat`，删除 Node 依赖自动安装块（`where node` 检测 + `if not exist "music-api\node_modules"` / `if not exist "unm-api\node_modules"` 两段 npm install，约 17–31 行）。**另存为 ANSI/GBK（cp936），不要 UTF-8**。

- [ ] **Step 6: 跑守卫 + bat 编码守卫 + 全套**

Run: `.venv\Scripts\python -m pytest tests/test_music_source_enhanced.py tests/test_bat_encoding.py -q`
Expected: PASS
Run: `.venv\Scripts\python -m pytest -q`
Expected: PASS（全绿）

- [ ] **Step 7: 提交**

```bash
git add .gitignore run.bat tests/test_music_source_enhanced.py
git commit -m "版权清理：music-api/unm-api 移出仓库改用户自部署，换向版权守卫测试"
```

---

## Task 7: 文档 — .env.example / README / CLAUDE.md

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `CLAUDE.md`

**Interfaces:** 无代码接口。

- [ ] **Step 1: `.env.example` 加 MUSIC_API_BASE**

在天气那段后追加：

```
# 可选：点歌。填了才能点歌；指向你自部署的 NeteaseCloudMusicApi 兼容服务（Enhanced 或 fork）。
# 本机自建示例：MUSIC_API_BASE=http://localhost:3000（把音源 Node 放进 music-api/ 则双击 run.bat 会自动起）
# 远程实例：MUSIC_API_BASE=http://your-host:3000
# MUSIC_API_BASE=
```

- [ ] **Step 2: 改 README 音源相关处**

- 手动启动块（约 35–36 行）删掉 `cd music-api && npm install` 与 `cd unm-api && npm install` 两行，替换为一行说明：
  ```
  > :: 点歌需另行自部署 NeteaseCloudMusicApi 兼容服务，并在 .env 填 MUSIC_API_BASE
  ```
- 快速开始第 2 步（约 27 行）删“装 Node 音乐服务依赖”表述。
- 小白教程 Node 相关（约 49、68、86 行）改为“点歌需自部署音源服务并填 `MUSIC_API_BASE`（进阶，可跳过）”。
- 目录结构（约 144–145 行）删 `music-api/`、`unm-api/` 两行，加一行：
  ```
  ├─ backend/providers/  # 音源 provider 层（base 契约 + registry 路由 + netease adapter）
  ```
- 许可致谢（约 160–161 行）保持指向 NeteaseCloudMusicApi Enhanced / UnblockNeteaseMusic 的链接（仅文字链接、非代码物料），措辞改为“点歌功能需用户自部署第三方服务，本项目不含其代码”。
- 新增一小节“点歌音源（自部署）”，说明：部署任意 NCM 兼容服务 → 填 `MUSIC_API_BASE`；曲库补齐可参考聚合 API（Meting / go-music-dl）/ QQ / YouTube（各作 provider adapter，未来）。

- [ ] **Step 3: 改 CLAUDE.md 音源描述**

- 顶部简介（约 4 行）“点歌走本地 Node 服务（网易云 API + UNM 解锁）”改为“点歌经 provider 抽象层（`backend/providers/`）连用户自部署的 NCM 兼容后端（`MUSIC_API_BASE`），仓内零 NCM/UNM 物料，解锁用后端自带 `/song/url/match`”。
- 模块速览里 `music.py` 一行改为“音乐门面，委托 `providers/` 当前 adapter”。

- [ ] **Step 4: 全套回归**

Run: `.venv\Scripts\python -m pytest -q`
Expected: PASS（全绿）

- [ ] **Step 5: 提交**

```bash
git add .env.example README.md CLAUDE.md
git commit -m "文档：音源改用户自部署 MUSIC_API_BASE，同步 README/CLAUDE/.env.example"
```

---

## 完成后总校验

- [ ] `.venv\Scripts\python -m pytest -q` 全绿。
- [ ] `git ls-files | grep -E "music-api/|unm-api/"` 为空。
- [ ] `git ls-files` 里所有 `package.json` 不含 NCM/UNM 依赖（版权守卫测试已覆盖）。
- [ ] 手动冒烟（可选，需自部署后端）：`.env` 填 `MUSIC_API_BASE`，`.venv\Scripts\python app.py`，点一首 VIP 歌确认播完整曲（非 30s 试听）。
