"""Windows 11 玻璃效果：给无边框透明窗口应用 acrylic 磨砂 + 圆角。

通过未公开的 user32.SetWindowCompositionAttribute 实现 acrylic 模糊，
通过 dwmapi.DwmSetWindowAttribute 设置圆角。全部 best-effort，失败静默。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

try:
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
except Exception:  # 非 Windows
    user32 = None
    dwmapi = None


class _ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_uint),
        ("AccentFlags", ctypes.c_uint),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_uint),
    ]


class _WINCOMPATTRDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.POINTER(_ACCENT_POLICY)),
        ("SizeOfData", ctypes.c_size_t),
    ]


_ACCENT_DISABLED = 0
_ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
_ACCENT_ENABLE_BLURBEHIND = 3
_WCA_ACCENT_POLICY = 19
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2


def rgba(r: int, g: int, b: int, a: int) -> int:
    """转成 SetWindowCompositionAttribute 需要的 0xAABBGGRR。"""
    return (a << 24) | (b << 16) | (g << 8) | r


def find_hwnd(title: str) -> int:
    if not user32:
        return 0
    return user32.FindWindowW(None, title) or 0


def enable_acrylic(hwnd: int, tint: int | None = None, enable: bool = True) -> bool:
    """enable=False 时禁用磨砂（迷你态要真透明，不要磨砂矩形）。"""
    if not user32 or not hwnd:
        return False
    if tint is None:
        tint = rgba(22, 20, 30, 0x9C)  # 深色半透明底色
    accent = _ACCENT_POLICY()
    accent.AccentState = _ACCENT_ENABLE_ACRYLICBLURBEHIND if enable else _ACCENT_DISABLED
    accent.AccentFlags = 2
    accent.GradientColor = tint
    accent.AnimationId = 0
    data = _WINCOMPATTRDATA()
    data.Attribute = _WCA_ACCENT_POLICY
    data.Data = ctypes.pointer(accent)
    data.SizeOfData = ctypes.sizeof(accent)
    try:
        user32.SetWindowCompositionAttribute(wintypes.HWND(hwnd), ctypes.pointer(data))
        return True
    except Exception:
        return False


def enable_round_corners(hwnd: int) -> bool:
    if not dwmapi or not hwnd:
        return False
    try:
        pref = ctypes.c_int(_DWMWCP_ROUND)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), _DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(pref), ctypes.sizeof(pref),
        )
        return True
    except Exception:
        return False


_HWND_TOPMOST = -1
_HWND_NOTOPMOST = -2
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010


def set_topmost(hwnd: int, on: bool = True) -> bool:
    """用 SetWindowPos 强制置顶 / 取消置顶（比 pywebview 的 on_top 更可靠）。"""
    if not user32 or not hwnd:
        return False
    try:
        user32.SetWindowPos(
            wintypes.HWND(hwnd),
            ctypes.c_void_p(_HWND_TOPMOST if on else _HWND_NOTOPMOST),
            0, 0, 0, 0, _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOACTIVATE,
        )
        return True
    except Exception:
        return False


def apply_glass(title: str, tint: int | None = None) -> bool:
    """按窗口标题查找 HWND 并应用磨砂 + 圆角 + 置顶。"""
    hwnd = find_hwnd(title)
    if not hwnd:
        return False
    ok = enable_acrylic(hwnd, tint)
    enable_round_corners(hwnd)
    set_topmost(hwnd, True)
    return ok


# ---------- 窗口几何（迷你停靠 / 恢复）----------
class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", _RECT),
                ("rcWork", _RECT), ("dwFlags", ctypes.c_ulong)]


_MONITOR_DEFAULTTONEAREST = 2
_SWP_SHOWWINDOW = 0x0040

_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_LWA_COLORKEY = 0x1
# webview 透明时露出的宿主 Form 底色 = SystemColors.Control(#F0F0F0）。把它当色键键成透明，
# 迷你态就能真正透出桌面（实测本机有效）。
_FORM_BACKDROP_KEY = 0x00F0F0F0

if user32:  # 64 位下句柄是指针，必须声明签名，否则返回值被截成 32 位
    try:
        user32.MonitorFromWindow.restype = ctypes.c_void_p
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
        user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MONITORINFO)]
        user32.GetDpiForWindow.restype = ctypes.c_uint
        user32.GetDpiForWindow.argtypes = [wintypes.HWND]
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetLayeredWindowAttributes.argtypes = [
            wintypes.HWND, wintypes.COLORREF, ctypes.c_ubyte, ctypes.c_uint]
    except Exception:
        pass


def set_clickthrough_key(hwnd: int, on: bool = True) -> bool:
    """on: 给窗口加分层色键，把浅灰 Form 底键成透明（迷你态真透桌面）。
    off: 移除分层样式，恢复完整模式的正常不透明渲染。"""
    if not user32 or not hwnd:
        return False
    try:
        ex = user32.GetWindowLongW(wintypes.HWND(hwnd), _GWL_EXSTYLE)
        if on:
            user32.SetWindowLongW(wintypes.HWND(hwnd), _GWL_EXSTYLE, ex | _WS_EX_LAYERED)
            user32.SetLayeredWindowAttributes(
                wintypes.HWND(hwnd), _FORM_BACKDROP_KEY, 0, _LWA_COLORKEY)
        else:
            user32.SetWindowLongW(wintypes.HWND(hwnd), _GWL_EXSTYLE, ex & ~_WS_EX_LAYERED)
        return True
    except Exception:
        return False


def dpi_scale(hwnd: int) -> float:
    """窗口当前 DPI 缩放（1.0 = 100%，1.5 = 150%）。"""
    if not user32 or not hwnd:
        return 1.0
    try:
        dpi = user32.GetDpiForWindow(wintypes.HWND(hwnd))
        if dpi:
            return dpi / 96.0
    except Exception:
        pass
    return 1.0


def window_rect(hwnd: int):
    """返回窗口物理像素矩形 (left, top, width, height)；失败返回 None。"""
    if not user32 or not hwnd:
        return None
    r = _RECT()
    try:
        user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
    except Exception:
        return None
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)


def _work_area(hwnd: int):
    mon = user32.MonitorFromWindow(wintypes.HWND(hwnd), _MONITOR_DEFAULTTONEAREST)
    mi = _MONITORINFO()
    mi.cbSize = ctypes.sizeof(_MONITORINFO)
    user32.GetMonitorInfoW(mon, ctypes.byref(mi))
    return mi.rcWork


def dock_right(hwnd: int, w_logical: int, h_logical: int, margin: int = 12,
               valign: str = "center") -> bool:
    """缩成 w×h（逻辑像素，自动按 DPI 放大）并贴到所在显示器工作区右缘、置顶。
    valign="center" 垂直居中；valign="bottom" 贴工作区底（即任务栏/状态栏上方）。"""
    if not user32 or not hwnd:
        return False
    try:
        scale = dpi_scale(hwnd)
        pw = int(round(w_logical * scale))
        ph = int(round(h_logical * scale))
        pm = int(round(margin * scale))
        work = _work_area(hwnd)
        x = work.right - pw - pm
        if valign == "bottom":
            y = work.bottom - ph - pm          # 工作区已不含任务栏，再留 pm 间隙 → 状态栏正上方
        else:
            y = work.top + (work.bottom - work.top - ph) // 2
        user32.SetWindowPos(
            wintypes.HWND(hwnd), ctypes.c_void_p(_HWND_TOPMOST),
            int(x), int(y), pw, ph, _SWP_NOACTIVATE | _SWP_SHOWWINDOW,
        )
        return True
    except Exception:
        return False


def set_geometry(hwnd: int, x: int, y: int, w: int, h: int, topmost: bool = True) -> bool:
    """按物理像素直接设置窗口位置 + 大小（用于从迷你态恢复到之前的窗口矩形）。"""
    if not user32 or not hwnd:
        return False
    try:
        ins = _HWND_TOPMOST if topmost else _HWND_NOTOPMOST
        user32.SetWindowPos(
            wintypes.HWND(hwnd), ctypes.c_void_p(ins),
            int(x), int(y), int(w), int(h), _SWP_NOACTIVATE | _SWP_SHOWWINDOW,
        )
        return True
    except Exception:
        return False
