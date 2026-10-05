"""instructor 命令行入口。

    python -m instructor hints                    列出提示稿里的节点与触发器
    python -m instructor facts [槽位]              打印某槽位当前的全部 facts
    python -m instructor check [槽位]              当前哪些节点已满足
    python -m instructor replay [槽位]             拿 Backup/ 里的真实快照按时间回放，
                                                报告每个节点「首次触发于第几秒」——
                                                这是写触发器时最有力的验证工具
    python -m instructor hook [--game <目录>]      装/查存档钩子（让提醒提前到
                                                书页出现的那一刻；--restore 还原）
    python -m instructor config                  看/改记住的路径（游戏目录、存档目录）；
                                                --game/--saves 设，--clear 全忘掉

  常用: --slot P2  --file <提示稿>  --saves <存档目录>
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import threading
import time
import webbrowser
from pathlib import Path

from . import facts as F
from . import gamedata as G
from . import hints as H
from . import logfile
from . import notify as N
from . import page as P
from . import render as R
from . import state as S
from . import watcher as W

HERE = Path(__file__).resolve().parent
DEFAULT_HINTS = HERE / "descriptions.txt"

# 收到「页面关了」的信标后等多久。刷新页面也会发信标，等这么久是为了不误杀。
PAGE_BYE_GRACE = 6.0

# 子命令表（exe 入口 `run_instructor.py` 也用它判断「第一个参数是不是子命令」）
CMDS = ("run", "page", "notify", "hints", "lint",
        "facts", "check", "replay", "curve", "runs", "fonts", "hook", "config", "state")


def hhmmss(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def auto_slot() -> str:
    return F.auto_slot()


def cmd_hints(a) -> int:
    nodes = H.load(Path(a.file))
    print(f"共 {len(nodes)} 个节点\n")
    for nd in nodes:
        flag = "OK " if nd.spec else "!! "
        why = R.describe_spec(nd.spec) if nd.spec else "（触发器未写/看不懂）"
        cat = R.CAT_NAME[R.category(nd)]
        muted = "  🔇静默" if nd.silent else ""
        print(f"{flag}{nd.nid}  [{cat}]  {nd.trigger_raw or '(无触发器)'}   →  {why}{muted}")
        if nd.note:
            print(f"       ! {nd.note}")
        if nd.spec:
            print(f"       {nd.spec}")
        if nd.silent:
            print("       🔇 永远不响铃、不弹浮条（自取型内容；解锁时刻记 0，也不标「新」）")
        if nd.chain:
            print("       ⛓ 逐层链（玩家点选展开）")
            print("          " + " → ".join(s.key for s in nd.sections))
        for s in nd.sections:
            nxt = f"  →  {s.next_key}" if s.next_key else ""
            print(f"       - {s.title}  ({len(s.items)} 条){nxt}")
        print()
    bad = [n.nid for n in nodes if n.spec is None]
    if bad:
        print(f"⚠ 触发器有问题：{bad}")
    return 0


def cmd_facts(a) -> int:
    slot = a.slot or auto_slot()
    p = Path(a.path) if a.path else F.slot_path(slot)
    if not p or not Path(p).exists():
        print(f"找不到存档：{slot}")
        return 1
    f = F.save_facts(Path(p), slot)
    print(f"=== {p} ===")
    for k in sorted(f):
        if isinstance(f[k], dict):
            continue
        print(f"  {k:44s} {f[k]}")
    return 0


def cmd_check(a) -> int:
    slot = a.slot or auto_slot()
    p = F.slot_path(slot)
    if not p:
        print(f"找不到存档：{slot}")
        return 1
    nodes = H.load(Path(a.file))
    f = F.save_facts(p, slot)
    base = F.increase_floor()
    hit = H.evaluate(nodes, f, base)
    print(f"=== {slot}  era={f['era']}  playTime={hhmmss(f['playTime'])}  "
          f"页 {f['pagesRevealed']}/49  已登记 {f['fates.correct']}/60 ===")
    done = {n.nid for n in hit}
    for nd in nodes:
        mark = "✔" if nd.nid in done else "·"
        print(f"  {mark} {nd.nid}  {nd.trigger_raw or (nd.sections[0].title if nd.sections else '')}")
    print(f"\n已满足 {len(done)}/{len(nodes)}")
    return 0


def _increase_facts(nodes) -> list[str]:
    out = []

    def walk(sp):
        if not sp:
            return
        if sp.get("kind") == "increase":
            out.append(sp["fact"])
        for k in ("specs",):
            for s in sp.get(k, []) or []:
                walk(s)
    for nd in nodes:
        walk(nd.spec)
    return out


# 游戏自己生成的备份名（SaveData.MakeBackup 的 reason + ProfilesMenu.cs:347-352）
#   -Recent / -EditFate 会被覆盖；-CorrectFates-<ts> / -Deleted-<ts> / -CopiedOver-<ts> 累积
# 我们自己工具写的（-beforexxx-<ts> / -midtest / -played …）以及 -CopiedOver 都要排除：
#   -CopiedOver- 是「被别的槽位覆盖前」的存档，属于**另一个周目**。
GAME_SUFFIX_RE = (
    r"^ObraDinnSave-(P\d)-(?:Recent|EditFate|CorrectFates-\d{14}|Deleted-\d{14})$")
GAME_BACKUP_RE = re.compile(GAME_SUFFIX_RE)


def snapshots(slot: str, root: Path | None = None,
              keep_foreign: bool = False) -> list[Path]:
    """主存档 + Backup/ 里该槽位的存档。

    默认只保留**游戏自己生成**的备份 —— 否则会把多个周目 / 我们自己改过的档
    混进同一条时间线，回放出来的「首次触发时刻」是错的。
    """
    d = root or F.saves_dir()
    if not d:
        return []
    out: list[Path] = []
    main = d / f"ObraDinnSave-{slot}.txt"
    if main.exists():
        out.append(main)
    bk = d / "Backup"
    if bk.is_dir():
        for p in sorted(bk.glob(f"ObraDinnSave-{slot}*.txt")):
            if keep_foreign or GAME_BACKUP_RE.match(p.stem):
                out.append(p)
    return out


def build_runs(slot: str, root: Path | None = None, keep_foreign: bool = False,
               gap_hours: float = 12.0):
    """把快照切成「同一周目」。

    为什么必须切：`Backup/` 会长期累积，里面可能混着好几个周目
    （实测有 20250823 的完整通关、20251020 的一次、20251225+2026 的改档/演示档）。
    只按 `playTime` 排序会把它们串成假时间线，回放出来的「首次触发时刻」就是错的。

    切法：按**文件 mtime**（真实写入顺序）排，遇到
      - mtime 间隔 > gap_hours，或
      - playTime 倒退
    就另起一个 run。
    """
    entries = []
    for p in snapshots(slot, root, keep_foreign):
        try:
            f = F.save_facts(p, slot)
        except Exception as e:                           # noqa: BLE001
            print(f"  [跳过] {p.name}: {type(e).__name__}: {e}")
            continue
        entries.append([p.stat().st_mtime, round(f["playTime"], 2), p, f])
    if not entries:
        return []
    entries.sort(key=lambda e: e[0])

    runs: list[list] = [[entries[0]]]
    for e in entries[1:]:
        prev = runs[-1][-1]
        if e[0] - prev[0] > gap_hours * 3600 or e[1] < prev[1] - 1.0:
            runs.append([])
        runs[-1].append(e)

    out = []
    for r in runs:
        seen: dict[str, tuple] = {}
        for e in r:
            seen.setdefault(hashlib.sha1(e[2].read_bytes()).hexdigest(), tuple(e))
        out.append(sorted(seen.values(), key=lambda t: t[1]))
    return out


def pick_run(runs, a):
    """选要回放的那个 run：默认「包含主存档」的那个；--run N 可指定；--run all 全用。"""
    if not runs:
        return []
    if str(a.run).lower() == "all":
        return sorted([e for r in runs for e in r], key=lambda t: t[1])
    slot = a.slot or auto_slot()
    main = F.saves_dir() / f"ObraDinnSave-{slot}.txt" if F.saves_dir() else None
    if str(a.run).isdigit():
        i = int(a.run)
        if 0 <= i < len(runs):
            return runs[i]
        print(f"  run 序号超出范围（0..{len(runs) - 1}），改用默认")
    if main and Path(main).exists():
        want = Path(main).resolve()
        for r in runs:
            if any(Path(e[2]).resolve() == want for e in r):
                return r
    return max(runs, key=len)


def describe_runs(slot, runs) -> None:
    print(f"{slot}: {len(runs)} 个周目")
    for i, r in enumerate(runs):
        ts = [e[0] for e in r]
        import datetime as _dt
        f0 = _dt.datetime.fromtimestamp(min(ts)).strftime("%Y-%m-%d %H:%M")
        f1 = _dt.datetime.fromtimestamp(max(ts)).strftime("%Y-%m-%d %H:%M")
        print(f"  run {i}: {len(r):3d} 个快照  {f0} → {f1}  "
              f"playTime {hhmmss(r[0][1])} → {hhmmss(r[-1][1])}  "
              f"页 {r[-1][3]['pagesRevealed']}/49  登记 {r[-1][3]['fates.correct']}/60")


def cmd_runs(a) -> int:
    slot = a.slot or auto_slot()
    describe_runs(slot, build_runs(slot, Path(a.saves) if a.saves else None, a.all))
    return 0


def cmd_replay(a) -> int:
    slot = a.slot or auto_slot()
    runs = build_runs(slot, Path(a.saves) if a.saves else None, a.all)
    if not runs:
        print(f"找不到 {slot} 的任何存档")
        return 1
    if len(runs) > 1:
        describe_runs(slot, runs)
    snaps = pick_run(runs, a)
    nodes = H.load(Path(a.file))
    print(f"\n回放 run: {len(snaps)} 个快照（{hhmmss(snaps[0][1])} → {hhmmss(snaps[-1][1])}）")

    inc = _increase_facts(nodes)
    # 与运行时保持一致：increase 的基线是「地板」而不是首个快照的值
    base = {k: v for k, v in F.increase_floor().items() if k in inc}
    print(f"基线（increase 地板）: " + (", ".join(f"{k}={v}" for k, v in base.items()) or "无"))

    fired: dict[str, tuple[float, Path]] = {}
    unlocked: set[str] = set()
    for _mt, pt, p, f in snaps:
        for nd in H.evaluate(nodes, f, base, unlocked):
            unlocked.add(nd.nid)
            fired.setdefault(nd.nid, (pt, p))

    print()
    for nd in nodes:
        label = nd.trigger_raw or (nd.sections[0].title if nd.sections else "")
        if nd.nid in fired:
            pt, p = fired[nd.nid]
            print(f"  ✔ {nd.nid}  @ {hhmmss(pt):>9s}  {label}")
            print(f"      首次触发于 {p.name}")
        elif nd.spec is None:
            print(f"  ! {nd.nid}  {'':>9s}  {label}   <- 触发器未写/看不懂")
        else:
            print(f"  · {nd.nid}  {'(未触发)':>9s}  {label}")
    ok = len([n for n in nodes if n.nid in fired])
    print(f"\n触发 {ok}/{len(nodes)}")
    return 0


def cmd_curve(a) -> int:
    """某个 fact 随游戏进度怎么变 —— 写触发器时用来掐时机。"""
    slot = a.slot or auto_slot()
    runs = build_runs(slot, Path(a.saves) if a.saves else None, a.all)
    if not runs:
        print(f"找不到 {slot} 的任何存档")
        return 1
    if len(runs) > 1:
        describe_runs(slot, runs)
    snaps = pick_run(runs, a)
    want = [w.strip() for w in a.fact.split(",") if w.strip()] or [
        "pagesRevealed", "facesUnblurred", "facesFillable", "facesWorkable",
        "fates.correct", "momentsVisited"]
    print(f"\n{slot}: {len(snaps)} 个快照（{hhmmss(snaps[0][1])} → {hhmmss(snaps[-1][1])}）")

    for w in want:
        print(f"\n=== {w} ===")
        last = object()
        for _mt, pt, _p, f in snaps:
            v = f.get(w)
            if v != last:
                print(f"  {hhmmss(pt)}   {v}")
                last = v
    return 0


def cmd_lint(a) -> int:
    nodes = H.load(Path(a.file))
    msgs = H.lint(nodes)
    if not msgs:
        print(f"✔ {len(nodes)} 个节点，没发现问题")
        return 0
    print(f"发现 {len(msgs)} 处问题：\n")
    for m in msgs:
        print("  " + m)
    return 1


def cmd_fonts(a) -> int:
    from . import fonts as FT
    if a.report:
        return FT.report()
    FT.build(force=a.force)
    print()
    return FT.report()


def cmd_state(a) -> int:
    """看 / 改某个槽位的「已解锁」记录。

    为什么需要这个：解锁是**粘性**的 —— 一个节点一旦解锁过就永久保留。想验证一条
    触发器到底会不会在正确的时机触发，就得先把它的记录抹掉（`--forget`），
    让它回到「还没解锁」。

    ⚠ 条件本身如果已经成立，抹掉的记录会在下一轮**立刻**被重新解锁 —— 那就说明判据
    本来就成立，不是触发时机的问题，换个还没满足该条件的存档再测。
    """
    st = S.State()
    known = st.data["slots"]
    want_slot = a.slot.upper() if a.slot else ""
    targets = [want_slot] if want_slot else sorted(known)

    if not a.forget:
        print(f"state  {st.path}")
        for k in targets:
            ss = known.get(k)
            if not ss:
                print(f"  {k}: 没有记录")
                continue
            u = S.unlocked_of(ss)
            print(f"  {k}: 已解锁 {len(u)} 个   attached={ss.get('attached')}   "
                  f"lastPlayTime={ss.get('lastPlayTime')}")
            if u:
                items = sorted(u.items(), key=lambda kv: kv[1])
                print("      " + "   ".join(
                    "{0}({1})".format(
                        nid,
                        "回填" if t == 0 else time.strftime("%m-%d %H:%M", time.localtime(t)))
                    for nid, t in items))
        return 0

    if a.forget == ["all"]:
        a.forget = sorted({nid for k in targets
                           for nid in S.unlocked_of(known.get(k) or {})})
        if not a.forget:
            print("这些槽位本来就没有解锁记录")
            return 0

    total = 0
    for k in targets:
        ss = known.get(k)
        if not ss:
            continue
        u = S.unlocked_of(ss)
        hit = [n for n in a.forget if n in u]
        if not hit:
            continue
        for n in hit:
            del u[n]
        ss["unlocked"] = u
        total += len(hit)
        print(f"  {k}: 忘掉 {', '.join(hit)}（还剩 {len(u)} 个已解锁）")
    if total:
        st.save()
        print(f"\n✔ 共忘掉 {total} 条。程序再跑起来时，它们会被当成「还没解锁」。")
        print("  如果存档里条件其实已经满足，下一轮就会立刻重新解锁并弹通知。")
    else:
        print("  没找到要忘掉的节点（拼写错了？或那个槽位本来就没解锁它）")
    return 0


def cmd_config(a) -> int:
    """看 / 改记住的路径。页面右上角「设置」面板改的是同一份东西。

        python -m instructor config                看现在是哪几个路径
        python -m instructor config --game <目录>   手动指定游戏目录（填一次就记住）
        python -m instructor config --saves <目录>  手动指定存档目录
        python -m instructor config --clear        全部忘掉，回到自动探测
    """
    from . import hook as HK, settings as SET
    if a.clear:
        SET.save({})
        print("已清空记住的路径")
        return 0
    if a.game:
        p, why = HK.set_game_dir(a.game)
        print(f"✔ 已记住游戏目录：{p}" if p else "✘ " + why)
        if p is None:
            return 1
    if a.saves:
        d = Path(a.saves).expanduser()
        if not d.is_dir():
            print(f"✘ 不是文件夹：{d}")
            return 1
        SET.update(saves_dir=str(d))
        print(f"✔ 已记住存档目录：{d}")
    rep = P.settings_report()
    src = "（手动指定）" if rep.get("game_saved") else "（自动检测）"
    print(f"游戏目录  {rep['game_dir'] or '（没找到）'}"
          + (src if rep["game_dir"] else ""))
    print(f"存档目录  {rep['saves_dir'] or rep['saves_effective'] or '（没找到）'}"
          + ("（手动指定）" if rep["saves_dir"] else "（自动探测）"))
    print(f"存档钩子  {rep['hook']}")
    print(f"langtool  {rep['langtool'] or '（找不到）'}")
    print(f"设置文件  {rep['settings_path']}")
    return 0


def cmd_hook(a) -> int:
    """装 / 查「书页浮现」钩子（让提醒提前到书页出现的那一刻）。"""
    from . import hook as HK
    if a.restore:
        return HK.restore()
    lt = HK.find_langtool()
    if a.report:
        game, why = HK.resolve_game(a.game)
        if game is None:
            print("✘ " + why)
            return 1
        dll, _ = HK.dll_and_deps(game)
        print(f"游戏目录  {game}")
        print(f"存档 DLL  {dll}")
        print(f"langtool  {lt or '（找不到）'}")
        print(f"钩子      {HK.describe_state(dll, lt)}")
        return 0
    return HK.install(a.game, langtool=lt)


def cmd_run(a) -> int:
    """真的跑起来：本地页面 + 后台监视 + 提示音 + 悬浮小条。"""
    P.ensure_fonts(quiet=not a.verbose)
    nodes = H.load(Path(a.file))
    st = S.State()
    site = P.Site(a.port)
    slot0 = (a.slot or F.auto_slot()).upper()
    site.update(P.build_payload(nodes, set(), slot=slot0))
    site.start_thread()

    def open_page() -> None:
        if a.tab:
            webbrowser.open(site.url)
            print("  窗口  普通标签页")
        else:
            print(f"  窗口  {P.open_app_window(site.url, S.data_dir() / 'browser-profile')}")

    sound = N.find_sound(a.sound)
    bar = None if a.no_bar else N.Bar(open_page, sound)

    def on_new(ns) -> None:
        """一条通知 = 「解锁了新的辅助提示！」+ 这次新出的**块**。

        块 = 页面上一个 `- 小节`。所以一个节点里有几节，就列几行（去重）。
        超了就写「…还有 N 块」——小条不能无限长。
        """
        names: list[str] = []
        for n in ns:
            got = [s.title.strip() for s in n.sections if s.title.strip()]
            if not got:                 # 没有小节的节点：退回用触发器原文 / 节点号
                got = [n.trigger_raw or n.label or n.nid]
            for t in got:
                if t not in names:
                    names.append(t)
        shown = names[:N.BAR_MAX_LINES]
        extra = len(names) - len(shown)
        body = "\n".join("- " + t for t in shown)
        if extra > 0:
            body += f"\n…还有 {extra} 块"
        lag = (f"   ← 存档写入后 {watcher.lag:.1f}s" if watcher.lag >= 0 else "")
        W.log(f"[通知] {N.BAR_TITLE} " + "／".join(shown)
              + (f"（还有 {extra} 块）" if extra > 0 else "") + lag)
        if bar:
            bar.push(body)

    watcher = W.Watcher(nodes, site, st, a.slot, a.interval, on_new)
    watcher.warmup()
    watcher.start()

    def watch_page() -> None:
        """提示页关掉就把整个程序也退掉。

        为什么必须有：exe 是 `--windowed`，没控制台。用户关掉窗口之后进程默默在后台跑，
        而且他没有任何办法关（小条没有关闭按钮，10 秒后自己消失）—— 实测就被这个坑了。
        时序：页面 `pagehide` 时用 sendBeacon 打 /api/bye（事件，不会被后台节流），
        之后等 PAGE_BYE_GRACE 秒；只要期间有新的 /api/alive（刷新页面就会发），就不杀。
        """
        while True:
            time.sleep(2.0)
            bye = site.bye_at
            if bye and site.last_page <= bye and time.time() - bye > PAGE_BYE_GRACE:
                W.log("[退出] 提示页已关闭 —— 程序退出"
                      "（想只要通知、不开页面：加 --no-browser）")
                os._exit(0)                     # state 每轮都已落盘（tmp+replace 原子），安全

    threading.Thread(target=watch_page, daemon=True, name="instructor-pagewatch").start()

    # 「书页浮现」钩子装了没有 —— 没装就意味着提醒要等玩家走出回忆门才弹，值得说一句。
    # 任何一步不成立（找不到游戏/langtool/认不出 DLL）就返回空串，不打扰。
    try:
        from . import hook as HK
        hook_note = HK.status_line()
    except Exception:                       # noqa: BLE001 —— 提示而已，绝不能影响启动
        hook_note = ""

    print(f"\n  奥伯拉丁 · 辅助提示\n"
          f"  页面  http://127.0.0.1:{site.port}/\n"
          f"  存档  {slot0}（自动跟随 mtime 最新的槽位）\n"
          f"  提示音 {sound or '（未找到 info.mp3，静音运行）'}\n"
          f"  轮询  {a.interval}s   悬浮条 {N.BAR_AUTO_HIDE}s 后自动隐藏\n"
          f"  退出  关掉提示页 ｜ 右键闭浮条 ｜ Ctrl+C（有控制台时）\n"
          + (f"  {hook_note}\n" if hook_note else "")
          + f"  状态  {st.path}\n")
    if hook_note:
        W.log("[钩子] " + hook_note)

    if not a.no_browser:
        threading.Timer(0.8, open_page).start()

    try:
        if bar:
            bar.run()                       # tkinter 必须在主线程
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    except Exception as e:                              # noqa: BLE001
        print(f"（悬浮条不可用：{type(e).__name__}: {e}）—— 改用无界面模式，"
              f"声音与页面照常工作")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    watcher.stop()
    return 0


def cmd_page(a) -> int:
    """只看页面（不起监视）。--out 落成静态 html 方便预览。"""
    P.ensure_fonts(quiet=not a.verbose)
    nodes = H.load(Path(a.file))
    slot = (a.slot or F.auto_slot()).upper()
    have = S.unlocked_of(S.State().slot(slot))
    if not a.unlock_all and not have:
        print(f"（{slot} 还没有解锁记录 —— 用 --unlock-all 先看看全部长什么样）")
    shown = {n.nid for n in nodes} if a.unlock_all else set(have)
    payload = P.build_payload(nodes, shown, have, preview=a.unlock_all, slot=slot)

    if a.out:
        out = P.write_static(payload, Path(a.out))
        print(f"已写出静态页：{out}  （直接双击就能看）")
        return 0
    site = P.Site(a.port)
    site.update(payload)
    site.start_thread()
    print(f"页面 http://127.0.0.1:{site.port}/   Ctrl+C 退出")
    if not a.no_browser:
        webbrowser.open(site.url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
    return 0


def cmd_notify(a) -> int:
    """单独试一下提示音 + 悬浮小条（不开监视、不开页面）。

    `python -m instructor notify 多行文本 --interval 12`
    —— `slot` 那个位置参数就是正文，`--interval` 顺手当展示秒数用。
    """
    msg = a.slot or ("- 便捷操作\n- 追溯尸体\n- 填写下落\n- 人物详情页\n- 叙事方法")
    snd = N.find_sound(a.sound)
    N.log(f"提示音 {snd}")
    N.log(f"悬浮条 {msg.replace(chr(10), ' ｜ ')}")
    bar = N.Bar(lambda: None, snd, auto_hide=a.interval)
    bar.push(msg)
    try:
        bar.run(exit_after=a.interval + 1.5)        # 自己退出，不用 Ctrl+C
    except Exception as e:                              # noqa: BLE001
        N.log(f"（悬浮条不可用：{type(e).__name__}: {e}）")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    # 先把日志装上（幂等）—— exe 入口已经装过一次，这里对 .py 那条路生效。
    # 注意要放在 parse_args 之前，参数错误也要能记下来。
    logfile.install("参数: " + " ".join(sys.argv[1:]))
    ap = argparse.ArgumentParser(prog="instructor", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=list(CMDS))
    ap.add_argument("slot", nargs="?", default="")
    ap.add_argument("--file", default=str(DEFAULT_HINTS), help="提示稿路径")
    ap.add_argument("--path", default="", help="直接指定某个存档文件")
    ap.add_argument("--saves", default="", help="存档目录（默认自动探测）")
    ap.add_argument("--fact", default="", help="curve: 逗号分隔的 fact 名")
    ap.add_argument("--all", action="store_true",
                    help="把非游戏生成的备份也算进来（默认排除）")
    ap.add_argument("--run", default="", dest="run",
                    help="选第几个周目（默认：包含主存档的那个；all=全部合并）")
    ap.add_argument("--port", type=int, default=P.DEFAULT_PORT)
    ap.add_argument("--interval", type=float, default=W.POLL_INTERVAL,
                    help="轮询间隔秒（默认 2）；notify 模式下是悬浮条保留秒数")
    ap.add_argument("--sound", default="", help="提示音路径（默认自动找 info.mp3）")
    ap.add_argument("--no-bar", action="store_true", help="不显示悬浮小条")
    ap.add_argument("--no-browser", action="store_true", help="不自动开浏览器")
    ap.add_argument("--tab", action="store_true",
                    help="用普通标签页打开（默认开 Edge/Chrome 的无地址栏 app 窗口）")
    ap.add_argument("--out", default="", help="page: 输出静态 html 到这个路径")
    ap.add_argument("--unlock-all", action="store_true",
                    help="page: 忽略存档，把全部节点都显示出来（预览用）")
    ap.add_argument("--force", action="store_true", help="fonts: 强制重建字体子集")
    ap.add_argument("--report", action="store_true", help="fonts/hook: 只看状态")
    ap.add_argument("--game", default="", help="hook: 游戏根目录（填一次就会记住）")
    ap.add_argument("--restore", action="store_true", help="hook: 从备份还原 DLL")
    ap.add_argument("--clear", action="store_true",
                    help="config: 清空记住的路径，回到自动探测")
    ap.add_argument("--forget", nargs="+", default=[],
                    help="state: 把节点改回未解锁（测试触发时机用，可写多个）")
    ap.add_argument("-v", "--verbose", action="store_true", help="多打点日志")
    a = ap.parse_args(argv)

    needs_file = a.cmd in ("hints", "lint", "facts", "check", "replay", "run", "page")
    if needs_file and not Path(a.file).exists():
        print(f"提示稿不存在：{a.file}")
        return 1
    return {"hints": cmd_hints, "lint": cmd_lint, "facts": cmd_facts,
            "check": cmd_check, "replay": cmd_replay, "curve": cmd_curve,
            "runs": cmd_runs, "run": cmd_run, "page": cmd_page,
            "notify": cmd_notify, "fonts": cmd_fonts, "hook": cmd_hook,
            "config": cmd_config, "state": cmd_state}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
