"""音源换成 Enhanced 分支（@neteasecloudmusicapienhanced/api）。

Binaryify 原版 NeteaseCloudMusicApi 早已 archive、停更，改用社区半重构增强分支
@neteasecloudmusicapienhanced/api（保留 serveNcmApi 与全部路由）。这个守卫防止
有人误 `npm install NeteaseCloudMusicApi` 把停更的原版装回来。
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MUSIC_API = ROOT / "music-api"
ENHANCED = "@neteasecloudmusicapienhanced/api"
BINARYIFY = "NeteaseCloudMusicApi"  # 停更的原版（精确包名，PascalCase）


def test_package_json_uses_enhanced_not_binaryify():
    deps = json.loads((MUSIC_API / "package.json").read_text("utf-8")).get("dependencies", {})
    assert ENHANCED in deps, f"music-api 应依赖 Enhanced 分支 {ENHANCED}"
    assert BINARYIFY not in deps, f"不应再依赖停更的 Binaryify 原版 {BINARYIFY}"


def test_server_js_requires_enhanced():
    src = (MUSIC_API / "server.js").read_text("utf-8")
    assert ENHANCED in src, f"server.js 应 require {ENHANCED}"
    assert f"require('{BINARYIFY}')" not in src, "server.js 不应再 require 停更的原版"
