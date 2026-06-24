"""开机自启：往 HKCU 的 Run 键写一条指向 venv pythonw.exe + app.py 的命令。

用 pythonw.exe（不弹黑框）+ 绝对路径，登录即由 Explorer 拉起；
注册表是唯一事实来源（开 / 关 / 当前状态都直接读写它），不在 settings.json 留副本以免漂移。
"""
from __future__ import annotations

import sys

from . import config

try:
    import winreg  # 仅 Windows
except Exception:  # noqa: BLE001
    winreg = None  # type: ignore

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "Dsdio"


def _command() -> str:
    """开机要执行的命令：优先 venv 的 pythonw.exe（用户平时就这么启动），回退当前解释器。"""
    pyw = config.BASE_DIR / ".venv" / "Scripts" / "pythonw.exe"
    exe = str(pyw) if pyw.exists() else sys.executable
    return f'"{exe}" "{config.BASE_DIR / "app.py"}"'


def is_enabled() -> bool:
    """Run 键里存在 Dsdio 且非空即视为已开启。"""
    if not winreg:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            val, _ = winreg.QueryValueEx(k, _APP_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_enabled(on: bool) -> bool:
    """on=写入命令；off=删除该项。成功返回 True。"""
    if not winreg:
        return False
    try:
        # Run 键一定存在；CreateKey = 打开或创建，附带写权限
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            if on:
                winreg.SetValueEx(k, _APP_NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(k, _APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
