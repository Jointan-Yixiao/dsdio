"""配置与设置持久化。

- 从 .env 读取 DeepSeek API Key / 代理。
- 定义 RSS 新闻源、DJ 音色 persona、默认参数。
- 用户可调设置存到项目根目录 settings.json。
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "cache"
SETTINGS_FILE = BASE_DIR / "settings.json"

# 串行化 settings.json 的 read-modify-write，避免并发 save 互相覆盖（丢 key/cookie 等）。
_settings_lock = threading.RLock()


def atomic_write_text(path: Path, text: str) -> None:
    """原子写文本：先写同目录临时文件，再 os.replace 顶替。
    崩溃/断电/磁盘满时只会留下未动的原文件或干净的临时文件，绝不出现写到一半的截断文件。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, "utf-8")
    try:
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise

load_dotenv(BASE_DIR / ".env")

# ---- DeepSeek ----
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


def _resolve_model() -> str:
    """DeepSeek 模型名：.env 里 DEEPSEEK_MODEL 填了就用它，否则用默认。
    分享给别人时这点很关键——他们账号未必有 deepseek-v4-flash，可在 .env 改成
    自己可用的（如官方公开的 deepseek-chat）。"""
    return os.getenv("DEEPSEEK_MODEL", "").strip() or "deepseek-v4-flash"


# 默认 deepseek-v4-flash（快/省）；deepseek-v4-pro 更强。可用 .env 的 DEEPSEEK_MODEL 覆盖。
DEEPSEEK_MODEL = _resolve_model()

# ---- 音源（用户自部署的 NeteaseCloudMusicApi 兼容服务，运行时注入）----
MUSIC_API_BASE = os.getenv("MUSIC_API_BASE", "").strip().rstrip("/")  # 空=点歌不可用
MUSIC_API_DIR = BASE_DIR / "music-api"  # 可选本地 spawn 目录（gitignore，不随仓发布）

# 泛请求“随便放点”的关键词（可免登录播放比例较高的类目）
FILLER_KEYWORDS = ["纯音乐", "轻音乐", "钢琴", "白噪音", "民谣", "爵士", "lo-fi 中文"]

# ---- AI 电台主持 ----
HOST_NAME = "Dsdio"  # 默认名；用户可在设置里改成自己填的英文名

_NAME_RE = re.compile(r"[^A-Za-z0-9 .'_-]")


def sanitize_host_name(raw: str) -> str:
    """主持名只允许英文/数字/空格及少量符号；其余字符剔除，长度封顶 24。"""
    return _NAME_RE.sub("", (raw or "")).strip()[:24]


def host_name() -> str:
    """当前 AI 主持的名字：设置里填了（且清洗后非空）就用它，否则用默认 HOST_NAME。"""
    return sanitize_host_name(load_settings().get("host_name", "")) or HOST_NAME


def get_api_key() -> str:
    """优先 .env，其次 settings.json 里手填的 key。"""
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    return (load_settings().get("api_key") or "").strip()


def get_weather_key() -> str:
    """OpenWeather API key：优先 .env，其次 settings.json。"""
    key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    if key:
        return key
    return (load_settings().get("weather_key") or "").strip()


# ---- 新闻源 ----
# category: 政治 / 财经 / 科技
# region:   cn(中文，对应 lang=zh) / intl(英文，对应 lang=en)
# 国外源在大陆通常需要代理；抓不到的源会被自动跳过。
FEEDS: list[dict] = [
    # —— 国内中文源（DeepSeek 会改写成英文播报）——
    {"name": "中新网·国内", "url": "https://www.chinanews.com.cn/rss/china.xml", "category": "Politics", "region": "cn"},
    {"name": "中新网·国际", "url": "https://www.chinanews.com.cn/rss/world.xml", "category": "Politics", "region": "cn"},
    {"name": "中新网·财经", "url": "https://www.chinanews.com.cn/rss/finance.xml", "category": "Finance", "region": "cn"},
    {"name": "IThome", "url": "https://www.ithome.com/rss/", "category": "Tech", "region": "cn"},
    {"name": "36氪", "url": "https://36kr.com/feed", "category": "Tech", "region": "cn"},
    # —— 国外英文源（需代理）——
    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "category": "Politics", "region": "intl"},
    {"name": "BBC Business", "url": "https://feeds.bbci.co.uk/news/business/rss.xml", "category": "Finance", "region": "intl"},
    {"name": "BBC Technology", "url": "https://feeds.bbci.co.uk/news/technology/rss.xml", "category": "Tech", "region": "intl"},
    {"name": "Guardian World", "url": "https://www.theguardian.com/world/rss", "category": "Politics", "region": "intl"},
    {"name": "Guardian Business", "url": "https://www.theguardian.com/business/rss", "category": "Finance", "region": "intl"},
    {"name": "Guardian Tech", "url": "https://www.theguardian.com/technology/rss", "category": "Tech", "region": "intl"},
    {"name": "NYT World", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "category": "Politics", "region": "intl"},
    {"name": "NYT Business", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "category": "Finance", "region": "intl"},
    {"name": "NYT Technology", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "category": "Tech", "region": "intl"},
    # —— 娱乐（国际源；国内娱乐 RSS 基本已失效）——
    {"name": "BBC Entertainment", "url": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml", "category": "Entertainment", "region": "intl"},
    {"name": "Guardian Culture", "url": "https://www.theguardian.com/culture/rss", "category": "Entertainment", "region": "intl"},
    {"name": "NYT Arts", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Arts.xml", "category": "Entertainment", "region": "intl"},
    {"name": "Variety", "url": "https://variety.com/feed/", "category": "Entertainment", "region": "intl"},
]

CATEGORIES = ["Politics", "Finance", "Tech", "Entertainment"]

# 新闻抓取时间窗口（小时）≈ 一个月，配合「开机后台预抓 + 缓存到次日 5 点」。
NEWS_FRESH_HOURS = 744

# ---- 本地语音识别模型目录 ----
MODELS_DIR = BASE_DIR / "models"

# ---- Kokoro TTS（本地 onnx，走 GPU/CPU）----
KOKORO_MODEL = MODELS_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES = MODELS_DIR / "voices-v1.0.bin"

# 模型下载地址（download_models.py 用）。可在 .env 用 KOKORO_MODEL_URL / KOKORO_VOICES_URL
# 覆盖成镜像，应对 GitHub releases 在大陆不稳的情况。
_KOKORO_MODEL_URL_DEFAULT = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx")
_KOKORO_VOICES_URL_DEFAULT = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin")


def _resolve_kokoro_model_url() -> str:
    return os.getenv("KOKORO_MODEL_URL", "").strip() or _KOKORO_MODEL_URL_DEFAULT


def _resolve_kokoro_voices_url() -> str:
    return os.getenv("KOKORO_VOICES_URL", "").strip() or _KOKORO_VOICES_URL_DEFAULT


KOKORO_MODEL_URL = _resolve_kokoro_model_url()
KOKORO_VOICES_URL = _resolve_kokoro_voices_url()

# ---- 本地语音识别（离线，不走 Google，没 VPN 也能用）----
# 离线只用 Vosk，专精中文（本地没 VPN 也查不了外网英文专有名词，无需双语）。
# 从 alphacephei 下载解压到 MODELS_DIR 下，国内免 VPN 可达。
VOSK_MODELS = {
    "cn": {"dir": "vosk-model-small-cn-0.22",
           "url": "https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip"},
}

# ---- sherpa-onnx · SenseVoice（默认离线引擎，替代 Vosk）----
# 中/英/粤/日/韩、非自回归、无 torch；int8 量化 ~229MB，解压后含 model.int8.onnx + tokens.txt。
# 默认从 GitHub releases 拉；大陆不稳时用 .env 的 SENSEVOICE_MODEL_URL 覆盖成镜像（如 ModelScope）。
SENSEVOICE_DIR = MODELS_DIR / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
_SENSEVOICE_URL_DEFAULT = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2")


def _resolve_sensevoice_url() -> str:
    return os.getenv("SENSEVOICE_MODEL_URL", "").strip() or _SENSEVOICE_URL_DEFAULT


SENSEVOICE_URL = _resolve_sensevoice_url()

# ---- DJ 音色 persona ----
# en=edge-tts 英文音；kokoro=Kokoro 对应音色。引擎在设置里切。
# zh 仅在偶发中文播报时用作回退（Dsdio 平时说英文）。
PERSONAS: dict[str, dict] = {
    # —— 女声 ——
    "warm_female": {  # 默认：磁性温暖女声
        "name": "AVA · warm female (US)",
        "zh": "zh-CN-XiaoxiaoNeural",
        "en": "en-US-AvaMultilingualNeural",
        "kokoro": "af_heart",
    },
    "bella_female": {
        "name": "BELLA · expressive female (US)",
        "zh": "zh-CN-XiaoxiaoNeural",
        "en": "en-US-JennyNeural",
        "kokoro": "af_bella",
    },
    "soft_female": {
        "name": "NICOLE · soft & close (US)",
        "zh": "zh-CN-XiaoyiNeural",
        "en": "en-US-MichelleNeural",
        "kokoro": "af_nicole",
    },
    "clear_female": {
        "name": "SARAH · clear & calm (US)",
        "zh": "zh-CN-XiaoxiaoNeural",
        "en": "en-US-AriaNeural",
        "kokoro": "af_sarah",
    },
    "bright_female": {
        "name": "EMMA · bright female (UK)",
        "zh": "zh-CN-XiaoyiNeural",
        "en": "en-US-EmmaMultilingualNeural",
        "kokoro": "bf_emma",
    },
    "brit_female": {
        "name": "ISABELLA · British female",
        "zh": "zh-CN-XiaoyiNeural",
        "en": "en-GB-SoniaNeural",
        "kokoro": "bf_isabella",
    },
    "aussie_female": {
        "name": "NATASHA · Aussie female",
        "zh": "zh-CN-XiaoxiaoNeural",
        "en": "en-AU-NatashaNeural",
        "kokoro": "af_sky",
    },
    # —— 男声 ——
    "warm_male": {
        "name": "ANDREW · warm male (US)",
        "zh": "zh-CN-YunxiNeural",
        "en": "en-US-AndrewMultilingualNeural",
        "kokoro": "am_michael",
    },
    "easy_male": {
        "name": "ADAM · easy male (US)",
        "zh": "zh-CN-YunyangNeural",
        "en": "en-US-GuyNeural",
        "kokoro": "am_adam",
    },
    "bold_male": {
        "name": "FENRIR · bold male (US)",
        "zh": "zh-CN-YunxiaNeural",
        "en": "en-US-RogerNeural",
        "kokoro": "am_fenrir",
    },
    "deep_male": {
        "name": "BRIAN · deep male (US)",
        "zh": "zh-CN-YunjianNeural",
        "en": "en-US-BrianMultilingualNeural",
        "kokoro": "bm_george",
    },
    "brit_male": {
        "name": "FABLE · British storyteller",
        "zh": "zh-CN-YunxiNeural",
        "en": "en-GB-RyanNeural",
        "kokoro": "bm_fable",
    },
}

# ---- 默认设置 ----
DEFAULT_SETTINGS = {
    "api_key": "",          # 留空则用 .env
    "host_name": "",        # AI 主持的名字（只限英文，留空则用默认 Dsdio）
    "user_name": "",        # 用户名：开机问候时 Dsdio 直接称呼（留空则不带名字）
    "persona": "warm_female",  # Dsdio 默认磁性女声
    "rate": -8,             # 语速百分比，负数更慢更松弛（聊天感）
    "volume": 0.85,          # 音乐音量
    "mic_enabled": True,     # 是否允许麦克风 / 语音输入
    "wake_word": "Dsdio",    # 迷你态语音唤醒词（留空则关闭唤醒监听；可填中文，逗号分隔多个）
    "recog_lang": "zh",      # 识别语言：zh / en（仅 online 引擎用；SenseVoice 自动多语言、Vosk 恒中文）
    "recog_engine": "sensevoice",  # 离线识别：sensevoice(sherpa-onnx,中/英/粤,免VPN) / vosk(旧,纯中文) / online(Google,需VPN)
    "tts_engine": "edge",    # 语音引擎：edge（在线，逐词精确）/ kokoro（本地，音色更自然）
    "weather_key": "",       # OpenWeather API key（留空则用 .env 的 OPENWEATHER_API_KEY）
    "weather_city": "",      # 城市（留空则按 IP 自动定位）
    "weather_country": "",   # 国家码（如 CN/US，配合城市精确定位）
}


def load_settings() -> dict:
    data = dict(DEFAULT_SETTINGS)
    if SETTINGS_FILE.exists():
        try:
            data.update(json.loads(SETTINGS_FILE.read_text("utf-8")))
        except Exception:
            pass
    return data


def save_settings(patch: dict) -> dict:
    # 整个 load→update→write 在锁内完成，否则两个并发 save 各读旧值、各写一遍会丢更新。
    with _settings_lock:
        data = load_settings()
        data.update(patch or {})
        atomic_write_text(SETTINGS_FILE, json.dumps(data, ensure_ascii=False, indent=2))
        return data


def personas_public() -> list[dict]:
    """给前端用的 persona 列表。"""
    return [{"id": pid, "name": p["name"]} for pid, p in PERSONAS.items()]
