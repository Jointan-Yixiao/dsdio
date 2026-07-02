# CLAUDE.md — Dsdio 维护指南（给 AI 助手 / 新贡献者）

桌面 AI 电台主持挂件（**仅 Windows 10/11**）：pywebview(WebView2) + Python 后端 + DeepSeek 流式对话，
点歌走本地 Node 服务（网易云 API + UNM 解锁），edge-tts/Kokoro 语音，新闻 RSS，离线 SenseVoice 识别（sherpa-onnx，中/英/粤；Vosk 保留可选）。

## 跑 / 测

```
.venv\Scripts\python app.py                         # 启动（或双击 run.bat）
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest                       # 全套单测（tests/，根目录 conftest.py 加 sys.path）
```

## 约定（改前必读）

- **测试先行（TDD）**：新功能 / 改 bug 一律先写失败测试再实现。纯逻辑用 pytest；pywebview/ctypes/前端
  这类 GUI 胶水在 Python 接缝处注入/mock 后测决策逻辑，不为 GUI 硬造大量 mock。
- **秘密与大文件绝不提交**：`.env`、`settings.json`(含明文 key)、`models/`(数百 MB)、`node_modules/`、
  `.webview/`、`long_memory.json`/`short_memory.json` 都在 `.gitignore`。
  ⚠️ `.gitignore` 的 `#` 注释**必须独占一行**——行尾内联注释会让 pattern 失效（踩过这个坑，导致 .webview 差点泄漏）。
  改完 `.gitignore` 用 `git add -An | grep -iE "\.env|settings|models/|node_modules|\.webview|_memory"` 验证一遍。
- **DeepSeek 模型**：`config.DEEPSEEK_MODEL` 读 env `DEEPSEEK_MODEL`，默认 `deepseek-v4-flash`。
- **配置/记忆写盘**：用 `config.atomic_write_text`(临时文件+os.replace) + 锁，别直接 `write_text`，避免崩溃截断丢 key。
- **对话代号 gen**：前端 `voiceGen` 是唯一真相源，传进 `Api.chat(text, gen)` / `startup_mix(gen)`；逐句推送与
  后台续解都用同一 gen，别在后端另起一套计数器。
- **pywebview js_api**：`Api` 的内部属性必须 `_` 前缀，否则 pywebview 暴露时会递归遍历原生 window 直到崩溃。
- **语音可选**：`requirements-voice.txt`(sherpa-onnx·SenseVoice / Kokoro 等)是可选项，懒加载 + 宽 except；
  新增懒加载第三方依赖务必同步进该文件（有 `tests/test_requirements_complete.py` 守卫）。
- **Windows 专有 API**（`win_effects.py` 的 ctypes、`autostart.py` 的 winreg、`app.py` 的 RegisterHotKey）都做了
  非 Windows 静默降级；新增此类调用照此包好。
- **含中文的 `.bat` 必须存 GBK（ANSI/cp936），绝不能 UTF-8**——cmd 按系统 GBK 解析 bat 文件，UTF-8 的
  三字节中文会错位、打散 `if(...)` 块导致语法错误 → 双击窗口闪一下就退（踩过这个坑：4 个 bat 全中招）。
  `chcp 65001` 救不了（只改输出代码页，改不了 cmd 解析 bat 用的编码）。有 `tests/test_bat_encoding.py` 守卫。

## 模块速览

`app.py` 入口(窗口/JS桥/逐句合成管线) · `backend/host.py` DeepSeek 对话 · `news.py` RSS+缓存自愈重抓 ·
`music.py` 网易云+UNM(免登录) · `commands.py` 播放控制命令解析(下一首/暂停等，前端直连不走 LLM) ·
`memory.py` 用户记忆(每10轮提炼) · `tts.py`/`stt.py` 语音 ·
`weather.py` 天气 · `win_effects.py`/`autostart.py` Win32 · `frontend/` 玻璃 UI。

## 提交

提交信息用中文；改完跑 `pytest` 确认全绿；秘密/大文件别进暂存（先 `git status` 扫一眼）。
