"""用户设置：游戏目录 / 存档目录。

就放在用户数据目录里：

    Windows  %LOCALAPPDATA%/ObraDinnInstructor/hook.json
    macOS    ~/Library/Application Support/ObraDinnInstructor/hook.json

内容（键都可以缺）：

    {"game_dir": "...", "saves_dir": "..."}

文件名沿用 `hook.json` —— 最早只有「书页钩子」用得到它，现在页面上的设置面板
也读同一个文件；改名会让老用户已经记住的路径失效。

写盘用「临时文件 + os.replace」，写坏也不会留下半个文件；出错就静默放弃
（设置丢了顶多是要重填一次，不该让程序起不来）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import state as S

NAME = "hook.json"


def path() -> Path:
    return S.data_dir() / NAME


def load() -> dict:
    try:
        d = json.loads(path().read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def save(d: dict) -> None:
    try:
        p = path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False), "utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


def update(**kv) -> dict:
    """改几个键：值为 None 或空串 = 删掉这个键。"""
    d = load()
    for k, v in kv.items():
        if v is None or v == "":
            d.pop(k, None)
        else:
            d[k] = str(v)
    save(d)
    return d


def get(key: str, default: str = "") -> str:
    return str(load().get(key) or default)
