"""Bug2: stt.py / tts.py 懒加载的第三方依赖必须在 requirements 里声明。

否则新环境 `pip install -r requirements.txt` 后语音输入(Vosk)和 Kokoro TTS 会被宽 except
静默吞掉 —— 换机即丢功能、还查不出原因。这个守卫防止此类遗漏复发。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 懒加载 import 名 → pip 包名（注意有几个包名和 import 名不一样）
IMPORT_TO_PKG = {
    "requests": "requests",
    "vosk": "vosk",
    "sherpa_onnx": "sherpa-onnx",
    "sounddevice": "sounddevice",
    "webrtcvad": "webrtcvad-wheels",
    "kokoro_onnx": "kokoro-onnx",
    "soundfile": "soundfile",
    "espeakng_loader": "espeakng-loader",
    "phonemizer": "phonemizer-fork",
}


def _all_declared() -> str:
    text = (ROOT / "requirements.txt").read_text("utf-8")
    voice = ROOT / "requirements-voice.txt"
    if voice.exists():
        text += "\n" + voice.read_text("utf-8")
    return text.lower()


def test_all_lazy_voice_deps_declared():
    declared = _all_declared()
    missing = [pkg for pkg in IMPORT_TO_PKG.values() if pkg.lower() not in declared]
    assert not missing, f"requirements 缺这些懒加载语音依赖: {missing}"
