"""当地天气：OpenWeather 当前天气。位置优先用设置里的城市，否则按 IP 自动定位。结果缓存 30 分钟。"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from . import config

_cache = {"ts": 0.0, "data": None}
_TTL = 1800  # 30 分钟

# OpenWeather icon 前缀 -> emoji
_EMOJI = {
    "01": "☀️", "02": "⛅", "03": "☁️", "04": "☁️",
    "09": "🌧️", "10": "🌦️", "11": "⛈️", "13": "❄️", "50": "🌫️",
}


def invalidate() -> None:
    _cache["data"] = None
    _cache["ts"] = 0.0


def _get(url: str, timeout: int = 8) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Dsdio/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _locate() -> tuple:
    """返回 (lat, lon, query)。填了城市就用「城市,国家码」查询，否则按 IP 定位。"""
    s = config.load_settings()
    city = (s.get("weather_city") or "").strip()
    country = (s.get("weather_country") or "").strip()
    if city:
        return None, None, (f"{city},{country}" if country else city)
    try:
        d = _get("http://ip-api.com/json/?fields=lat,lon,city")
        return d.get("lat"), d.get("lon"), d.get("city", "")
    except Exception:
        return None, None, ""


def current() -> dict:
    now = time.time()
    if _cache["data"] and now - _cache["ts"] < _TTL:
        return _cache["data"]

    key = config.get_weather_key()
    if not key:
        return {"ok": False, "error": "no_key"}

    lat, lon, city = _locate()
    try:
        if lat is not None and lon is not None:
            url = (f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}"
                   f"&appid={key}&units=metric&lang=zh_cn")
        elif city:
            url = "https://api.openweathermap.org/data/2.5/weather?" + urllib.parse.urlencode(
                {"q": city, "appid": key, "units": "metric", "lang": "zh_cn"})
        else:
            return {"ok": False, "error": "no_location"}
        d = _get(url)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}

    if str(d.get("cod")) != "200":
        return {"ok": False, "error": d.get("message", "weather error")}

    w0 = (d.get("weather") or [{}])[0]
    icon = (w0.get("icon") or "01d")[:2]
    out = {
        "ok": True,
        "city": d.get("name") or city,
        "temp": round((d.get("main") or {}).get("temp", 0)),
        "desc": w0.get("description", ""),
        "emoji": _EMOJI.get(icon, "🌡️"),
    }
    _cache["ts"] = now
    _cache["data"] = out
    return out
