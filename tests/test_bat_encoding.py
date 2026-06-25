"""含中文的 .bat 必须用 GBK 编码（cmd 的母语代码页），不能用 UTF-8。

否则双击时 cmd 按系统 GBK 解析 UTF-8 的三字节中文，字符边界错乱会打散多行 if(...) 块，
触发语法错误 → 窗口闪一下就退（踩过这个坑：get-voice-model.bat 双击闪退）。
chcp 65001 救不了——它只改控制台输出代码页，改不了 cmd 解析 bat 文件用的编码。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_chinese_bat_files_use_gbk_not_utf8():
    bad = []
    for bat in sorted(ROOT.glob("*.bat")):
        raw = bat.read_bytes()
        if not any(b >= 0x80 for b in raw):
            continue                      # 纯 ASCII，无所谓
        try:
            raw.decode("utf-8")
            bad.append(bat.name)          # 能按 UTF-8 解出 = UTF-8 中文，cmd 会闪退
        except UnicodeDecodeError:
            pass                          # 不是合法 UTF-8 = GBK，正确
    assert not bad, ("这些含中文的 .bat 是 UTF-8，cmd 按 GBK 解析会打散 if() 块导致双击闪退，"
                     f"应改存 GBK：{bad}")
