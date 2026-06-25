"""一键拉取可选的本地模型，放进 models/。

- Kokoro 本地音色：kokoro-v1.0.onnx (~310MB) + voices-v1.0.bin。不下载也能用——
  默认走在线 edge-tts；想要本地、更自然的音色才需要它。
- SenseVoice 离线识别（~229MB）：首次语音时会自动下载，这里顺带预拉一份（也可双击 get-voice-model.bat）。

用法：
    .venv\\Scripts\\python download_models.py

模型地址可在 .env 用 KOKORO_MODEL_URL / KOKORO_VOICES_URL / SENSEVOICE_MODEL_URL 覆盖（GitHub releases 在大陆不稳时换镜像）。
"""
from __future__ import annotations

import shutil
import sys
import urllib.request
from pathlib import Path

from backend import config


def _download(url: str, dest: Path) -> None:
    """下到同目录 .part 临时文件再改名，避免中断留下半截文件被当成"已下好"。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"  下载 {url}\n     → {dest}")
    with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    tmp.replace(dest)


def ensure_kokoro(download=_download) -> list[str]:
    """下载缺失的 Kokoro 模型文件，返回本次实际下载的文件名（已存在且非空的跳过）。"""
    fetched: list[str] = []
    for url, dest in ((config.KOKORO_MODEL_URL, config.KOKORO_MODEL),
                      (config.KOKORO_VOICES_URL, config.KOKORO_VOICES)):
        if dest.exists() and dest.stat().st_size > 0:
            print(f"  已存在，跳过：{dest.name}")
            continue
        download(url, dest)
        fetched.append(dest.name)
    return fetched


def main() -> int:
    print("[*] 检查 Kokoro 本地音色模型 …")
    try:
        got = ensure_kokoro()
    except Exception as e:  # noqa: BLE001
        print(f"[x] Kokoro 模型下载失败：{e}")
        print("    可手动从 https://github.com/thewh1teagle/kokoro-onnx/releases 下载这两个文件放进 "
              "models/，或在 .env 设 KOKORO_MODEL_URL / KOKORO_VOICES_URL 换镜像后重试。")
        return 1
    print(f"[OK] Kokoro 就绪（本次下载：{got or '无，已齐全'}）")

    print("[*] 预拉 SenseVoice 离线识别模型（默认引擎，约 229MB）…")
    try:
        from backend import stt
        stt.ensure_sensevoice()
        print("[OK] SenseVoice 就绪")
    except Exception as e:  # noqa: BLE001
        print(f"[!] SenseVoice 预拉失败（不影响——首次语音时会再自动下载；"
              f"GitHub 在大陆不稳时用 .env 的 SENSEVOICE_MODEL_URL 换镜像）：{e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
