"""把 stdout/stderr 同时写进日志文件。

为什么要单独一个模块：打包成 `--windowed` 的 exe 时，Windows 上
`sys.stdout/stderr` 是 `None`（macOS 上是 `/dev/null`），程序出错就什么都看不到。
日志必须**两条路都有**（exe 和 `python -m instructor`），否则排查时经常
「以为在看日志、其实什么都没写」。

`install()` 是幂等的：exe 入口在 import `instructor` 之前就得装一次
（不然 import 阶段的崩溃记不下来），包里的 `main()` 再调一次不会重复套娃。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

LOG_NAME = "ObraDinnInstructor.log"
LOG_MAX = 256 * 1024

_log_path: Path | None = None
_installed = False


def path() -> Path:
    from . import state as S
    return S.data_dir() / LOG_NAME


def _rotated(p: Path):
    try:
        if p.is_file() and p.stat().st_size > LOG_MAX:
            p.replace(p.with_suffix(p.suffix + ".1"))
        return open(p, "a", encoding="utf-8", errors="replace")
    except OSError:
        return None


class Tee:
    """把输出同时写给若干流；写不动就算了，绝不让日志拖垮程序。"""

    def __init__(self, *streams):
        self.streams = [s for s in streams if s is not None]

    def write(self, data):
        for s in self.streams:
            try:
                s.write(data)
                s.flush()
            except Exception:                                # noqa: BLE001
                pass
        return len(data)

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:                                # noqa: BLE001
                pass

    def isatty(self):
        return False


def install(banner: str = "") -> Path | None:
    """装一次日志；已经装过就什么都不做。返回日志路径（失败返回 None）。"""
    global _log_path, _installed
    if _installed:
        return _log_path
    _installed = True
    try:
        p = path()
        p.parent.mkdir(parents=True, exist_ok=True)
        f = _rotated(p)
        if f is None:
            return None
        _log_path = p
        sys.stdout = Tee(sys.__stdout__, f)
        sys.stderr = Tee(sys.__stderr__, f)
        print("\n" + "=" * 66)
        print(f"启动 {time.strftime('%Y-%m-%d %H:%M:%S')}  {os.path.basename(sys.argv[0])}")
        if banner:
            print(banner)
        return p
    except Exception:                                        # noqa: BLE001
        return None
