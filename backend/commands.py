"""本地播放控制命令解析（阶段 A）。

把"下一首 / 上一首 / 暂停 / 继续"这类直接命令，在进 DeepSeek 之前就识别出来，前端据此
就地操作播放器——不耗 API、离线可用、零延迟。

判定很保守：只在"短文本 + 归一化后近精确命中"时算命令；长句、带额外语义的话（"我不想听
下一首这种歌"、"下一首歌的歌词是什么意思"）一律放过给对话，绝不误伤。
"""
from __future__ import annotations

import re

# 命中后 Dsdio 用 TTS 念的固定英文短语（符合对听众固定说英文的设定）。
_SAY = {
    "next": "You got it — next one.",
    "prev": "Sure, back one.",
    "pause": "Paused.",
    "resume": "Back on.",
}

# 归一化后（小写、去标点空白、剥掉首尾语气/礼貌虚词）若精确等于其中之一即命中。
# 尽量穷举常见中英文说法（含带前缀动词的整句变体，避免依赖激进的前缀剥离）。
_PHRASES = {
    "next": {
        "下一首", "下一曲", "下一个", "下首", "下个", "下一首歌", "下一",
        "换一首", "换一曲", "换个", "换首", "换首歌", "换一首歌", "换歌", "换一个",
        "切歌", "切下一首", "切一首", "切一下", "切首",
        "跳过", "跳过这首", "跳过这首歌", "跳这首", "跳过本首", "跳过这个",
        "放下一首", "放下一曲", "来下一首", "听下一首",
        "next", "nextone", "nextsong", "nexttrack", "nextplease",
        "skip", "skipit", "skipthis", "skipsong", "skiptrack", "skipthisone",
    },
    "prev": {
        "上一首", "上一曲", "上一个", "上首", "上个", "上一首歌", "上一",
        "前一首", "前一曲", "前一个",
        "返回上一首", "回上一首", "回到上一首", "退回上一首", "回去",
        "放上一首", "来上一首", "听上一首",
        "previous", "previoussong", "previoustrack", "prev", "prevsong",
        "goback", "back", "backone", "lastone", "lastsong", "lasttrack",
    },
    "pause": {
        "暂停", "暂停播放", "暂停一下", "停一下", "停一停", "停下", "停下来",
        "先停", "先暂停", "别放了", "别放", "停", "安静", "安静一下", "静音",
        "pause", "pauseit", "stop", "stopit", "stopplaying",
        "hold", "holdon", "wait", "waitup", "shush", "quiet", "bequiet",
    },
    "resume": {
        "继续", "继续放", "继续播放", "接着放", "接着播", "接着听", "接着",
        "恢复", "恢复播放", "放吧", "继续吧",
        "resume", "resumeplaying", "unpause", "continue",
        "keepplaying", "keepgoing", "playon", "goon",
    },
}

# 反查：归一化短语 -> action
_LOOKUP = {p: act for act, ps in _PHRASES.items() for p in ps}

# 可剥离的首部虚词（礼貌/请求语气）；从开头精确剥，剥完再查。
# 故意不收单独的"我"（避免把"我不想…"也剥进来）。
_PREFIXES = ["帮我", "帮忙", "给我", "麻烦", "我想", "我要", "能不能", "可以", "请", "那就", "那", "来"]
# 可剥离的尾部语气词。
_SUFFIXES = ["谢谢", "谢啦", "一下", "吧", "呗", "啊", "呀", "嘛", "了", "哈", "喔", "噢", "哦", "嗯"]

_STRIP_RE = re.compile(r"[\s\W_]+", re.UNICODE)
_MAX_LEN = 16  # 命令都很短；归一化后超过这个长度直接当对话，多一层不误伤长句的兜底。


def _strip_affixes(t: str) -> str:
    """反复从两端剥离虚词，直到稳定。"""
    changed = True
    while changed:
        changed = False
        for p in _PREFIXES:
            if t.startswith(p) and len(t) > len(p):
                t = t[len(p):]
                changed = True
        for s in _SUFFIXES:
            if t.endswith(s) and len(t) > len(s):
                t = t[: -len(s)]
                changed = True
    return t


def match_playback(text: str) -> dict | None:
    """text 是不是一句直接的播放控制命令？是则返回 {"action","say"}，否则 None。"""
    raw = _STRIP_RE.sub("", (text or "").strip().lower())
    if not raw or len(raw) > _MAX_LEN:
        return None
    act = _LOOKUP.get(_strip_affixes(raw))
    if not act:
        return None
    return {"action": act, "say": _SAY[act]}


# 命令命中后，给 DeepSeek 的人类可读情境（让它在固定短语之后自然补一句 DJ 评论）。
_ACTION_DESC = {
    "next": "skipped to the next track",
    "prev": "went back to the previous track",
    "pause": "paused the music",
    "resume": "resumed the music",
}


def followup_action_desc(action: str) -> str:
    """把 action 转成给 DeepSeek 的人类可读情境；未知 action 返回空串。"""
    return _ACTION_DESC.get(action, "")
