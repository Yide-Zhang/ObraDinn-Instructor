"""每个槽位的持久状态。

存在用户数据目录（不动游戏存档）：
    Windows  %LOCALAPPDATA%/ObraDinnInstructor/state.json
    macOS    ~/Library/Application Support/ObraDinnInstructor/state.json

内容：
  slot -> {
    "attached":   bool          是否已经「挂上」（第一次看到这个槽位时做静默回填）
    "unlocked":   {nid: 时刻}   已解锁节点（**粘性**：一旦解锁永久保留）
                                时刻是 unix 秒，用来把「最近得到的」排在页面最前；
                                0 表示不知道（首次挂上时的回填、或老格式迁移过来的）
    "baseline":   {fact: v}     increase 类 fact 的基线（挂上那一刻的值）
    "lastPlayTime": float       用来识别「同一个槽位开了新周目」
  }
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def data_dir() -> Path:
    if sys.platform == "darwin":
        p = Path.home() / "Library/Application Support/ObraDinnInstructor"
    else:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        p = Path(base) / "ObraDinnInstructor"
    p.mkdir(parents=True, exist_ok=True)
    return p


class State:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else data_dir() / "state.json"
        self.data: dict = {"version": 1, "slots": {}}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:                              # noqa: BLE001
                self.data = {"version": 1, "slots": {}}
        self.data.setdefault("version", 1)
        self.data.setdefault("slots", {})

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, self.path)

    def slot(self, name: str) -> dict:
        return self.data["slots"].setdefault(name, {})

    def reset_slot(self, name: str) -> None:
        self.data["slots"][name] = {}


def unlocked_of(ss: dict) -> dict[str, float]:
    """取槽位的 {nid: 解锁时刻}，并兼容老格式（列表）。

    老格式只知道「解锁了」不知道何时 —— 时间记 0，于是它们在同类里按提示稿
    顺序排（而不是倒序）：老玩家第一次挂上时，页面读起来就是顺着的。
    """
    u = ss.get("unlocked")
    if isinstance(u, dict):
        return {str(k): float(v or 0.0) for k, v in u.items()}
    return {str(k): 0.0 for k in (u or [])}


def main() -> int:
    st = State()
    print(f"state: {st.path}")
    for k, v in st.data["slots"].items():
        u = unlocked_of(v)
        print(f"  {k}: attached={v.get('attached')} unlocked={len(u)} "
              f"baseline={v.get('baseline')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
