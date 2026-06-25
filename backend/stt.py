"""本地/离线语音识别 —— 不走 Google，没 VPN 也能用。

离线引擎只用 **Vosk·专精中文**（本地没 VPN 也查不了外网英文专有名词，无需双语/英文）：
- vosk：vosk-model-small-cn，轻、省、免 VPN，~2s/句。
（设置里另有 online = 浏览器 Web Speech，走 Google 需 VPN，前端处理，可识别英文。）

麦克风用 sounddevice 采集 16k 单声道，webrtcvad 做静音切句：
- 唤醒：常驻监听，按段识别，命中唤醒词就回调（并自动暂停，交给前端念问候 + 收指令）；
- 收指令：listen_once 等你开口（standby）、说话停顿够久（gap）即视为说完，整段转文字返回。

模型按需懒加载；Vosk 模型从 alphacephei 直链下载（国内免 VPN）。
"""
from __future__ import annotations

import json
import queue
import re
import threading
import time

from . import config

SR = 16000                       # 采样率
FRAME_MS = 30                    # VAD 帧长（webrtcvad 只接受 10/20/30ms）
FRAME = SR * FRAME_MS // 1000    # 每帧样本数 = 480
FRAME_BYTES = FRAME * 2          # int16 = 2 bytes/样本

_PUNCT = re.compile(r"[\s,.!?~·　-〿＀-￯]+")


def _norm(s: str) -> str:
    """归一化：转小写、去空格标点，便于"包含"匹配唤醒词。"""
    return _PUNCT.sub("", (s or "").lower())


def _settings() -> dict:
    return config.load_settings()


def engine() -> str:
    """离线引擎名。老配置里的 whisper 已下线，归一到默认离线引擎 sensevoice。"""
    eng = _settings().get("recog_engine", "sensevoice")
    return "sensevoice" if eng == "whisper" else eng


# ============================ 模型下载（从 alphacephei 直链，免 VPN）============================
def ensure_vosk(lang_code: str = "cn") -> None:
    """缺模型就从 alphacephei 下载 zip 解压（vosk-model-small-cn）。"""
    import io
    import zipfile
    import requests
    info = config.VOSK_MODELS[lang_code]
    mdir = config.MODELS_DIR / info["dir"]
    if mdir.exists():
        return
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with requests.get(info["url"], stream=True, timeout=120, allow_redirects=True) as r:
        r.raise_for_status()
        buf = io.BytesIO()
        for chunk in r.iter_content(chunk_size=1 << 20):
            buf.write(chunk)
    buf.seek(0)
    with zipfile.ZipFile(buf) as z:
        z.extractall(config.MODELS_DIR)   # zip 内含顶层目录 = info["dir"]


def _fetch_tarbz2(url: str, dest_root) -> None:
    """下载 tar.bz2 到内存、解压到 dest_root（tar 内含顶层目录 = 模型目录名）。"""
    import io
    import tarfile
    import requests
    dest_root.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=300, allow_redirects=True) as r:
        r.raise_for_status()
        buf = io.BytesIO()
        for chunk in r.iter_content(chunk_size=1 << 20):
            buf.write(chunk)
    buf.seek(0)
    with tarfile.open(fileobj=buf, mode="r:bz2") as t:
        t.extractall(dest_root)


def ensure_sensevoice(fetch=None) -> None:
    """缺模型就下载 SenseVoice tar.bz2 解压到 MODELS_DIR；已存在则跳过。fetch 可注入（测试用）。"""
    if (config.SENSEVOICE_DIR / "model.int8.onnx").exists():
        return
    (fetch or _fetch_tarbz2)(config.SENSEVOICE_URL, config.MODELS_DIR)


# ============================ 引擎：模型加载 + 转写 ============================
_lock = threading.Lock()
_vosk: dict = {}        # lang_code -> vosk.Model
_sensevoice: dict = {}  # "rec" -> sherpa_onnx.OfflineRecognizer（单例）


def _load_vosk(lang_code: str = "cn"):
    """加载 Vosk 中文模型；缺失则抛 FileNotFoundError（前端提示去下载）。"""
    with _lock:
        if lang_code not in _vosk:
            import vosk
            vosk.SetLogLevel(-1)
            mdir = config.MODELS_DIR / config.VOSK_MODELS[lang_code]["dir"]
            if not mdir.exists():
                raise FileNotFoundError(f"Vosk 模型未下载：{mdir}")
            _vosk[lang_code] = vosk.Model(str(mdir))
        return _vosk[lang_code]


def is_ready(eng: str | None = None) -> bool:
    eng = eng or engine()
    if eng == "vosk":
        return "cn" in _vosk
    if eng == "sensevoice":
        return "rec" in _sensevoice
    return True  # online 不需要本地模型


def prepare(eng: str | None = None) -> dict:
    """后台加载所选引擎模型（首次可能要下载），返回是否就绪。"""
    eng = eng or engine()
    try:
        if eng == "vosk":
            ensure_vosk("cn")
            _load_vosk("cn")
        elif eng == "sensevoice":
            ensure_sensevoice()
            _load_sensevoice()
        return {"ok": True, "engine": eng, "ready": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "engine": eng, "ready": False, "error": str(e)}


def _vosk_text(pcm: bytes) -> str:
    """专精中文：只用中文模型转写。"""
    from vosk import KaldiRecognizer
    rec = KaldiRecognizer(_load_vosk("cn"), SR)
    rec.SetWords(True)
    rec.AcceptWaveform(pcm)
    res = json.loads(rec.FinalResult())
    return (res.get("text") or "").strip()


def _load_sensevoice():
    """加载 sherpa-onnx SenseVoice OfflineRecognizer（单例）；缺模型抛 FileNotFoundError。"""
    with _lock:
        if "rec" not in _sensevoice:
            import sherpa_onnx
            model = config.SENSEVOICE_DIR / "model.int8.onnx"
            tokens = config.SENSEVOICE_DIR / "tokens.txt"
            if not model.exists():
                raise FileNotFoundError(f"SenseVoice 模型未下载：{config.SENSEVOICE_DIR}")
            _sensevoice["rec"] = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(model), tokens=str(tokens),
                num_threads=2, use_itn=True, language="auto", debug=False)
        return _sensevoice["rec"]


def _pcm_to_float(pcm: bytes):
    """16k int16 PCM bytes → float32 ndarray（[-1,1]，sherpa-onnx 要的入参格式）。"""
    import numpy as np
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def _sensevoice_text(pcm: bytes) -> str:
    """用 SenseVoice 把一段 16k int16 PCM 转文字（中/英/粤/日/韩自动识别）。"""
    rec = _load_sensevoice()
    s = rec.create_stream()
    s.accept_waveform(SR, _pcm_to_float(pcm))
    rec.decode_stream(s)
    return (s.result.text or "").strip()


def transcribe(pcm: bytes, lang: str | None = None) -> str:
    """把一段 16k int16 PCM 转成文字（默认 sherpa-onnx·SenseVoice；选了 vosk 才走 Vosk）。
    lang 仅为兼容旧调用，忽略。识别异常一律降级空串（语音是可选项，别炸到主路径）。"""
    try:
        return _vosk_text(pcm) if engine() == "vosk" else _sensevoice_text(pcm)
    except Exception:  # noqa: BLE001
        return ""


# ============================ 麦克风：VAD 切句 ============================
def _vad():
    import webrtcvad
    return webrtcvad.Vad(2)   # 0~3，越大越激进（更易判成静音）


def _open_stream(cb):
    import sounddevice as sd
    return sd.RawInputStream(samplerate=SR, blocksize=FRAME, dtype="int16",
                             channels=1, callback=cb)


def listen_once(standby_ms: int = 5000, gap_ms: int = 2000, lang: str | None = None) -> str:
    """收一句话：等你开口（最多 standby_ms），开口后停顿超过 gap_ms 视为说完，整段转文字返回。
    没开口或没识别到内容返回空串。"""
    q: queue.Queue = queue.Queue()
    vad = _vad()
    seg: list[bytes] = []
    started = False
    t0 = time.time()
    last = t0
    MAX_S = 20  # 单句安全上限
    stream = _open_stream(lambda indata, frames, t, s: q.put(bytes(indata)))
    stream.start()
    try:
        while True:
            try:
                data = q.get(timeout=0.3)
            except queue.Empty:
                if not started and time.time() - t0 > standby_ms / 1000:
                    return ""
                continue
            if len(data) != FRAME_BYTES:
                continue
            now = time.time()
            speech = vad.is_speech(data, SR)
            if not started:
                if speech:
                    started = True
                    seg.append(data)
                    last = now
                elif now - t0 > standby_ms / 1000:
                    return ""
            else:
                seg.append(data)
                if speech:
                    last = now
                elif now - last > gap_ms / 1000:
                    break
                if now - t0 > MAX_S:
                    break
    finally:
        try:
            stream.stop(); stream.close()
        except Exception:
            pass
    pcm = b"".join(seg)
    if len(pcm) < SR * 2 * 0.2:   # 不足 0.2s，当没说
        return ""
    return transcribe(pcm)


# ---- 唤醒：常驻监听线程 ----
_wake_run = False        # 线程是否该存活
_wake_paused = False     # 临时暂停（命中后到收完指令期间）
_speaking = False        # Dsdio 正在说话 → 丢弃这段音频，别把自己当输入
_on_wake = None          # 命中唤醒词的回调（前端 evaluate_js）
_WAKE_END_SIL = 8        # 连续静音帧数 ~0.24s 即认为一段说完，去识别
_MIN_SEG_S = 0.3         # 太短的段不识别


def _wake_words() -> list[str]:
    raw = _settings().get("wake_word", "") or ""
    return [w for w in (_norm(x) for x in re.split(r"[,，]", raw)) if w]


def set_speaking(on: bool) -> None:
    global _speaking
    _speaking = bool(on)


def wake_resume() -> None:
    global _wake_paused
    _wake_paused = False


def wake_stop() -> None:
    global _wake_run
    _wake_run = False


def wake_start(on_wake) -> None:
    """启动常驻唤醒监听（离线引擎用）。on_wake：命中唤醒词时调用（无参）。"""
    global _wake_run, _wake_paused, _on_wake
    _on_wake = on_wake
    if _wake_run:
        return
    _wake_run = True
    _wake_paused = False
    threading.Thread(target=_wake_loop, daemon=True).start()


def _wake_loop() -> None:
    words = _wake_words()
    if not words:
        return
    q: queue.Queue = queue.Queue()
    vad = _vad()
    seg: list[bytes] = []
    sil = 0
    stream = None
    try:
        while _wake_run:
            if _wake_paused:
                if stream is not None:
                    try:
                        stream.stop(); stream.close()
                    except Exception:
                        pass
                    stream = None
                seg = []; sil = 0
                time.sleep(0.05)
                continue
            if stream is None:
                with q.mutex:
                    q.queue.clear()
                stream = _open_stream(lambda indata, frames, t, s: q.put(bytes(indata)))
                stream.start()
            try:
                data = q.get(timeout=0.3)
            except queue.Empty:
                continue
            if _speaking or len(data) != FRAME_BYTES:   # 自己在说话就丢弃
                seg = []; sil = 0
                continue
            if vad.is_speech(data, SR):
                seg.append(data); sil = 0
            elif seg:
                sil += 1
                if sil >= _WAKE_END_SIL:
                    pcm = b"".join(seg); seg = []; sil = 0
                    if len(pcm) >= SR * 2 * _MIN_SEG_S:
                        txt = transcribe(pcm)
                        n = _norm(txt)
                        if n and any(w in n for w in words):
                            _trigger()
                            # _trigger 已置暂停，下个循环会关流
    finally:
        if stream is not None:
            try:
                stream.stop(); stream.close()
            except Exception:
                pass


def _trigger() -> None:
    global _wake_paused
    _wake_paused = True
    cb = _on_wake
    if cb:
        try:
            cb()
        except Exception:
            pass
