"""Dsdio —— AI 私人电台 DJ。基于 DeepSeek 的流式多轮对话：闲聊 / 放音乐 / 聊新闻。

输出走纯文本流（便于前端逐字显示 + 逐句合成语音）；点歌用末尾的 [PLAY: 查询] 标记表达。
"""
from __future__ import annotations

import json
import re

from openai import OpenAI

from . import commands, config

# 语言锁贴在 messages 末尾（最后一条 user 之后），借近因效应压过 DeepSeek 的"语言镜像"先验
# + 中文消息 / 新闻标题，把回复强制锁成英文；stream_reply 与 command_followup 共用。
_LANG_LOCK = ("Language lock: no matter what language appears above — the listener's message, "
              "the conversation history, or any Chinese news headlines — your ENTIRE reply MUST "
              "be written in English. Never reply in Chinese or any other language.")


def _system() -> str:
    """系统提示词。主持名每次按设置动态取（用户可在设置里改名）。"""
    name = config.host_name()
    return (
        f"You are {name}, the personal DJ of the listener's own private radio station — a one-to-one "
        "broadcast, just the two of you on the air. You are warm, magnetic and a little playful — but "
        "also genuinely sharp, curious and knowledgeable, like a brilliant friend spinning tracks and "
        "talking just for this one listener.\n"
        "Match your length to the moment: light chit-chat gets a sentence or two; a real question gets "
        "a thoughtful, accurate, genuinely useful answer — still in your relaxed on-air voice. Never be "
        "vague, generic or fluffy. If you don't actually know something, say so honestly.\n"
        "ALWAYS speak in English, even when the listener writes in Chinese or any other language. You "
        "understand every language; you just always go on air in English.\n"
        "Reply in plain spoken text only — NO JSON, no markdown, no bullet lists, no stage directions.\n"
        "If the listener asks about news / what's happening, pick the few most interesting items from "
        "TODAY'S HEADLINES (given separately) and chat about them in your own words. If no headlines "
        "were given, just say they're still loading.\n"
        "If (and only if) the listener wants music, append a marker on its very last line, and put "
        "nothing after it — everything before it is what you say on air. Choose the marker by intent:\n"
        "  • They name a PARTICULAR song (a specific title, optionally with the artist) → "
        "[SONG: <title> <artist>]  — this plays just that one track, then returns to the playlist.\n"
        "  • They want a mood / genre / vibe / 'some music' / an artist's selection (not one exact title) "
        "→ [PLAY: <concise search query>]  — this curates a playlist.\n"
        "The query MAY be Chinese for Chinese artists/songs."
    )


class HostError(Exception):
    pass


def _client() -> OpenAI:
    key = config.get_api_key()
    if not key:
        raise HostError("Missing DeepSeek API key — add it in Settings or in the .env file.")
    return OpenAI(api_key=key, base_url=config.DEEPSEEK_BASE_URL)


def stream_reply(history: list[dict], user_text: str, news_digest: str = "", memory_ctx: str = ""):
    """逐块产出 Dsdio 回复文本（纯文本流；[PLAY:] 标记由调用方解析）。"""
    messages = [{"role": "system", "content": _system()}]
    if memory_ctx:
        messages.append({"role": "system", "content":
                         "WHAT YOU KNOW ABOUT THIS LISTENER (use it naturally — pick up on their mood "
                         "and what they've been doing, offer warmth or comfort when it fits, and when it "
                         "makes sense suggest music matching their taste / the time / the weather via a "
                         "[PLAY: ...] line; never recite this list back at them):\n" + memory_ctx})
    if news_digest:
        messages.append({"role": "system", "content":
                         "TODAY'S HEADLINES (only bring up if the listener asks about news; "
                         "otherwise ignore):\n" + news_digest})
    messages += history + [{"role": "user", "content": user_text}]
    messages.append({"role": "system", "content": _LANG_LOCK})   # 末尾语言锁，见 _LANG_LOCK 注释
    client = _client()
    try:
        stream = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL, messages=messages, stream=True,
            temperature=0.7, max_tokens=1200, frequency_penalty=0.5, presence_penalty=0.3,
        )
        for chunk in stream:
            try:
                delta = chunk.choices[0].delta.content
            except Exception:
                delta = None
            if delta:
                yield delta
    except Exception as e:  # noqa: BLE001
        raise HostError(f"DeepSeek request failed: {e}") from e


def command_followup(history: list[dict], action: str, said: str,
                     now_playing: str = "", memory_ctx: str = "") -> str:
    """快捷命令（切歌/暂停等）命中、固定短语 said 已脱口之后，让 Dsdio 用 DJ 口吻自然补一句
    ——不重复 said、不重新打招呼。把刚切到的歌 now_playing 告诉她。返回一两句短文本（非流式）。"""
    situation = commands.followup_action_desc(action) or "changed the playback"
    parts = [f'The listener just {situation}. A beat ago you already blurted "{said}".']
    if now_playing:
        parts.append(f"Now playing: {now_playing}.")
    parts.append(
        "In your on-air DJ voice, add exactly ONE short, fresh line that flows on from what you just "
        "said — react to the moment or the track. Do NOT repeat what you already said, do NOT greet "
        "again, no song markers — plain spoken text only.")
    messages = [{"role": "system", "content": _system()}]
    if memory_ctx:
        messages.append({"role": "system", "content":
                         "WHAT YOU KNOW ABOUT THIS LISTENER (use it naturally):\n" + memory_ctx})
    messages += list(history or [])
    messages.append({"role": "user", "content": " ".join(parts)})
    messages.append({"role": "system", "content": _LANG_LOCK})
    client = _client()
    try:
        resp = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL, messages=messages,
            temperature=0.8, max_tokens=120, frequency_penalty=0.4, presence_penalty=0.3,
        )
    except Exception as e:  # noqa: BLE001
        raise HostError(f"DeepSeek request failed: {e}") from e
    return (resp.choices[0].message.content or "").strip()


_PLAY_RE = re.compile(r"\[(PLAY|SONG):\s*(.+?)\]", re.S)
_PARTIAL = ("[PLAY", "[SONG", "[PLAY:", "[SONG:")


def displayable(full: str) -> str:
    """流式过程中，把（可能还不完整的）[PLAY:...] / [SONG:...] 标记从可见文本里去掉。"""
    m = _PLAY_RE.search(full)
    if m:
        return full[:m.start()].rstrip()
    i = full.rfind("[")
    if i != -1:
        tail = full[i:]
        if any(tail.startswith(p) or p.startswith(tail) for p in _PARTIAL):
            return full[:i].rstrip()
    return full


def split_play(full: str) -> tuple[str, str, str]:
    """返回 (要说的话, 点歌查询, 类型)。类型: "song"=点名单曲 / "play"=氛围歌单 / ""=没点歌。"""
    m = _PLAY_RE.search(full)
    if m:
        return full[:m.start()].strip(), m.group(2).strip(), m.group(1).lower()
    return full.strip(), "", ""


def opening_playlist(part_of_day: str, weather_desc: str, user_name: str = "",
                     memory_ctx: str = "") -> dict:
    """按时间段 + 天气（+ 用户记忆）出一句"问候陪伴"开场白 + 一组搜歌关键词。返回 {say, queries}。"""
    name = (user_name or "").strip()
    addr = (f'Drop their name "{name}" right into the casual opener, like "Evening, {name}." — '
            "say it the easy way a close friend would, never stiff or formal."
            if name else
            "Greet the listener warmly and directly — you don't know their name, so don't invent one.")
    mem_rule = (
        "- You ALSO remember things about this listener (given below). If you know their mood or what "
        "they've been up to today, weave in a caring, specific line — comfort or celebrate, then offer "
        "to play something for it (e.g. 'you've been deep in Claude Code all day — let's unwind, here's "
        "one for you'). Lean on their known music taste / time / weather preferences when picking the vibe.\n"
        if memory_ctx else ""
    )
    dj = config.host_name()
    sys_prompt = (
        f"You are {dj}, the listener's personal radio companion, on the air just for them. "
        f"Right now it is {part_of_day} and the weather is: {weather_desc}.\n"
        "Write a warm, caring spoken greeting — the kind a close friend gives, genuinely glad they "
        "showed up — then curate a matching playlist. Return JSON only:\n"
        '{"say": "<the spoken greeting>", "queries": ["<search query>", ...]}\n'
        'Rules for "say":\n'
        "- Open casually and colloquially with just the time of day — \"Morning\" / \"Afternoon\" / "
        "\"Evening\" / \"Hey, it's late\" — NOT the stiff 'Good morning / Good evening'. Talk like a "
        "close friend, relaxed and easy.\n"
        f"- {addr}\n"
        "- Do NOT introduce yourself or mention your own name; go straight to caring about the listener.\n"
        "- Use today's weather to open a little caring topic (comment on the rain / cold / sun / heat, "
        "tell them to stay cozy, bundle up, hydrate, etc.).\n"
        "- Add a gentle, companion-like touch fitting the hour — morning: a fresh new day, ask if "
        "they've had breakfast; midday: hope lunch went well, take a breather; evening: time to wind "
        "down; late night: you'll keep them company so they're not up alone.\n"
        + mem_rule +
        "- 1 to 3 warm spoken English sentences. Plain text only — no markdown, no stage directions.\n"
        'For "queries": 8 concise search queries for a Chinese music app (NetEase) — moods, genres or '
        "artists that fit this time of day, this weather, and the listener's known taste; mix Chinese "
        "and English terms.\n"
        "Output JSON only."
    )
    user = (f"Time of day: {part_of_day}. Weather: {weather_desc}. "
            f"Listener name: {name or '(unknown)'}.")
    if memory_ctx:
        user += "\n\nWHAT YOU REMEMBER ABOUT THIS LISTENER:\n" + memory_ctx
    client = _client()
    try:
        resp = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}],
            response_format={"type": "json_object"}, temperature=0.9, max_tokens=600,
        )
    except Exception as e:  # noqa: BLE001
        raise HostError(f"DeepSeek request failed: {e}") from e
    try:
        data = json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        data = {}
    queries = [q.strip() for q in (data.get("queries") or []) if isinstance(q, str) and q.strip()]
    return {"say": (data.get("say") or "").strip(), "queries": queries[:10]}


def split_sentences(text: str) -> list[dict]:
    """按句切分，返回 [{text, start, end}]，start/end 是在 text 中的字符区间（拼接可还原整段）。"""
    out: list[dict] = []
    start = 0
    for j, ch in enumerate(text):
        if ch in ".!?。！？\n":
            if text[start:j + 1].strip():
                out.append({"text": text[start:j + 1].strip(), "start": start, "end": j + 1})
            start = j + 1
    if start < len(text) and text[start:].strip():
        out.append({"text": text[start:].strip(), "start": start, "end": len(text)})
    return out
