"""版权守卫：公开仓不得出现网易云 Node / UNM 的代码物料。

音源改为用户自部署 + MUSIC_API_BASE 注入；仓库里任何被 git 跟踪的 package.json
都不得声明 NeteaseCloudMusicApi / Enhanced / UNM 依赖，music-api/ 与 unm-api/
目录也不得被跟踪。踩线即红。
"""
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
BANNED = ("neteasecloudmusicapi", "@neteasecloudmusicapienhanced", "@unblockneteasemusic")


def _tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    return out.stdout.splitlines()


def test_no_music_source_dirs_tracked():
    tracked = _tracked_files()
    bad = [f for f in tracked if f.startswith("music-api/") or f.startswith("unm-api/")]
    assert not bad, f"这些音源目录文件不应被 git 跟踪（版权风险）：{bad[:5]}"


def test_no_tracked_packagejson_declares_ncm_or_unm():
    offenders = []
    for f in _tracked_files():
        if f.endswith("package.json"):
            text = (ROOT / f).read_text("utf-8", errors="ignore").lower()
            if any(b in text for b in BANNED):
                offenders.append(f)
    assert not offenders, f"这些被跟踪的 package.json 含 NCM/UNM 依赖，不能上仓：{offenders}"
