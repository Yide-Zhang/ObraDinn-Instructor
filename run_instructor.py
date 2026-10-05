#!/usr/bin/env python3
"""instructor 的 app 版入口 —— 打包成 exe 后双击的就是它。

    ObraDinnInstructor.exe                 起服务 + 开 app 窗口 + 悬浮小条 + 提示音
    ObraDinnInstructor.exe --no-browser    只起服务和悬浮小条（调试用）
    ObraDinnInstructor.exe --no-bar        不要悬浮小条
    ObraDinnInstructor.exe --tab           用普通标签页打开（不开 app 窗口）
    ObraDinnInstructor.exe --port 8730 --slot P2 --interval 2

命令固定是 `run`（给了子命令就照给，所以 `notify` / `check` / `replay` 也能用），
其余参数原样转发给 `python -m instructor run` —— 参数的唯一源头还是
`instructor/__main__.py`，这里不做第二套解析。

为什么要这个文件：PyInstaller `--windowed` 打包后，Windows 上 `sys.stdout/stderr`
是 `None`（macOS 上是 `/dev/null`），程序一旦出错就什么都看不到。所以这里
**在 import `instructor` 之前**先把日志装上（`instructor.logfile`，幂等），
致命错误再用弹窗告诉用户日志在哪。
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _alert(text: str) -> None:
    """windowed exe 没有控制台，出错只能靠弹窗。"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(          # type: ignore[attr-defined]
            None, text, "奥伯拉丁 · 辅助提示", 0x10)
    except Exception:                                    # noqa: BLE001
        pass
    try:                                                 # macOS：没有 MessageBox，用 osascript
        import subprocess
        if sys.platform == "darwin":
            esc = text.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(["osascript", "-e",
                            f'display alert "奥伯拉丁 · 辅助提示" message "{esc}"'],
                           capture_output=True, timeout=30)
    except Exception:                                    # noqa: BLE001
        pass


def main() -> int:
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))

    # exe 是 --windowed，没有控制台；必须在 import instructor 之前就装好日志，
    # 否则 import 阶段的崩溃什么都留不下。install() 幂等，包里还会再调一次。
    from instructor import logfile
    log = logfile.install("参数: " + " ".join(sys.argv[1:]))

    try:
        from instructor.__main__ import CMDS, main as cli_main
        args = sys.argv[1:]

        # 把游戏的 ObraDinn.exe（或游戏文件夹、mac 的 .app）拖到本程序图标上：
        # 当作「--game」—— 记住目录 + 把书页钩子装上，然后弹窗告诉用户结果。
        # （hook 会先把原 DLL 备份到 hook-backup/，随时可以用 --restore 还原）
        if args and not args[0].startswith("-") and args[0] not in CMDS \
                and Path(args[0]).exists():
            import contextlib
            import io
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                code = cli_main(["hook", "--game", args[0], *args[1:]])
            _alert(buf.getvalue().strip() or "已完成（没有输出）")
            return code

        # 不跟子命令就默认 run；跟了就照跟（这样 exe 也能跑 notify / check / replay）
        if not args or args[0] not in CMDS:
            args = ["run", *args]
        return cli_main(args)
    except SystemExit as e:                      # argparse 的 --help / 参数错误
        return int(e.code or 0)
    except Exception:                                    # noqa: BLE001
        traceback.print_exc()
        try:
            sys.stdout.flush()
        except Exception:                                # noqa: BLE001
            pass
        _alert("启动失败。\n\n日志（最后几行）：\n" + str(log or "（日志没写成功）"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
