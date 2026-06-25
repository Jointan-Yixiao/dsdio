"""离线识别从 Vosk 换成 sherpa-onnx·SenseVoice（中/英/粤/日/韩、非自回归、无 torch）。

纯逻辑全部钉死：模型配置（含 env 覆盖镜像）、PCM→float32 转换、引擎分派、降级。
真实 sherpa_onnx 识别需装包 + 模型，由真机实跑验证；这里只测决策逻辑（接缝处 mock）。
"""
import numpy as np
import pytest

from backend import config, stt


# ---------- config：SenseVoice 模型配置 ----------
def test_sensevoice_dir_under_models():
    assert config.SENSEVOICE_DIR.parent == config.MODELS_DIR
    assert "sense-voice" in config.SENSEVOICE_DIR.name


def test_sensevoice_url_default_is_int8_tarbz2(monkeypatch):
    monkeypatch.delenv("SENSEVOICE_MODEL_URL", raising=False)
    url = config._resolve_sensevoice_url()
    assert "sense-voice" in url and "int8" in url
    assert url.endswith(".tar.bz2")


def test_sensevoice_url_env_override(monkeypatch):
    monkeypatch.setenv("SENSEVOICE_MODEL_URL", "https://mirror.example/sv.tar.bz2")
    assert config._resolve_sensevoice_url() == "https://mirror.example/sv.tar.bz2"


def test_default_engine_is_sensevoice():
    assert config.DEFAULT_SETTINGS["recog_engine"] == "sensevoice"


# ---------- stt：PCM→float32（纯逻辑） ----------
def test_pcm_to_float_range_and_dtype():
    pcm = np.array([0, 32767, -32768], dtype=np.int16).tobytes()
    out = stt._pcm_to_float(pcm)
    assert out.dtype == np.float32
    assert len(out) == 3
    assert out.min() >= -1.0 and out.max() <= 1.0
    assert abs(float(out[0])) < 1e-6          # 0 → 0
    assert out[1] > 0.99                        # 满幅正
    assert out[2] < -0.99                       # 满幅负


def test_pcm_to_float_empty():
    assert len(stt._pcm_to_float(b"")) == 0


# ---------- stt：transcribe 引擎分派 + 降级 ----------
def test_transcribe_uses_sensevoice_by_default(monkeypatch):
    monkeypatch.setattr(stt, "engine", lambda: "sensevoice")
    monkeypatch.setattr(stt, "_sensevoice_text", lambda pcm: "你好世界")
    monkeypatch.setattr(stt, "_vosk_text", lambda pcm: "WRONG")
    assert stt.transcribe(b"\x00\x00") == "你好世界"


def test_transcribe_uses_vosk_when_selected(monkeypatch):
    monkeypatch.setattr(stt, "engine", lambda: "vosk")
    monkeypatch.setattr(stt, "_sensevoice_text", lambda pcm: "WRONG")
    monkeypatch.setattr(stt, "_vosk_text", lambda pcm: "hello")
    assert stt.transcribe(b"\x00\x00") == "hello"


def test_transcribe_degrades_to_empty_on_error(monkeypatch):
    monkeypatch.setattr(stt, "engine", lambda: "sensevoice")

    def boom(pcm):
        raise RuntimeError("model missing")

    monkeypatch.setattr(stt, "_sensevoice_text", boom)
    assert stt.transcribe(b"\x00\x00") == ""        # 宽 except，不让识别异常炸到调用方


# ---------- stt：ensure_sensevoice 下载/跳过分发（注入 fetch，不真下载） ----------
def test_ensure_sensevoice_skips_when_present(monkeypatch, tmp_path):
    mdir = tmp_path / "sv"
    mdir.mkdir()
    (mdir / "model.int8.onnx").write_bytes(b"x")     # 模型已在
    monkeypatch.setattr(config, "SENSEVOICE_DIR", mdir)
    calls = []
    stt.ensure_sensevoice(fetch=lambda url, root: calls.append(url))
    assert calls == []                                # 已存在 → 不下载


def test_ensure_sensevoice_downloads_when_missing(monkeypatch, tmp_path):
    mdir = tmp_path / "sv"                             # 不创建 → 缺失
    monkeypatch.setattr(config, "SENSEVOICE_DIR", mdir)
    monkeypatch.setattr(config, "SENSEVOICE_URL", "https://mirror.example/sv.tar.bz2")
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path)
    calls = []
    stt.ensure_sensevoice(fetch=lambda url, root: calls.append((url, root)))
    assert calls == [("https://mirror.example/sv.tar.bz2", tmp_path)]
