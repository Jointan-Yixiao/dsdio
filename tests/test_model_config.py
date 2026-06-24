"""分享适配: DeepSeek 模型名支持 env 覆盖（默认仍 deepseek-v4-flash）。

别人的 DeepSeek 账号不一定有 deepseek-v4-flash，得能在 .env 里用 DEEPSEEK_MODEL 改成
自己账号可用的（如 deepseek-chat），否则首跑就报错。
"""
from backend import config


def test_resolve_model_default(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    assert config._resolve_model() == "deepseek-v4-flash"


def test_resolve_model_env_override(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    assert config._resolve_model() == "deepseek-chat"


def test_resolve_model_blank_env_falls_back(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_MODEL", "   ")     # 空白当没填
    assert config._resolve_model() == "deepseek-v4-flash"
