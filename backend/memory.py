"""用户记忆：长期(偏好) + 短期(当日)。

- long_memory.json：长期偏好 —— 喜欢的曲风、什么时段听什么、什么天气听什么、喜欢怎样的聊天方式。
- short_memory.json：当日记录 —— 今天的心情、做了什么、几点/什么天气听了什么、聊天方式（带日期）。

机制：
- 启动时 rollover()：若短期记忆是过去某天且有内容，用 DeepSeek 把它总结进长期记忆，再开"新的一天"。
- 对话时 observe()（后台、不阻塞）：从最近一轮对话里更新当日心情 / 活动 / 聊天方式，并记录
  "用户主动要求放的歌曲风格(requested)"与"被推荐后用户明确喜欢/夸奖的那首歌的风格(liked)"
  —— 只记风格，不记具体歌名；开机自动播放的歌不计入偏好。
- context_blurb()：把长期偏好 + 今日情况压成一段，注入对话/开场白，用来找话题、安慰、荐歌。
"""
from __future__ import annotations

import json
import threading
from datetime import date, datetime

from . import config, host

LONG_FILE = config.BASE_DIR / "long_memory.json"
SHORT_FILE = config.BASE_DIR / "short_memory.json"

_LONG_DEFAULT = {
    "updated": "",
    "genres": [],          # 喜欢的曲风 / 风格
    "time_prefs": [],      # 时段听歌偏好，如 "late night: ambient, lo-fi"
    "weather_prefs": [],   # 天气听歌偏好，如 "rainy: mellow piano"
    "chat_style": "",      # 喜欢怎样的聊天方式
    "notes": [],           # 其它长期洞察
}

_SHORT_DEFAULT = {
    "date": "",
    "mood": "",            # 当日心情
    "activities": [],      # 今天做了什么
    "music": [],           # 风格记录 [{time, weather, style, why}]，why ∈ "requested" | "liked"
    "chat_notes": "",      # 今天观察到的聊天方式
}

_lock = threading.RLock()


def _today() -> str:
    return date.today().isoformat()


def _read(path, default: dict) -> dict:
    if path.exists():
        try:
            merged = dict(default)
            merged.update(json.loads(path.read_text("utf-8")) or {})
            return merged
        except Exception:
            pass
    return dict(default)


def _write(path, data: dict) -> None:
    config.atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def load_long() -> dict:
    return _read(LONG_FILE, _LONG_DEFAULT)


def load_short() -> dict:
    return _read(SHORT_FILE, _SHORT_DEFAULT)


def save_long(data: dict) -> None:
    with _lock:
        data["updated"] = _today()
        _write(LONG_FILE, data)


def save_short(data: dict) -> None:
    with _lock:
        _write(SHORT_FILE, data)


def ensure_today() -> dict:
    """确保短期记忆是"今天"的；不是则重置为今天的空记录。返回当前短期记忆。"""
    with _lock:
        s = _read(SHORT_FILE, _SHORT_DEFAULT)
        if s.get("date") != _today():
            s = dict(_SHORT_DEFAULT)
            s["date"] = _today()
            _write(SHORT_FILE, s)
        return s


def context_blurb() -> str:
    """长期偏好 + 今日情况压成一段，注入对话/开场白。"""
    long, short = load_long(), load_short()
    parts: list[str] = []
    if long.get("genres"):
        parts.append("Liked music styles: " + ", ".join(long["genres"]))
    if long.get("time_prefs"):
        parts.append("By time of day: " + "; ".join(long["time_prefs"]))
    if long.get("weather_prefs"):
        parts.append("By weather: " + "; ".join(long["weather_prefs"]))
    if long.get("chat_style"):
        parts.append("Preferred chat style: " + long["chat_style"])
    if long.get("notes"):
        parts.append("Notes about them: " + "; ".join(long["notes"][:6]))
    if short.get("date") == _today():
        if short.get("mood"):
            parts.append("Their mood today: " + short["mood"])
        if short.get("activities"):
            parts.append("What they've been doing today: " + "; ".join(short["activities"]))
        if short.get("music"):
            def _fmt(m):
                ctx = ", ".join(x for x in (m.get("time"), m.get("weather")) if x)
                return m.get("style", "") + (f" ({ctx})" if ctx else "")
            req = [_fmt(m) for m in short["music"] if m.get("why") == "requested" and m.get("style")]
            liked = [_fmt(m) for m in short["music"] if m.get("why") == "liked" and m.get("style")]
            if req:
                parts.append("Styles they asked to play today: " + "; ".join(req[-5:]))
            if liked:
                parts.append("Styles they liked / praised today: " + "; ".join(liked[-5:]))
    return "\n".join(parts)


# ---------------- LLM：归并 / 观察 ----------------
def _coerce_list(v, fallback, cap=12) -> list:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()][:cap]
    return list(fallback or [])


def _summarize_into_long(long: dict, short: dict) -> dict:
    """用 DeepSeek 把一天的短期记录融进长期偏好（保留旧的、增量更新，不简单覆盖）。"""
    sys = (
        "You maintain a music listener's long-term preference profile. Merge one day's log into the "
        "existing profile: keep what's still true, fold in fresh evidence about their music taste — the "
        "STYLES/GENRES they actively asked the DJ to play, and the styles of recommended songs they "
        "praised or said they liked — plus what they reach for at which time of day, in which weather, "
        "and their preferred chat style. Record only music STYLES/GENRES, NEVER specific song titles. "
        "Deduplicate, keep each list concise (<=12 short items), stay factual — do not invent "
        "preferences not supported by the log. Return ONLY JSON with exactly these keys: genres "
        "(array of strings), time_prefs (array), weather_prefs (array), chat_style (string), notes (array)."
    )
    keep = ("genres", "time_prefs", "weather_prefs", "chat_style", "notes")
    user = (
        "EXISTING LONG-TERM PROFILE:\n"
        + json.dumps({k: long.get(k) for k in keep}, ensure_ascii=False)
        + "\n\nDAY LOG TO FOLD IN (date " + short.get("date", "") + "):\n"
        + json.dumps({k: short.get(k) for k in ("mood", "activities", "music", "chat_notes")},
                     ensure_ascii=False)
    )
    client = host._client()
    resp = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
        response_format={"type": "json_object"}, temperature=0.3, max_tokens=900,
    )
    try:
        data = json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        data = {}
    out = dict(_LONG_DEFAULT)
    for k in ("genres", "time_prefs", "weather_prefs", "notes"):
        out[k] = _coerce_list(data.get(k), long.get(k))
    cs = data.get("chat_style")
    out["chat_style"] = cs.strip() if isinstance(cs, str) and cs.strip() else long.get("chat_style", "")
    return out


def rollover() -> bool:
    """启动时调用：短期记忆若是过去某天且有内容 → 总结进长期记忆，并开新的一天。
    返回是否发生了归并。无 API key 时仅安全地重置日期。"""
    with _lock:
        s = _read(SHORT_FILE, _SHORT_DEFAULT)
        stale = bool(s.get("date")) and s["date"] != _today()
        has_content = bool(s.get("mood") or s.get("activities") or s.get("music") or s.get("chat_notes"))
        if stale and has_content:
            try:
                merged = _summarize_into_long(load_long(), s)
                save_long(merged)
            except Exception:
                pass  # 没 key / 网络问题：宁可不归并，也不丢当天数据进黑洞
            fresh = dict(_SHORT_DEFAULT)
            fresh["date"] = _today()
            _write(SHORT_FILE, fresh)
            return True
    ensure_today()
    return False


# 提炼节流：每轮只入缓冲，攒够这么多轮才真正发一次 DeepSeek 提炼（把每条消息一次 API 降到每 10 条）。
_OBSERVE_EVERY = 10
_turn_buffer: list[dict] = []


def observe(history: list, user_text: str, reply: str, weather_desc: str = "") -> bool:
    """把本轮对话入缓冲；攒够 _OBSERVE_EVERY 轮才做一次 LLM 提炼。
    返回这一轮是否真的触发了提炼（省 API：平时只是廉价地 append）。失败静默。
    代价：未满 10 轮就关程序时，这几轮的当日心情/活动不会被提炼进短期记忆。"""
    with _lock:
        _turn_buffer.append({"user": user_text or "", "reply": reply or "", "weather": weather_desc or ""})
        if len(_turn_buffer) < _OBSERVE_EVERY:
            return False
        batch = list(_turn_buffer)
        _turn_buffer.clear()
    try:
        _run_observe(batch)
    except Exception:
        pass
    return True


def _run_observe(batch: list[dict]) -> None:
    """对攒起来的一批对话做一次提炼：更新当日心情 / 活动 / 聊天方式，并记录"用户主动要求放的
    歌曲风格"和"被推荐后明确喜欢/夸奖的那首歌的风格"（只记风格、不记歌名）。"""
    sys = (
        "You quietly keep a listener's short-term day notes for their personal radio-DJ companion. "
        "Given the current notes and the recent exchanges, update them. Infer the listener's current "
        "mood, what they've been doing today (activities), and their chat style. ALSO capture music "
        "STYLES/GENRES (never song titles): 'wanted_styles' = the kinds of music the listener "
        "ACTIVELY asked the DJ to play in these exchanges (if they named an artist, give that artist's "
        "general style instead of the name); 'liked_styles' = the style of a song the DJ "
        "recommended or played that the listener then praised or said they liked. Only record real "
        "signal from the listener's own words; leave any field empty if nothing new is revealed. "
        "Keep activities concise (<=10 short items); mood a short phrase; each style a short phrase. "
        "Return ONLY JSON with keys: mood (string), activities (array), chat_notes (string), "
        "wanted_styles (array), liked_styles (array)."
    )
    cur = ensure_today()
    transcript = "\n".join(
        f"Listener: {e.get('user','')}\nDJ: {e.get('reply','')}" for e in batch)
    # 取这批里最后一个非空天气，作为这批新增风格记录的天气上下文。
    weather_desc = next((e.get("weather") for e in reversed(batch) if e.get("weather")), "")
    user = (
        "CURRENT NOTES:\n"
        + json.dumps({k: cur.get(k) for k in ("mood", "activities", "chat_notes")}, ensure_ascii=False)
        + "\n\nRECENT EXCHANGES:\n" + transcript
    )
    client = host._client()
    resp = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
        response_format={"type": "json_object"}, temperature=0.2, max_tokens=400,
    )
    data = json.loads(resp.choices[0].message.content or "{}")
    with _lock:
        s = _read(SHORT_FILE, _SHORT_DEFAULT)
        if s.get("date") != _today():
            s = dict(_SHORT_DEFAULT)
            s["date"] = _today()
        mood = data.get("mood")
        if isinstance(mood, str) and mood.strip():
            s["mood"] = mood.strip()
        acts = data.get("activities")
        if isinstance(acts, list):
            s["activities"] = _coerce_list(acts, s.get("activities"), cap=10)
        cn = data.get("chat_notes")
        if isinstance(cn, str) and cn.strip():
            s["chat_notes"] = cn.strip()
        now = datetime.now().strftime("%H:%M")
        for why, key in (("requested", "wanted_styles"), ("liked", "liked_styles")):
            for st in _coerce_list(data.get(key), [], cap=6):
                s.setdefault("music", []).append(
                    {"time": now, "weather": weather_desc, "style": st, "why": why})
        s["music"] = s.get("music", [])[-40:]
        _write(SHORT_FILE, s)
