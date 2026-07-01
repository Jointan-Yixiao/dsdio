# 可配置音源 provider 层 — 设计文档

> 日期：2026-07-01 ｜ 状态：待评审
> 目标：把公开仓库里的网易云 Node / UNM 代码物料清干净以规避版权风险，音源改为**用户自部署 + 运行时配置 baseUrl**；播放器与音源解耦，未来可插多音源。

---

## 1. 背景与目标

**现状**：`backend/music.py` 按 HTTP 打两个本仓自带、由 `app.py` spawn 的 Node 服务——`music-api/`(网易云 Enhanced，搜索/取址) 与 `unm-api/`(UNM 解锁)。这两个目录带着 `NeteaseCloudMusicApi*` / `@unblockneteasemusic/*` 依赖，**不能上 GitHub**。

**目标**
1. **公开仓零 NCM/UNM 代码物料**：不 import、不作依赖、`package.json` 不出现；只保留"打到用户自填 baseUrl"的 HTTP 客户端逻辑。
2. **音源用户自配**：`.env` 注入 baseUrl，指向用户自部署的网易云 Node（Enhanced 或任意兼容 fork）。留空则点歌不可用，聊天/新闻照常。
3. **薄 provider 接缝**：定义 `MusicProvider` 接口 + id 前缀 + 按前缀路由，本期只实现网易云一个 adapter，未来加聚合/QQ/YouTube 各写一个 adapter 即插。
4. **保住一键便利**：本地存在音源目录时 app 仍自动 spawn（用户选项 B）。

## 2. 非目标（YAGNI）

- 不做 capabilities/歌词/歌单/专辑/artist 等 spec 里的重接口。
- 不做缓存装饰器、登录态管理、音质档协商。
- 本期不写聚合/QQ/YouTube/Local adapter——只预留接口。
- 不动前端、不动 `app.py` 的对外行为（music.py 公共函数签名不变）。

## 3. 架构总览

数据流在接缝处不变：**前端 → `app.py`(js_api) → `backend/music.py`(公共函数) → provider → HTTP → 用户后端**。

新增 `backend/providers/` 包，`music.py` 降为"公共函数 + 委托当前 provider"的薄壳：

```
backend/
  music.py                 # 对外公共函数（签名不变），持 registry，委托 provider
  providers/
    __init__.py            # 装配默认 registry（注册 NeteaseProvider）
    base.py                # MusicProvider 协议 + 归一化模型 + pack_id/unpack_id + ProviderError
    registry.py            # 按 id 前缀路由（register / resolve / get）
    netease.py             # NeteaseProvider：NCM 路由方言 + 取址 + 试听检测 + 解锁
```

**边界职责**
- `base.py`：只定义契约与工具，无网络。纯可测。
- `netease.py`：唯一懂"网易云路由方言"的地方。所有 `/cloudsearch`、`/song/url`、`/song/url/match` 封在这。
- `registry.py`：按前缀派发；本期只有一个 `ncm` provider，但路由已就位。
- `music.py`：保持 `search_split/search_playable/resolve_pending/something/is_up` 五个对外函数，内部转调 registry 解析出的 provider。

## 4. 归一化模型与 id 前缀（base.py）

沿用现有 `_track` 的字段（`id/name/artist/album/cover/duration/url/unlocked/source`），只改两点：

- **id 带前缀**：`"{prefix}:{rawId}"`，如 `"ncm:123456"`。提供 `pack_id(prefix, raw)` / `unpack_id(id) -> (prefix, raw)`。
- **归一化产出统一经 provider**，上层不碰原始响应。

```python
class MusicProvider(Protocol):
    prefix: str                       # 如 "ncm"
    def is_up(self, timeout: float = 2) -> bool: ...
    def search(self, keywords: str, limit: int) -> list[dict]: ...        # 归一化 track，url 已解析
    def search_split(self, keywords, limit, timeout) -> tuple[list, list]: ...  # 快路径：ready/pending
    def resolve_pending(self, pending: list, max_n: int): ...             # 后台续解，逐首 yield
```

> 注 1：`search`（对应 music.py 的 `search_playable`，开机铺垫、宽超时）与 `search_split`（交互点歌、紧超时）都在内部**急切**解析并附上可播 url——现架构没有独立的"单曲 getPlayUrl"公共调用，取址+解锁是 provider 内部 helper（见 §5），不进 Protocol。
> 注 2：`search_split`/`resolve_pending` 进接口，是因为"秒起 + 后台续解"是 provider 内部关切（哪些歌要解锁、怎么并发）。聚合/YouTube adapter 各自实现同一语义。music.py 的 `something()`（泛请求随便放点）仍是 music.py 层薄封装，不进 Protocol。

`ProviderError(code, provider_id, message)`，`code ∈ {NETWORK, NOT_FOUND, UNAVAILABLE, UNKNOWN}`。对外不冒泡原始 urllib 错误。

## 5. NeteaseProvider 取址/解锁流程（核心）

`prefix = "ncm"`，`base = config.MUSIC_API_BASE`。路由方言：`/cloudsearch`、`/song/url`、`/song/url/match`。

**取址+解锁（NeteaseProvider 内部 helper `_play_url(raw_id) -> (url, unlocked)`，被 `search`/`search_split`/`resolve_pending` 调用）严格顺序：**

```
1. /song/url?id=<rawId>  取网易云地址
2. 若 url 非空 且 非试听片段（响应 freeTrialInfo 为空）：
     → 完整免费曲，直接用，source=""
3. 若 url 为空，或 freeTrialInfo 非空（试听片段）：      ← 关键修正
     → /song/url/match?id=<rawId>（不传 source）取回完整地址
        → 成功：unlocked=True, source=""（后端不回传源平台）
        → 失败：该曲不可用（跳过 / 上层继续下一首）
```

**为什么必须做试听检测**（2026-07-01 基准，292 首 VIP 歌）：
- 免登录 `/song/url` 对 VIP 歌 **完整 0 / 试听 291 / 空 1**——几乎全是 30 秒片段。
- 只判 `url 为空` 会让绝大多数热门歌只播 30 秒就断。故 `freeTrialInfo` 非空必须一并判为"需解锁"。
- Enhanced 自带 `/song/url/match` 对这 292 首解锁 **292/292 = 100%**（经典 UNM 95%，且 UNM 漏的 14 首 Enhanced 全补上）→ 单 baseUrl + 后端自带解锁足够，**不引入独立 UNM**。

`search_split` 沿用现有"ready 保相关性即可播 / 头部被锁即时解一次定 track[0] / 其余 pending 后台续解"逻辑，只是把"被锁"的判定从 `url 空` 扩展为 `url 空 或 试听`，解锁调用从旧 `unm_match` 换成 `/song/url/match`。

## 6. 配置与可选本地 spawn（config.py / app.py）

**config.py**
```python
MUSIC_API_BASE = os.getenv("MUSIC_API_BASE", "").strip().rstrip("/")  # 用户自部署；空=点歌不可用
MUSIC_API_DIR  = BASE_DIR / "music-api"   # 可选本地便利目录（已 gitignore，不随仓发布）
```
移除 `NCM_PORT/NCM_BASE` 命名与 `UNM_PORT/UNM_BASE/UNM_API_DIR/UNM_SOURCES`（解锁并入后端）。

**app.py `start_music_server()`（可选便利 spawn）**
- 若 `MUSIC_API_BASE` 指向 localhost/127.0.0.1、且 `MUSIC_API_DIR/server.js` 存在、且该端口未起 → `node server.js` 起在从 baseUrl 解析出的端口。
- 否则只连不 spawn（用户跑远程或不放本地目录）。
- 逻辑加注释标明"可选便利、目录不随仓发布"，避免读代码困惑。
- 删除对 `unm-api` 的 spawn。

## 7. 版权清理（仓库 / 文档 / 构建）

- `git rm -r --cached music-api unm-api`；`.gitignore` 追加 `music-api/`、`unm-api/`。
- `run.bat`：删掉对 `music-api`/`unm-api` 的 `npm install` 步骤。
- `.env.example`：加 `MUSIC_API_BASE=`（含注释：填你自部署的网易云 Node 地址）。
- `README.md`：音源段重写为"自部署任意 NeteaseCloudMusicApi 兼容服务，填 MUSIC_API_BASE"；附推荐 fork/部署指引与可选补源方向（聚合 API / QQ / YouTube）。
- `CLAUDE.md`：音源描述同步为"用户自配 baseUrl，仓内零 NCM/UNM 物料"。

## 8. 错误处理与降级

- `MUSIC_API_BASE` 为空 → `is_up()` False → 现有降级路径生效（点歌不可用，聊天/新闻正常）。
- 后端不可达 → provider 抛 `ProviderError(NETWORK)`，`music.py` 收敛为 `MusicError`（保持 `app.py` 现有 except 不变）。
- 解锁失败 → 该曲跳过，不致命。

## 9. 测试策略（TDD）

纯逻辑在 provider 接缝 mock HTTP 后测：
1. **免费全曲直用**：`/song/url` 返回 url 且 `freeTrialInfo` 空 → 直接用，`unlocked=False`。
2. **试听→解锁**：`/song/url` 返回 url 但 `freeTrialInfo` 非空 → 走 `/song/url/match` → 用解锁地址，`unlocked=True`。（基准挖出的关键 case）
3. **空→解锁**：`/song/url` 返回 null → 走 `/song/url/match`。
4. **baseUrl 空 → 不可用**：`MUSIC_API_BASE=""` → `is_up()` False，`search_*` 抛 `MusicError`/返回空而不崩。
5. **id 前缀路由**：`unpack_id("ncm:123")` 正确；`registry.resolve` 按前缀派发；未知前缀抛 `NOT_FOUND`。
6. **改写版权守卫**：把现有 `tests/test_music_source_enhanced.py` 换向——扫描 **git 跟踪的文件** 中任何 `package.json` 不得含 `NeteaseCloudMusicApi*` / `@neteasecloudmusicapienhanced/*` / `@unblockneteasemusic/*`。踩线即红，把"GitHub 不能出现网易云 nodejs/UNM"钉成测试。
7. 现有 `test_music_no_login.py` / `test_music_robustness.py` 迁移到 provider 语义，保持覆盖。

## 10. 验收标准

1. `MUSIC_API_BASE` 空时点歌不可用、无静默内置地址；聊天/新闻正常。
2. VIP 试听歌能取回完整地址（不再 30 秒断）——试听检测生效。
3. `git ls-files` 里无 `music-api/`、`unm-api/`，无任何 NCM/UNM 包依赖；版权守卫测试绿。
4. `app.py`、前端零改动仍正常点歌（公共函数签名不变）。
5. 未来加一个新音源 = 新写 `providers/<x>.py` + 注册，不改 `music.py` 公共层与 `app.py`。
6. 全套 `pytest` 绿。

## 11. 未来扩展（本期只预留，不实现）

按 id 前缀新增 adapter 即插：
- **聚合 API**（推荐兜底）：一个 `agg` adapter 指向自建 Meting-API / go-music-dl，一次覆盖网易云+QQ+酷狗+酷我+咪咕。
- **QQ音乐**：`qq` adapter（jsososo/Rain120，补华语大盘）。
- **YouTube**：`yt` adapter 包 yt-dlp 小服务（全球 catch-all）。
- **本地/自有曲库**：`local` adapter（本地文件/直链）、Subsonic/Navidrome。

每个都遵循同一原则：仓内零该平台代码物料，用户自部署 + 配各自 baseUrl。
