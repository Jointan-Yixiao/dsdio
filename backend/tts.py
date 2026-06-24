"""TTS：两套引擎。
- edge：edge-tts（在线，给精确逐词时间轴）
- kokoro：Kokoro-82M 本地 onnx（音色更自然；逐词时间按词长估算）
synth() 统一返回 (audio_bytes, words, mime)。
"""
from __future__ import annotations

import asyncio
import io
import threading

import edge_tts

from . import config


# ================= edge-tts =================
def _rate_str(rate: int) -> str:
    return f"{int(rate):+d}%"


def voice_for(lang: str, persona_id: str) -> str:
    persona = config.PERSONAS.get(persona_id, config.PERSONAS["warm_female"])
    return persona["zh"] if lang == "zh" else persona["en"]


async def _synth_edge_async(text: str, voice: str, rate: int):
    communicate = edge_tts.Communicate(text, voice, rate=_rate_str(rate), boundary="WordBoundary")
    audio = bytearray()
    words: list[dict] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            start = chunk["offset"] / 10000.0          # 100ns -> ms
            dur = chunk["duration"] / 10000.0
            words.append({"text": chunk["text"], "start": start, "end": start + dur})
    return bytes(audio), words


def _synth_edge(text: str, voice: str, rate: int):
    audio, words = asyncio.run(_synth_edge_async(text, voice, rate))
    return audio, words, "audio/mpeg"


# ================= Kokoro (本地 onnx) =================
_kokoro = None
_kokoro_lock = threading.Lock()


def _get_kokoro():
    global _kokoro
    if _kokoro is None:
        with _kokoro_lock:
            if _kokoro is None:
                import espeakng_loader
                from phonemizer.backend.espeak.wrapper import EspeakWrapper
                EspeakWrapper.set_library(espeakng_loader.get_library_path())
                espeakng_loader.make_library_available()
                from kokoro_onnx import Kokoro
                _kokoro = Kokoro(str(config.KOKORO_MODEL), str(config.KOKORO_VOICES))
    return _kokoro


def warm_kokoro() -> bool:
    """启动时预加载模型（首次推理才不卡）。返回是否成功。"""
    try:
        _get_kokoro()
        return True
    except Exception:
        return False


def _estimate_words(text: str, total_ms: float) -> list[dict]:
    """Kokoro 不给逐词时间，用词长比例估算，驱动'逐词点亮'。"""
    toks = text.split()
    if not toks:
        return []
    weights = [max(1, len(t)) for t in toks]
    total_w = sum(weights)
    words, acc = [], 0.0
    for tok, w in zip(toks, weights):
        dur = total_ms * w / total_w
        words.append({"text": tok, "start": acc, "end": acc + dur})
        acc += dur
    return words


def _synth_kokoro(text: str, voice: str, rate: int):
    import soundfile as sf
    k = _get_kokoro()
    speed = max(0.5, min(1.5, 1.0 + rate / 100.0))
    samples, sr = k.create(text, voice=voice, speed=speed, lang="en-us")
    total_ms = len(samples) / sr * 1000.0
    words = _estimate_words(text, total_ms)
    buf = io.BytesIO()
    sf.write(buf, samples, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue(), words, "audio/wav"


# ================= dispatch =================
def synth(text: str, lang: str, persona_id: str, rate: int = 0) -> tuple[bytes, list[dict], str]:
    persona = config.PERSONAS.get(persona_id, config.PERSONAS["warm_female"])
    engine = config.load_settings().get("tts_engine", "edge")
    if engine == "kokoro" and config.KOKORO_MODEL.exists():
        try:
            return _synth_kokoro(text, persona.get("kokoro", "af_heart"), rate)
        except Exception:
            pass  # Kokoro 出错时回退 edge
    voice = persona["zh"] if lang == "zh" else persona["en"]
    return _synth_edge(text, voice, rate)
