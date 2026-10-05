"""后台监视：盯着正在玩的那个存档，算出新解锁的节点。

纪律：
  - **只读**存档，从不写回
  - 每个槽位独立状态；同一个槽位开新周目（playTime 倒退）会自动重置
  - 第一次挂上某个槽位时做**静默回填**（已满足的节点直接标记为已解锁，不弹通知），
    否则老玩家一开就炸出十几条 —— 只有「一开始就有」那类节点例外，它会提醒一次，
    好让玩家知道这工具在工作
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from . import facts as F
from . import hints as H
from . import page as P
from . import state as S

# 采样必须盯**主存档文件**：Backup/ 是稀疏的，像 era=1 这种瞬时态可能整个被错过
POLL_INTERVAL = 2.0
NEW_GAME_BACKSTEP = 60.0        # playTime 倒退超过这么多秒就当成新周目


def log(msg: str) -> None:
    """带时间戳的日志。

    必须要有：之前日志里一行时间都没有，出问题只能猜「是检测慢了还是显示慢了」。
    """
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def increase_facts(nodes) -> list[str]:
    out: list[str] = []

    def walk(sp):
        if not sp:
            return
        if sp.get("kind") == "increase":
            out.append(sp["fact"])
        for s in sp.get("specs", []) or []:
            walk(s)
    for nd in nodes:
        walk(nd.spec)
    return sorted(set(out))


class Watcher:
    def __init__(self, nodes, site: P.Site, state, slot: str = "",
                 interval: float = POLL_INTERVAL, on_new=None, verbose=True):
        self.nodes = nodes
        self.site = site
        self.state = state
        self.slot = slot.upper() if slot else ""
        self.interval = interval
        self.on_new = on_new
        self.verbose = verbose
        self._stop = threading.Event()
        self._sig: tuple = ()
        self._thread: threading.Thread | None = None
        self.last_facts: dict = {}
        self.lag: float = -1.0                    # 上一轮：存档 mtime 到现在差多少秒
        self._seen = False                        # 成功 tick 过没有（首轮的 lag 没意义）

    # ------------------------------------------------------------------
    def _pick(self) -> tuple[str, Path | None]:
        slot = self.slot or F.auto_slot()
        return slot, F.slot_path(slot)

    def _signal(self, p: Path) -> tuple:
        try:
            st = p.stat()
            return (p.name, st.st_mtime_ns, st.st_size)
        except OSError:
            return ()

    def tick(self) -> list:
        slot, p = self._pick()
        if not p or not p.exists():
            return []
        sig = self._signal(p)
        if sig == self._sig:
            return []
        self._sig = sig

        # 存档是**游戏**写下的，它的 mtime 就是「事情发生」的时刻。
        # 跟现在比一下，就是工具自己的检测延迟（下面的日志会打出来）。
        try:
            self.lag = max(0.0, time.time() - p.stat().st_mtime)
        except OSError:
            self.lag = -1.0

        try:
            f = F.save_facts(p, slot)
        except Exception as e:                                  # noqa: BLE001
            if self.verbose:
                log(f"[跳过] 读档失败（游戏可能正在写）：{type(e).__name__}: {e}")
            self._sig = ()                                      # 下一轮重试
            return []
        self.last_facts = f

        ss = self.state.slot(slot)
        # 同一槽位开新周目？
        if ss.get("attached") and \
                f["playTime"] + NEW_GAME_BACKSTEP < ss.get("lastPlayTime", 0.0):
            if self.verbose:
                log(f"[{slot}] 检测到新周目（playTime 倒退），重置该槽位状态")
            self.state.reset_slot(slot)
            ss = self.state.slot(slot)

        # increase 类事实的基线 = 「全新存档」时的值（地板），**不是**挂上那一刻的快照
        # —— 否则半路挂上会把 increase 触发器（及其后面的 gate_all_previous）永远堵死
        base = F.increase_floor()
        ss["baseline"] = base

        newly = []
        if not ss.get("attached"):
            hit = H.evaluate(self.nodes, f, base, set())
            ss["attached"] = True
            # 回填的节点不知道确切解锁时刻 → 记 0：它们在同类里排在真正的
            # 「刚得到的」后面，内部按提示稿顺序（老玩家一开就是顺着的）
            ss["unlocked"] = {n.nid: 0.0 for n in hit}
            # 回填**一律静默**，一个也不提醒：刚装上工具就开始响铃很突傅；
            # 「一开始就有」那类也一样（`Node.silent`）。
            newly = []
            if self.verbose:
                log(f"[{slot}] 首次挂上：回填 {len(hit)} 个已满足节点（静默）")
        else:
            have = S.unlocked_of(ss)
            hit = H.evaluate(self.nodes, f, base, have)
            newly = [n for n in hit if n.nid not in have]
            if newly:
                now = time.time()
                # ★ 静默的（一开始就有 / 逐层链）记 0：不响铃、不弹浮条，也不标「新」
                have.update({n.nid: (0.0 if n.silent else now) for n in newly})
            ss["unlocked"] = have       # 顺手把老格式（列表）迁移成 {nid: 时刻}

        ss["lastPlayTime"] = f["playTime"]
        self.state.save()
        self._update_page(slot)

        # 存梅变了但没有任何新解锁也要记一笔：这样才能分清「没东西可报」和「漏了」
        # 首轮不算：`_sig` 从空变成有值，并不是游戏刚写了盘。
        first = not self._seen
        if first:
            self.lag = -1.0             # 别把这个假延迟再传给 on_new 的通知行
        lag = f"档案写入于 {self.lag:.1f}s 前" if not first and self.lag >= 0 else "首次读取"
        self._seen = True
        alert = [n for n in newly if not n.silent]
        quiet = [n for n in newly if n.silent]
        log(f"[{slot}] 存档变化（{lag}）→ 新解锁 "
            f"{','.join(n.nid for n in alert) if alert else '（无）'}"
            + (f"｜静默 {','.join(n.nid for n in quiet)}" if quiet else ""))

        if alert and self.on_new:
            self.on_new(alert)
        return newly

    def _update_page(self, slot: str) -> None:
        have = S.unlocked_of(self.state.slot(slot))
        self.site.update(P.build_payload(self.nodes, set(have), have, slot=slot))

    # ------------------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:                              # noqa: BLE001
                if self.verbose:
                    print(f"[X] 监视出错：{type(e).__name__}: {e}")
            self._stop.wait(self.interval)

    def start(self) -> "Watcher":
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="instructor-watch")
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def warmup(self) -> None:
        """先把状态读出来（不阻塞）——让页面立刻有内容。"""
        slot, p = self._pick()
        if not p or not p.exists():
            return
        try:
            f = F.save_facts(p, slot)
        except Exception:                                       # noqa: BLE001
            return
        self.last_facts = f
        self._update_page(slot)


def main() -> int:
    from pathlib import Path as _P
    from . import hints as _H
    nodes = _H.load(_P(__file__).parent / "descriptions.txt")
    print("increase 类 fact:", increase_facts(nodes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
