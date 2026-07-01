"""Dsdio —— 桌面 AI 电台主持挂件。

无边框、置顶、手机尺寸的科幻玻璃窗口。你用对话（打字或语音）跟 AI 主持 Dsdio 互动：
闲聊、点歌（网易云）、或让她聊今天的新闻。前端通过 js_api 调用后端。
"""
from __future__ import annotations

import base64
import json
import os
import queue
import random
import shutil
import subprocess
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import webview

from backend import (autostart, commands, config, host, memory, music, news, stt, tts, weather,
                     win_effects)

WINDOW_TITLE = "Dsdio"
MINI_W, MINI_H = 330, 116   # 迷你停靠条的逻辑尺寸（贴桌面右缘）

# 模型偶尔没正常吐内容时给用户的兜底句（随机选，且绝不写入对话历史，避免复读）
FALLBACKS = [
    "Hmm, you cut out for a second — say that again?",
    "Sorry, I drifted off the signal there. What was that?",
    "I didn't quite catch that — run it by me once more?",
    "Static on the line for a sec — come again?",
]


def _voice_data_url(text: str, persona: str, rate: int) -> tuple[str, list]:
    audio, words, mime = tts.synth(text, "en", persona, rate)
    return f"data:{mime};base64," + base64.b64encode(audio).decode("ascii"), words


class _SentencePipeline:
    """逐句 TTS 合成的并行管线：合成在线程池里并行跑（不阻塞 DeepSeek 流的消费），
    但按 submit 的 idx 顺序推送给前端（播放次序不乱）。

    synth_fn(text) -> (voice, words)；push_fn(idx, text, voice, words) 真正推前端。
    合成完成先后无所谓，消费线程按提交顺序逐个取 future.result()，所以推送严格有序。"""

    def __init__(self, synth_fn, push_fn, max_workers: int = 3) -> None:
        self._synth = synth_fn
        self._push = push_fn
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        self._q: queue.Queue = queue.Queue()
        self._consumer = threading.Thread(target=self._run, daemon=True)
        self._consumer.start()

    def submit(self, idx: int, text: str) -> None:
        fut = self._pool.submit(self._synth, text)   # 立刻并行合成，不等
        self._q.put((idx, text, fut))

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            idx, text, fut = item
            try:
                voice, words = fut.result()
            except Exception:           # 单句合成失败：空语音兜底，不卡后续
                voice, words = "", []
            try:
                self._push(idx, text, voice, words)
            except Exception:
                pass

    def close(self) -> None:
        """等所有已提交句子按序推完，再收摊。"""
        self._q.put(None)
        self._consumer.join()
        self._pool.shutdown(wait=True)


class Api:
    def __init__(self) -> None:
        # 注意：所有内部属性都用 _ 前缀，否则 pywebview 暴露 js_api 时会去遍历
        # 这些对象（尤其是原生 window），递归 window.native.AccessibilityObject... 直到崩溃。
        self._window: webview.Window | None = None
        self._history: list[dict] = []
        self._music_proc: subprocess.Popen | None = None
        self._top = True
        self._mini = False            # 是否处于迷你停靠态
        self._full_rect: tuple | None = None  # 进入迷你前的窗口矩形（物理像素），用于精确还原
        self._gen = 0  # 对话代数：新消息 +1，前端据此丢弃过期的逐句推送
        self._hotkey_ok = False       # 全局还原热键是否注册成功；没成功则迷你态不全穿透，免卡死

    # ---------- 状态 / 设置 ----------
    def get_state(self) -> dict:
        s = config.load_settings()
        return {
            "has_key": bool(config.get_api_key()),
            "has_weather_key": bool(config.get_weather_key()),
            "host": config.host_name(),
            "personas": config.personas_public(),
            "music_up": music.is_up(),
            "autostart": autostart.is_enabled(),
            "settings": {
                "host_name": s.get("host_name", ""),
                "persona": s["persona"],
                "rate": s["rate"],
                "volume": s["volume"],
                "mic_enabled": s.get("mic_enabled", True),
                "wake_word": s.get("wake_word", "Dsdio"),
                "recog_lang": s.get("recog_lang", "zh"),
                "recog_engine": s.get("recog_engine", "vosk"),
                "tts_engine": s.get("tts_engine", "edge"),
            },
        }

    def save_settings(self, patch: dict) -> dict:
        patch = dict(patch or {})
        if "host_name" in patch:  # 主持名只留英文，存进去前先清洗
            patch["host_name"] = config.sanitize_host_name(patch["host_name"])
        config.save_settings(patch)
        if (patch or {}).get("tts_engine") == "kokoro":  # 切到 Kokoro 时后台预热模型
            threading.Thread(target=tts.warm_kokoro, daemon=True).start()
        if any(k in (patch or {}) for k in ("weather_city", "weather_country", "weather_key")):
            weather.invalidate()
        return self.get_state()

    def set_api_key(self, key: str) -> dict:
        config.save_settings({"api_key": (key or "").strip()})
        return {"ok": True, "has_key": bool(config.get_api_key())}

    def set_autostart(self, on: bool) -> dict:
        """开 / 关开机自启（写 HKCU Run 键），返回写入后的真实状态。"""
        ok = autostart.set_enabled(bool(on))
        return {"ok": ok, "autostart": autostart.is_enabled()}

    # ---------- 本地语音识别（离线引擎：vosk·中文；online 由前端 Web Speech 处理）----------
    def voice_prepare(self) -> dict:
        """加载所选离线引擎模型（首次会下载，可能几十秒）。在 js_api 工作线程上跑，不挡 UI。"""
        eng = config.load_settings().get("recog_engine", "vosk")
        if eng == "online":
            return {"ok": True, "engine": "online", "ready": True}
        return stt.prepare(eng)

    def voice_wake_start(self) -> dict:
        """启动离线唤醒监听。online 引擎返回 online=True，让前端走 Web Speech。"""
        eng = config.load_settings().get("recog_engine", "vosk")
        if eng == "online":
            return {"ok": False, "online": True}
        win = self._window
        stt.wake_start(lambda: win and win.evaluate_js("window.dsdioOnWake()"))
        return {"ok": True}

    def voice_wake_stop(self) -> dict:
        stt.wake_stop()
        return {"ok": True}

    def voice_wake_resume(self) -> dict:
        stt.wake_resume()
        return {"ok": True}

    def voice_speaking(self, on: bool) -> dict:
        """前端在 Dsdio 出声时置位，唤醒监听据此丢弃这段音频（避免把自己当输入）。"""
        stt.set_speaking(bool(on))
        return {"ok": True}

    def voice_listen(self, standby_ms: int = 5000, gap_ms: int = 2000) -> dict:
        """收一句话并转文字（离线引擎）。等开口最多 standby_ms，停顿超 gap_ms 视为说完。"""
        try:
            text = stt.listen_once(int(standby_ms), int(gap_ms))
        except Exception:  # noqa: BLE001
            text = ""
        return {"ok": True, "text": text}

    def weather(self) -> dict:
        return weather.current()

    def startup_mix(self, gen: int | None = None) -> dict:
        """开机定制：按时间段 + 天气 + 记忆生成开场白(逐句念) + 歌单，返回曲目列表。"""
        s = config.load_settings()
        win = self._window
        memory.rollover()  # 短期记忆过期则先总结进长期，再开新的一天
        for _ in range(12):  # 等网易云服务就绪
            if music.is_up():
                break
            time.sleep(0.5)

        h = time.localtime().tm_hour
        part = ("late night" if h < 5 else "early morning" if h < 8 else "morning" if h < 12
                else "afternoon" if h < 18 else "evening" if h < 22 else "night")
        w = weather.current()
        wdesc = f"{w['desc']}, {w['temp']}°C in {w.get('city','')}" if w.get("ok") else "weather unknown"

        say, queries = "", []
        if config.get_api_key():
            try:
                r = host.opening_playlist(part, wdesc, s.get("user_name", ""), memory.context_blurb())
                say, queries = r.get("say", ""), r.get("queries", [])
            except Exception:  # noqa: BLE001
                pass

        # 先把开场白逐句念出来（同时下面接着搜歌，重叠不干等）
        gen = self._next_gen(gen)
        idx = 0
        if say:
            for sent in host.split_sentences(say):
                self._emit_sentence(win, gen, idx, sent["text"], s)
                idx += 1
            self._history.append({"role": "assistant", "content": say})
            self._history = self._history[-16:]

        tracks: list[dict] = []
        seen: set = set()
        for q in queries:
            try:
                for t in music.search_playable(q, limit=4):
                    if t["id"] in seen:
                        continue
                    seen.add(t["id"])
                    tracks.append(t)
            except music.MusicError:
                pass
            if len(tracks) >= 15:
                break
        if not tracks:
            try:
                tracks = music.something(limit=12)
            except music.MusicError:
                tracks = []
        # 开机自动播放的歌不算用户主动选择，不计入风格偏好（偏好只在对话里由 observe 提炼）。
        return {"ok": True, "tracks": tracks}

    def _next_gen(self, gen: int | None) -> int:
        """gen 由前端传入则采用它（前后端共用同一真相源，避免跨桥错位）；
        没传(旧调用)就自增兜底。"""
        if gen is None:
            self._gen += 1
        else:
            self._gen = gen
        return self._gen

    # ---------- 对话主流程 ----------
    def chat(self, text: str, gen: int | None = None) -> dict:
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "empty"}
        s = config.load_settings()
        digest = news.digest(news.cached_items(), 16)  # 今日头条注入上下文，新闻也在这一轮回答
        mem_ctx = memory.context_blurb()                # 长期偏好 + 今日情况，用来找话题 / 安慰 / 荐歌
        win = self._window
        gen = self._next_gen(gen)
        terms = ".!?。！？\n"
        full, pos, idx = "", 0, 0
        # 逐句合成走并行管线：合成在线程池里跑，不再卡住下面这层流式读取（边读边并行合成、按序推送）
        pipe = _SentencePipeline(
            lambda seg: self._synth_voice(seg, s),
            lambda i, seg, voice, words: self._push_sentence(win, gen, i, seg, voice, words),
        )
        try:
            # 流式生成：每凑齐一句就提交合成 + 排队推前端（提交不阻塞，继续读流）
            for delta in host.stream_reply(self._history, text, digest, mem_ctx):
                full += delta
                disp = host.displayable(full)
                while True:
                    end = next((j + 1 for j in range(pos, len(disp)) if disp[j] in terms), -1)
                    if end == -1:
                        break
                    seg = disp[pos:end].strip()
                    pos = end
                    if seg:
                        pipe.submit(idx, seg)
                        idx += 1
        except host.HostError as e:
            pipe.close()
            return {"ok": False, "error": str(e)}
        except Exception as e:  # noqa: BLE001
            pipe.close()
            return {"ok": False, "error": f"Chat failed: {e}"}

        say, play_query, play_kind = host.split_play(full)
        tail = host.displayable(full)[pos:].strip()
        if say and tail:
            pipe.submit(idx, tail)
            idx += 1

        tracks: list[dict] = []
        pending: list[dict] = []
        one_shot = play_kind == "song"   # 点名单曲：只放这一首，放完切回推荐歌单
        note = ""
        if play_query:
            try:
                if one_shot:
                    # 只取最相关那一首（原版），不要同名翻唱，也不后台续解
                    ready, _ = music.search_split(play_query, limit=3)
                    tracks = ready[:1]
                else:
                    tracks, pending = music.search_split(play_query, limit=12)  # 氛围歌单：秒播首曲 + 后台续解
                if not tracks and not pending:
                    tracks = music.something(limit=12)
                    one_shot = False  # 兜底给的是歌单，不是点名单曲
                    if tracks:
                        note = "couldn't find that one free, so here's something close"
            except music.MusicError as e:
                note = f"(music error: {e})"

        self._history.append({"role": "user", "content": text})
        had_real = bool(say) or bool(tracks)
        if not say:
            say = random.choice(FALLBACKS)
            if idx == 0:
                pipe.submit(idx, say)
                idx += 1
        # 等所有句子按序合成 + 推完前端，再继续（保持"所有逐句推送都发生在 chat() 内"的约定）
        pipe.close()
        if had_real:
            self._history.append({"role": "assistant", "content": say})
        self._history = self._history[-16:]

        # 记忆全部丢到后台线程，绝不挡当前回应（含可能联网的天气查询 + LLM 提炼）
        threading.Thread(target=self._remember,
                         args=(list(self._history), text, say),
                         daemon=True).start()
        # 氛围歌单时，其余被锁的歌后台慢慢用 UNM 解锁、解好一首推给前端追加（点名单曲不续解，免得灌一堆翻唱）
        if pending and not one_shot and win is not None:
            threading.Thread(target=self._resolve_more, args=(gen, pending, win),
                             daemon=True).start()
        return {"ok": True, "tracks": tracks, "play": bool(tracks), "one_shot": one_shot, "note": note}

    def _resolve_more(self, gen: int, songs: list, win) -> None:
        """后台：UNM 解锁 pending 里的歌，逐首推给前端追加到播放队列（带 gen，过期则丢弃）。"""
        try:
            for tr in music.resolve_pending(songs, max_n=11):
                if win is None or gen != self._gen:  # 已经是新一轮对话了，旧队列的歌不要了
                    return
                try:
                    win.evaluate_js(
                        "window.dsdioQueueAppend(%d, %s)" % (gen, json.dumps([tr], ensure_ascii=False)))
                except Exception:
                    return
        except Exception:
            pass

    def _remember(self, history: list, user_text: str, reply: str) -> None:
        """后台：从本轮对话提炼当日心情 / 活动 / 聊天方式，并记录用户主动要的 / 夸奖的歌曲风格
        （含当时天气）。不在对话主路径上。"""
        try:
            wn = weather.current()
            wd = f"{wn['desc']}, {wn['temp']}°C" if wn.get("ok") else ""
        except Exception:  # noqa: BLE001
            wd = ""
        memory.observe(history, user_text, reply, wd)

    def _synth_voice(self, sentence: str, s: dict) -> tuple[str, list]:
        """合成一句的语音 data-url + 逐词时间轴；失败给空。可被线程池并行调用。"""
        try:
            return _voice_data_url(sentence, s["persona"], s["rate"])
        except Exception:
            return "", []

    def _push_sentence(self, win, gen: int, idx: int, sentence: str, voice: str, words: list) -> None:
        """把已合成好的一句推给前端排队播放（必须按 idx 顺序调用）。"""
        if not win:
            return
        payload = json.dumps({"gen": gen, "i": idx, "text": sentence, "words": words, "voice": voice})
        try:
            win.evaluate_js("window.dsdioSentence(" + payload + ")")
        except Exception:
            pass

    def _emit_sentence(self, win, gen: int, idx: int, sentence: str, s: dict) -> None:
        """同步合成 + 推送一句（开场白等非流式路径用；流式路径走 _SentencePipeline 并行）。"""
        voice, words = self._synth_voice(sentence, s)
        self._push_sentence(win, gen, idx, sentence, voice, words)

    def speak(self, text: str) -> dict:
        """单独合成语音 + 逐字时间轴（前端异步调用，不阻塞文字显示）。"""
        text = (text or "").strip()
        if not text:
            return {"ok": False}
        s = config.load_settings()
        try:
            voice, words = _voice_data_url(text, s["persona"], s["rate"])
        except Exception:
            return {"ok": False}
        return {"ok": True, "voice": voice, "words": words}

    def playback_command(self, text: str) -> dict:
        """前端在发起对话前先问这一句是不是直接的播放控制命令（下一首/上一首/暂停/继续）。
        命中则返回 {action, say}，前端就地操作播放器、不再发给 DeepSeek；否则 action=None。"""
        hit = commands.match_playback(text) or {}
        return {"ok": True, "action": hit.get("action"), "say": hit.get("say", "")}

    def command_followup(self, action: str, say: str, now_playing: str = "") -> dict:
        """命令命中、固定短语 say 已念之后，让 Dsdio 用 DJ 口吻自然补一句（不重复 say）。
        只读对话历史作氛围、不写回（命令是即兴操作，不污染上下文）；失败静默降级。"""
        try:
            text = host.command_followup(self._history, action, say, now_playing,
                                         memory.context_blurb())
        except Exception:  # noqa: BLE001
            return {"ok": False}
        return {"ok": True, "text": text}

    def preview_voice(self, persona_id: str) -> dict:
        s = config.load_settings()
        try:
            voice, _ = _voice_data_url("Hey, this is the voice that'll keep you company tonight.",
                                       persona_id, s["rate"])
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"Preview failed: {e}"}
        return {"ok": True, "audio": voice}

    # ---------- 窗口控制 ----------
    def minimize(self) -> None:
        if not self._window:
            return
        try:
            self._window.minimize()
        except Exception:
            pass

    def enter_mini(self) -> dict:
        """最小化 = 缩成贴右缘的迷你停靠条（保留播放/语音，不挂后台）。"""
        hwnd = win_effects.find_hwnd(WINDOW_TITLE)
        clickthrough = False
        if hwnd:
            rect = win_effects.window_rect(hwnd)
            if rect:
                self._full_rect = rect      # 记住当前窗口矩形，退出迷你时精确还原
            # 只有全局还原热键确实注册成功时，才进"全透明 + 鼠标穿透"态：
            #   关磨砂露出浅灰 Form 底，再用分层色键把它键透 → 桌面真透出来。代价是整条窗鼠标
            #   穿透（点不到头像），靠 Ctrl+Alt+D 还原。
            # 热键不可用时退而求其次：保留磨砂、不穿透，用户仍能点头像还原 —— 绝不卡死。
            clickthrough = bool(self._hotkey_ok)
            win_effects.enable_acrylic(hwnd, enable=not clickthrough)
            win_effects.set_clickthrough_key(hwnd, clickthrough)
            win_effects.dock_right(hwnd, MINI_W, MINI_H, margin=14, valign="bottom")  # 右下、状态栏上方
            self._mini = True
        return {"mini": True, "clickthrough": clickthrough}

    def exit_mini(self) -> dict:
        """从迷你态展开回完整窗口。"""
        stt.wake_stop()   # 直接停掉离线唤醒监听（释放麦克风/停 Vosk），不依赖前端回调
        hwnd = win_effects.find_hwnd(WINDOW_TITLE)
        if hwnd:
            win_effects.set_clickthrough_key(hwnd, False)  # 先移除分层色键
            win_effects.enable_acrylic(hwnd)               # 恢复完整模式磨砂
            if self._full_rect:
                x, y, w, h = self._full_rect
                win_effects.set_geometry(hwnd, x, y, w, h, self._top)
            else:  # 兜底：没存到旧矩形就给个默认尺寸贴右边
                win_effects.dock_right(hwnd, 400, 800, margin=40)
            self._mini = False
        return {"mini": False}

    def toggle_mini(self) -> None:
        """全局热键触发：完整 <-> 迷你 互切，并同步前端布局（透明迷你态点不到，只能靠热键）。

        关键：窗口缩放/还原是纯 Win32、必须同步做掉（即使前端出问题也能靠它还原）；
        evaluate_js 丢到独立线程发 —— 它可能反过来触发 JS→Python 调用（如停唤醒监听），
        若同步在热键线程里等，会卡住消息循环，导致之后按键全失灵。
        """
        try:
            if self._mini:
                self.exit_mini()
            else:
                self.enter_mini()
        except Exception:  # noqa: BLE001
            pass
        js = "window.dsdioSetMini(%s)" % ("true" if self._mini else "false")
        threading.Thread(target=self._safe_eval, args=(js,), daemon=True).start()

    def _safe_eval(self, js: str) -> None:
        try:
            if self._window:
                self._window.evaluate_js(js)
        except Exception:  # noqa: BLE001
            pass

    def close(self) -> None:
        self._stop_music_server()
        if self._window:
            self._window.destroy()

    def toggle_top(self) -> dict:
        self._top = not self._top
        win_effects.set_topmost(win_effects.find_hwnd(WINDOW_TITLE), self._top)
        try:
            self._window.on_top = self._top
        except Exception:
            pass
        return {"on_top": self._top}

    # ---------- 本地音源服务（可选便利 spawn，目录不随仓发布）----------
    @staticmethod
    def _node_exe() -> str:
        """解析 node 可执行文件：优先 PATH，回退常见安装路径（pythonw 启动时 PATH 可能不全）。"""
        exe = shutil.which("node")
        if exe:
            return exe
        for p in (r"C:\Program Files\nodejs\node.exe", r"C:\Program Files (x86)\nodejs\node.exe"):
            if os.path.exists(p):
                return p
        return "node"

    def _spawn_node(self, work_dir, env_extra: dict | None = None):
        if not (work_dir / "server.js").exists():
            return None
        try:
            flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            env = dict(os.environ)
            if env_extra:
                env.update(env_extra)
            return subprocess.Popen(
                [self._node_exe(), "server.js"], cwd=str(work_dir), env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags,
            )
        except Exception:
            return None

    def start_music_server(self) -> None:
        # 可选便利：仅当 baseUrl 指向本机、且本地存在（gitignore 的）music-api/ 时，帮用户 spawn。
        # 否则只连不 spawn（远程后端 / 未放本地目录 → 用户自己跑）。
        base = config.MUSIC_API_BASE
        if not base or music.is_up():
            return
        parts = urllib.parse.urlsplit(base)
        if parts.hostname not in ("localhost", "127.0.0.1", "::1"):
            return
        if not (config.MUSIC_API_DIR / "server.js").exists():
            return
        port = parts.port or 3000
        self._music_proc = self._spawn_node(config.MUSIC_API_DIR, {"NCM_PORT": str(port)})

    def _stop_music_server(self) -> None:
        proc = self._music_proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass


def _hotkey_loop(api: "Api") -> None:
    """全局热键 Ctrl+Alt+D：完整 <-> 迷你 切换。
    迷你态背景全透明 → 整条窗鼠标穿透、点不回来，必须靠热键还原。"""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
        VK_D = 0x44
        if not user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_D):
            api._hotkey_ok = False  # 组合键被别的程序占了 → 迷你态走不穿透兜底，免卡死
            return
        api._hotkey_ok = True       # 注册成功，迷你态可安全进全透明穿透
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == 0x0312:  # WM_HOTKEY
                try:
                    api.toggle_mini()
                except Exception:  # noqa: BLE001
                    pass
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    except Exception:  # noqa: BLE001
        pass


def _warm_news() -> None:
    # 开机后台预抓今天到一个月内的要闻，缓存到次日 5 点，让首次「聊新闻」也秒回
    try:
        news.fetch_all()
    except Exception:
        pass


def _apply_glass_when_ready() -> None:
    for _ in range(20):
        time.sleep(0.15)
        if win_effects.apply_glass(WINDOW_TITLE):
            break


def main() -> None:
    # 允许开机自动播放（否则 WebView2 会拦截无用户手势的播放）。
    # 不再默认禁 HTTP 缓存——项目已定型，禁缓存只会拖慢每次冷启动；要改前端时设
    # DSDIO_CLEAR_CACHE=1 单次清缓存即可（见下方 _clear_webview_cache）。
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--autoplay-policy=no-user-gesture-required"
    config.CACHE_DIR.mkdir(exist_ok=True)
    api = Api()
    threading.Thread(target=api.start_music_server, daemon=True).start()
    threading.Thread(target=_warm_news, daemon=True).start()
    if config.load_settings().get("tts_engine") == "kokoro":  # 用 Kokoro 时开机预热模型
        threading.Thread(target=tts.warm_kokoro, daemon=True).start()

    window = webview.create_window(
        WINDOW_TITLE,
        url=str(config.BASE_DIR / "frontend" / "index.html"),
        js_api=api,
        width=400,
        height=800,
        frameless=True,
        easy_drag=False,
        on_top=True,
        # 开透明：完整模式外壳本身不透明、外观不变；迷你态把外壳设透明即可透出桌面。
        # （旧版关透明是因为"透明 + 原生最小化"会 GDI+ 崩溃，现在最小化改成缩放停靠、不再原生最小化）
        transparent=True,
        background_color="#05070e",
        # 调小最小尺寸，让迷你停靠条能缩到位（无边框窗口本就不能手动拉伸，min_size 仅约束程序化缩放）
        min_size=(160, 70),
    )
    api._window = window
    threading.Thread(target=_apply_glass_when_ready, daemon=True).start()
    threading.Thread(target=_hotkey_loop, args=(api,), daemon=True).start()  # 全局热键还原迷你态
    # private_mode=False -> 固定端口 + 持久化数据，麦克风授权只问一次、之后记住
    storage = str(config.BASE_DIR / ".webview")
    if os.getenv("DSDIO_CLEAR_CACHE"):   # 开发期改前端时设它，重启即清缓存生效；平时不清，冷启动更快
        _clear_webview_cache(storage)
    webview.start(debug=False, private_mode=False, storage_path=storage)


def _clear_webview_cache(storage_path: str) -> None:
    """清掉 WebView2 的 HTTP / 代码缓存，避免改了前端（含 index.html）重启还吃旧缓存。
    只删 Cache 类目录；麦克风授权等存在 Default/Preferences、Network 里，不受影响。"""
    base = os.path.join(storage_path, "EBWebView", "Default")
    for sub in ("Cache", "Code Cache", "GPUCache"):
        shutil.rmtree(os.path.join(base, sub), ignore_errors=True)


if __name__ == "__main__":
    main()
