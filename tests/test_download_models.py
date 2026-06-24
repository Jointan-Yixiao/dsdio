"""分享适配: download_models.py 一键拉 Kokoro 模型。

已存在的文件跳过、只下缺失的 —— 让用户「拉下来跑一下脚本」即可获得本地音色，
且重复跑不会重复下载 340MB。
"""
import download_models
from backend import config


def _point_models_at(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "KOKORO_MODEL", tmp_path / "kokoro-v1.0.onnx")
    monkeypatch.setattr(config, "KOKORO_VOICES", tmp_path / "voices-v1.0.bin")


def test_downloads_all_when_missing(tmp_path, monkeypatch):
    _point_models_at(tmp_path, monkeypatch)
    fetched = download_models.ensure_kokoro(download=lambda url, dest: None)
    assert set(fetched) == {"kokoro-v1.0.onnx", "voices-v1.0.bin"}


def test_skips_existing_downloads_only_missing(tmp_path, monkeypatch):
    _point_models_at(tmp_path, monkeypatch)
    (tmp_path / "kokoro-v1.0.onnx").write_bytes(b"already here")   # 已存在且非空
    calls = []
    fetched = download_models.ensure_kokoro(download=lambda url, dest: calls.append(dest.name))
    assert fetched == ["voices-v1.0.bin"]          # 只下缺的
    assert calls == ["voices-v1.0.bin"]
    assert "kokoro-v1.0.onnx" not in fetched         # 已存在跳过


def test_zero_byte_file_is_redownloaded(tmp_path, monkeypatch):
    _point_models_at(tmp_path, monkeypatch)
    (tmp_path / "kokoro-v1.0.onnx").write_bytes(b"")   # 空文件 = 上次没下完，应重下
    fetched = download_models.ensure_kokoro(download=lambda url, dest: None)
    assert "kokoro-v1.0.onnx" in fetched


def test_model_urls_overridable_via_env(monkeypatch):
    monkeypatch.setenv("KOKORO_MODEL_URL", "https://mirror.example/k.onnx")
    assert config._resolve_kokoro_model_url() == "https://mirror.example/k.onnx"
