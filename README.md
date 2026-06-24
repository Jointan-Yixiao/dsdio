# Dsdio · 桌面 AI 电台主持挂件

一个本地运行的桌面小挂件：手机屏幕大小、无边框、置顶、Win11 玻璃磨砂外观。
你用对话（打字或语音）跟 AI 主持 **Dsdio** 互动——闲聊、点歌（网易云）、或让她用聊天的口吻
聊今天的新闻。她总说英文，但听得懂中文。

- 🎙️ **对话主持**：DeepSeek 流式生成，边说边逐句合成语音、逐词高亮
- 🎵 **点歌即放**：网易云搜索 + UNM 解锁（免登录），灰色/VIP 也能找回原版地址
- 📰 **聊新闻**：各大媒体 RSS（中新网 + BBC/Guardian/NYT 等），抓取后交给 Dsdio 挑重点闲聊
- 🌦️ **天气陪伴**（可选）：按当地天气和时段问候、选歌
- 🎤 **语音交互**（可选）：离线 Vosk 中文识别 + 唤醒词；本地 Kokoro 音色
- 🪟 **玻璃挂件**：亚克力磨砂、可拖动置顶，最小化成桌面右下角迷你停靠条

> ⚠️ **仅支持 Windows 10/11**（依赖 WebView2、Win32 亚克力磨砂、注册表自启等）。

## 前置要求

- **Windows 10/11**
- **Python 3.10+**（[下载](https://www.python.org/downloads/)，安装时勾选 Add to PATH）
- **DeepSeek API Key**（[申请](https://platform.deepseek.com/)）——对话/新闻/记忆都靠它
- **Node.js 18+**（[下载](https://nodejs.org/)）——*仅音乐功能需要*；不装也能聊天 / 听新闻

## 快速开始

1. **填 Key**：复制 `.env.example` 为 `.env`，填入 `DEEPSEEK_API_KEY`（也可启动后在 ⚙ 设置里填）。
2. **双击 `run.bat`**：首次自动建虚拟环境、装 Python 依赖、装 Node 音乐服务依赖（需联网），之后直接启动。
   首次启动后会在**桌面创建「Dsdio」快捷方式**（指向 `pythonw`，**启动无黑框**）；以后双击它即可，`run.bat` 仅用于重装/更新。
3. 开播后直接在底部输入框跟 Dsdio 说话，或点 🎤 语音；想听新闻就问她「今天有什么新闻」。

> 手动启动：
> ```
> python -m venv .venv
> .venv\Scripts\python -m pip install -r requirements.txt
> cd music-api && npm install && cd ..      :: 音乐功能（可选）
> cd unm-api  && npm install && cd ..        :: 音乐功能（可选）
> .venv\Scripts\python app.py
> ```

<details>
<summary>🔰 <b>小白完整教程（没装过 Python / 不会命令行，点开看这里）</b></summary>

> 全程**不用敲命令**，能双击就能用。

**第一步 · 装两个运行环境（只需一次）**

1. **装 Python**：去 [python.org/downloads](https://www.python.org/downloads/) 下载并双击安装。
   ⚠️ 安装第一屏**务必勾选最下面的 “Add python.exe to PATH”**，再点 Install。不勾后面会失败。
2. **装 Node.js**（只为「点歌」；不想要音乐可跳过）：去 [nodejs.org](https://nodejs.org/) 下载 LTS 版，一路 Next。
3. *(Win10 用户)* 若之后窗口打不开，搜 “WebView2 Runtime” 装一下；Win11 自带，无需理会。

**第二步 · 拿一个 DeepSeek Key（聊天的大脑）**

4. 打开 [platform.deepseek.com](https://platform.deepseek.com/) 注册登录 → **API Keys** → 新建 → 复制那串
   `sk-...`（只显示一次，先存记事本）。该 API 需充少量费用。

**第三步 · 跑起来（双击就行）**

5. 双击 **`run.bat`**。首次会自动建环境、装依赖（几分钟、滚字正常），然后**自动弹出一个记事本**。
6. 在记事本里把 `DEEPSEEK_API_KEY=` 后面**粘上你的 key**（变成 `DEEPSEEK_API_KEY=sk-xxxx`），**Ctrl+S 保存、关闭**。
7. **再双击一次 `run.bat`** → 桌面右侧弹出玻璃挂件，Dsdio 开口打招呼，就成了。
   这次还会在**桌面自动建一个「Dsdio」快捷方式**——以后**双击桌面快捷方式启动即可，不再弹黑框**；
   `run.bat` 只在重装 / 更新依赖时才需要再用。

**第四步 · 怎么用**

- 底部输入框**打字**跟她聊（回车发送）；想听新闻就问「今天有什么新闻」。
- 想点歌直接说「放首周杰伦」「来点轻音乐」（需第一步装了 Node）。
- **⚙ 设置**里换音色 / 语速 / 填天气；**📌** 置顶；最小化成右下角小条，按 **`Ctrl+Alt+D`** 还原。

**第五步 · 可选增强（想要再弄，依然双击）**

| 想要的功能 | 怎么做 | 之后在哪开 |
|---|---|---|
| 🎤 语音说话 | 双击 **`install-voice.bat`** | 直接点挂件上的麦克风图标即可（无需改设置）|
| 🗣️ 更自然的本地音色 | 双击 **`get-kokoro.bat`**（约 340MB，等几分钟）| ⚙ 设置 → **语音引擎 → 选 Kokoro** |
| 🌦️ 天气陪伴 | 无需命令 | ⚙ 设置 → **天气**栏，粘上 [OpenWeather](https://openweathermap.org/api) 的免费 key |

> 📷 *(设置面板示意图占位 —— 截一张 ⚙ 面板放这里，标出「语音引擎」「天气」的位置)*

**遇到问题？**

- 双击 `run.bat` 闪退 / 报 Python → 没装 Python 或没勾 Add to PATH，重装。
- 国外新闻（BBC/NYT）抓不到 → 需要科学上网，开着系统代理即可。
- 聊天报「模型不存在」→ 你的账号没 `deepseek-v4-flash`，用记事本打开 `.env` 加一行 `DEEPSEEK_MODEL=deepseek-chat`。
- 没装 Node → 聊天 / 新闻照常，只是不能点歌。

</details>

## 可选增强

> 怕命令行的话，下面两项都有**双击版**：`install-voice.bat`、`get-kokoro.bat`（见上方小白教程第五步）。

- **语音输入 / 本地 Kokoro 音色**：`.venv\Scripts\python -m pip install -r requirements-voice.txt`。
  不装也能用——缺了会自动退回「打字 + 在线 edge-tts」。
  - Vosk 中文识别模型首次使用时**自动下载**（国内免代理）。
  - Kokoro 本地音色模型一键拉取：`.venv\Scripts\python download_models.py`
    （~340MB，下到 `models/`；GitHub 慢的话在 `.env` 设 `KOKORO_MODEL_URL` / `KOKORO_VOICES_URL` 换镜像）。
    下完后到 ⚙ 设置把语音引擎切到 Kokoro 才生效。不下则继续用在线 edge-tts。
- **天气**：在 `.env` 填 `OPENWEATHER_API_KEY`（[免费申请](https://openweathermap.org/api)），或挂件 ⚙ 设置里填。

## 说明

- **DeepSeek 模型**：默认 `deepseek-v4-flash`。若你的账号没有这个模型（首跑报错），在 `.env` 里设
  `DEEPSEEK_MODEL=deepseek-chat`（官方公开模型）或你账号可用的其它名字。
- **新闻来源 / 代理**：BBC / Guardian / NYT 等国外源在大陆通常需代理。开着系统代理即可（程序走系统代理），
  或在 `.env` 设 `HTTP_PROXY` / `HTTPS_PROXY`。抓不到的源会自动跳过。想换源改 `backend/config.py` 的 `FEEDS`。
- **音色 / 语速 / 唤醒词等**：挂件 ⚙ 设置里调，或改 `settings.json`。
- **跑测试**：`pip install -r requirements-dev.txt` 后 `python -m pytest`。

## 控制

| 操作 | 功能 |
|---|---|
| 底部输入框 | 打字跟 Dsdio 说话（回车发送）|
| 🎤 | 语音输入 |
| ▶ / ⏸ · ⏮ / ⏭ | 音乐 播放暂停 / 上一首下一首 |
| ⚙ | 设置（API Key、音色、语速、唤醒词、识别/语音引擎、天气、开机自启）|
| 📌 | 置顶开关 |
| – | 最小化成右下角迷你停靠条 |
| `Ctrl + Alt + D` | 全局热键：迷你 ⇆ 完整 切换（迷你态点不到时靠它还原）|
| 顶栏 | 按住拖动挂件 |

## 目录结构

```
news-podcast/
├─ app.py              # 入口：窗口 + JS↔Python 桥 + 玻璃效果 + 逐句合成管线
├─ backend/
│  ├─ config.py        # 配置：Key、RSS 源、音色 persona、设置持久化（原子写）
│  ├─ host.py          # DeepSeek 流式对话：闲聊 / 点歌 / 聊新闻（AI 主持 Dsdio）
│  ├─ news.py          # RSS 抓取 / 清洗 / 去重 / 过滤 / 缓存自愈重抓
│  ├─ memory.py        # 用户记忆：长期偏好 + 当日短期（每 10 轮提炼）
│  ├─ music.py         # 网易云搜索 + 取址 + UNM 解锁（免登录）
│  ├─ tts.py           # edge-tts / Kokoro 语音 + 逐词时间轴
│  ├─ stt.py           # 本地离线识别（Vosk·中文）+ 唤醒监听
│  ├─ weather.py       # OpenWeather 当前天气（IP / 城市定位）
│  ├─ autostart.py     # 开机自启（HKCU Run 键）
│  └─ win_effects.py   # Win11 亚克力磨砂 + 圆角 + 迷你停靠
├─ frontend/           # 玻璃 UI（index.html / style.css / app.js）
├─ tests/              # pytest 单测
├─ music-api/          # 本地 Node：NeteaseCloudMusicApi（搜索 / 免费地址）
├─ unm-api/            # 本地 Node：UNM 解锁服务
├─ download_models.py        # 可选：一键拉 Kokoro / Vosk 模型
├─ requirements.txt          # 核心依赖
├─ requirements-voice.txt    # 可选：语音输入 + Kokoro
├─ run.bat                   # 双击启动（首次自动装依赖）
├─ install-voice.bat         # 双击：装语音输入功能
├─ get-kokoro.bat            # 双击：装并下载本地 Kokoro 音色
├─ LICENSE
└─ .env.example
```

## 许可与免责

- 代码以 **MIT** 许可证开源（见 `LICENSE`）。
- 本项目调用了第三方服务：[NeteaseCloudMusicApi](https://github.com/Binaryify/NeteaseCloudMusicApi)
  和 [UnblockNeteaseMusic](https://github.com/UnblockNeteaseMusic/server)。音乐相关功能**仅供个人学习与
  研究**，请遵守相应平台的服务条款与当地法律，自行承担使用风险。
- 新闻内容版权归各 RSS 来源所有；DeepSeek / OpenWeather 等 API 按其各自条款使用。
