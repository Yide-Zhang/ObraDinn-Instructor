"""存档 -> facts。所有规则条件都从这里取数。

字段口径全部对齐游戏源码（见 save_format.md 与各处的 `# 依据` 注释）。
另一条纪律：**只读，绝不写回玩家的存档**。
"""
from __future__ import annotations

import re
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from make_envelope_save import load_save              # noqa: E402
from . import gamedata                                # noqa: E402

GENERAL_RE = re.compile(r"<general\b([^>]*)>")
MOMENT_RE = re.compile(r"<moment\b([^>]*?)/>")
DISASTER_RE = re.compile(r"<disaster\b([^>]*?)/>")
FACE_RE = re.compile(r"<face\b([^>]*?)/>")
STAT_RE = re.compile(r"<stat>\s*<id>(.*?)</id>\s*<val>(.*?)</val>\s*</stat>", re.S)
INV_RE = re.compile(r"<inventory>(.*?)</inventory>", re.S)
INV_ITEM_RE = re.compile(r"<string>(.*?)</string>", re.S)
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')

BOOL = {"true": True, "false": False}


def _attrs(tag: str) -> dict:
    return dict(ATTR_RE.findall(tag))


def _b(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return BOOL.get(v.strip().lower(), default)


def _i(v: str | None, default: int = 0) -> int:
    try:
        return int(v)          # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _f(v: str | None, default: float = 0.0) -> float:
    try:
        return float(v)        # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------- clue 求值
def _eval_clue(tokens: tuple[str, ...], visited) -> bool:
    """复刻 BookContent.Eval（BookContent.cs:833-849）。

    只看存档时 `IsInMoment` 恒为 false，所以
      - 单字符 token（`-`）-> True          (InOrHaveVisitedMoment: `momentId.Length == 1`)
      - 其余 token -> 对应时刻 visited
    注意 C# 里 `|`/`&` 是**前缀**读法：先取运算符，再各取一个操作数。
    """
    idx = 0

    def eat() -> bool:
        nonlocal idx
        tok = tokens[idx] if idx < len(tokens) else ""
        idx += 1
        if tok == "|":
            a, b = eat(), eat()
            return a or b
        if tok == "&":
            a, b = eat(), eat()
            return a and b
        if len(tok) == 1:
            return True
        return bool(tok) and visited(tok)

    try:
        return eat()
    except IndexError:
        return False


@lru_cache(maxsize=1)
def increase_floor() -> dict[str, int]:
    """increase 类事实在**全新存档**里的值（= 地板）。

    ⚠ 基线**不能**用「挂上那一刻的快照」。半路挂上一个打了很久的存档时，
    快照会让「有人面孔变清晰」这类**事件型**触发器永远不成立
    （实测 `58 > 58` 为假），而它后面还有 `gate_all_previous` 的节点要靠它 ——
    会把整条「救救我！」链永远堵死（就算玩到 60/60 也解不开）。

    地板是**由游戏数据算出来的**，与什么时候挂上无关：全新存档一个时刻都没访问过、
    一个面孔都没标对，所以
      - `facesUnblurred` = clue 表达式在零进度下就成立的人数（Crew.csv 里 clue 为 `-` 的）
      - `facesFillable` / `facesWorkable` = 0（要 `HaveVisitedClimax`，开局一个都没有）

    于是 `fact > 地板` 的意思正好是「玩家自己造成过至少一次这样的变化」。
    """
    def never(_mid: str) -> bool:
        return False
    unblurred = sum(1 for toks in gamedata.clue_tokens().values()
                    if _eval_clue(toks, never))
    return {"facesUnblurred": unblurred, "facesFillable": 0, "facesWorkable": 0}


def save_facts(path: Path, slot: str = "") -> dict:
    """读一份存档，返回扁平 facts 字典。"""
    _container, xml = load_save(Path(path))

    gen = _attrs(GENERAL_RE.search(xml).group(1)) if GENERAL_RE.search(xml) else {}
    moments = {a["id"]: a for a in (_attrs(m.group(1)) for m in MOMENT_RE.finditer(xml))}
    disasters = {a["id"]: a for a in (_attrs(m.group(1)) for m in DISASTER_RE.finditer(xml))}
    faces = {a["id"]: a for a in (_attrs(m.group(1)) for m in FACE_RE.finditer(xml))}
    stats = {i.strip(): _i(v) for i, v in STAT_RE.findall(xml)}
    inv = set(INV_ITEM_RE.findall(INV_RE.search(xml).group(1))) if INV_RE.search(xml) else set()

    f: dict = {
        "slot": slot,
        "era": _i(gen.get("era")),
        "playTime": _f(gen.get("playTime")),
        "playerFemale": _b(gen.get("playerFemale")),
        "lastVisitedMomentId": gen.get("lastVisitedMomentId", ""),
        "bookPageId": gen.get("bookPageId", ""),
        "bookVisitedLastPage": _b(gen.get("bookVisitedLastPage")),
        "bookBookmarkedCrewId": gen.get("bookBookmarkedCrewId", ""),
    }
    # 教学是否已展示（HelpedZoom / HelpedZoomBook / HelpedWatchBook / HelpedStartHunt
    # / HelpedBookUsage / HelpedBookFaceBlur / HelpedBookFaceClear / HelpedBookFatesCheck
    # / HelpedBookDifficulty / HelpedBookBookmarks）
    for k, v in gen.items():
        if k.startswith("helped"):
            f["helped." + k[len("helped"):][:1].lower() + k[len("helped") + 1:]] = _b(v)
        elif k.startswith("office"):
            f["office." + k[len("office"):][:1].lower() + k[len("office") + 1:]] = _b(v)

    for k in ("moments", "disasters"):
        pass
    for mid, a in moments.items():
        f[f"moment.{mid}.visited"] = _i(a.get("visitCount")) > 0
        f[f"moment.{mid}.visitCount"] = _i(a.get("visitCount"))
        f[f"moment.{mid}.unlocked"] = _b(a.get("unlocked"))
        f[f"moment.{mid}.ghosts"] = _b(a.get("revealedGhosts"))
        # BookContent.cs:108 页面在书里可见 <=> revealedPageInBook
        f[f"moment.{mid}.pageRevealed"] = _b(a.get("revealedPageInBook"))
    for did, a in disasters.items():
        f[f"disaster.{did}.chart"] = _b(a.get("revealedChartInBook"))
        f[f"disaster.{did}.disappearances"] = _b(a.get("revealedDisappearancesInBook"))
    for cid, a in faces.items():
        f[f"face.{cid}.markedCorrect"] = _b(a.get("markedCorrect"))
        f[f"face.{cid}.nameKnown"] = a.get("nameId", cid) != cid
        f[f"face.{cid}.fateSet"] = a.get("fateId", "") not in ("", "unknown")
        f[f"face.{cid}.clueWarning"] = _i(a.get("clueWarning"))
        f[f"face.{cid}.nameId"] = a.get("nameId", "")
        f[f"face.{cid}.fateId"] = a.get("fateId", "")
    for sid, val in stats.items():
        f[f"stat.{sid}"] = val
    for item in inv:
        f[f"inventory.{item}"] = True

    _derive(f, moments, faces, stats)
    return f


def _derive(f: dict, moments: dict, faces: dict, stats: dict) -> None:
    """派生量——规则里真正会用到的那些。"""
    # ---- 章节
    for ch, ids in gamedata.chapters().items():
        vis = [f.get(f"moment.{m}.visited", False) for m in ids]
        f[f"chapter.{ch}.visitedCount"] = sum(1 for v in vis if v)
        # SaveData.cs:409 HaveVisitedEntireDisaster
        f[f"chapter.{ch}.allVisited"] = all(vis)
        f[f"chapter.{ch}.pageCount"] = len(ids)
    f["anyChapterComplete"] = any(f.get(f"chapter.{c}.allVisited", False)
                                  for c in gamedata.chapters())

    # ---- 「盖过章了」= 游戏自己的判据
    #      `SaveData.GetWantRevealCompleteDisasterId()`（SaveData.cs:370）就是
    #      「全章到过 **且** revealedDisappearancesInBook 还是 false」⇒ 那个字段
    #      就是「本章已经走过全章揭示（盖戳）动画」的永久标记。
    #      ⚠ 它不等于 anyChapterComplete：全章到过是在**回忆里**发生的，
    #      盖戳要等玩家回到船上（MomentLogic.cs:129 的 AT_INTERP）才开始。
    f["anyChapterStamped"] = any(
        v for k, v in f.items()
        if k.startswith("disaster.") and k.endswith(".disappearances"))

    # ---- 暴风雨演出播完（船尾船夫提示条）
    #   ShipEnder.cs:78  notifyDialogInfo.Show(...) → Game.ShowDialog → Dialog.Play
    #   → Dialog.cs:96   IncStat("#dia-ship-end-notify")
    #   这条提示条**只在 era==0 起风暴那一次**播（era != 0 时 ShipEnder.Start 直接进
    #   ZoneDone，那个回调不会再跑），所以这个 stat > 0 就是「过场演出播完、可以下船」。
    #   ⚠ 不能用 `era>=1` 代替：ShipEnder.cs:28-31 是**先**把 era 置 1、**再**判断要不要
    #   先跑全章盖章动画，而盖章那一帧站点 2 的钩子就会写盘 ⇒ 磁盘上真实存在
    #   「era 已经是 1、演出还没播」的存档（273 份实测快照里有 4 份）。
    f["stormEnded"] = _i(stats.get("#dia-ship-end-notify")) > 0

    # ---- 面孔：unblur / 已解对
    # BookContent.cs:857-872 GetClueStatus -> NotYet 时用 faceBlurMaterial（即「模糊」）
    def visited(mid: str) -> bool:
        return f.get(f"moment.{mid}.visited", False)

    unblurred = 0
    for cid, toks in gamedata.clue_tokens().items():
        seen = _eval_clue(toks, visited)
        f[f"face.{cid}.clueSeen"] = seen
        f[f"face.{cid}.blurred"] = (not f.get(f"face.{cid}.markedCorrect", False)) and not seen
        if seen:
            unblurred += 1
    f["facesUnblurred"] = unblurred

    # ---- 「可填写下落」= SaveData.HaveVisitedClimax（SaveData.cs:262）
    #      书里这一页出现「下落」栏的前提（FateEditor.cs:93 -> items["right"]）
    #      游戏自己的变量名就叫 canEdit（BookTut.cs:470）
    fillable = 0
    workable = 0
    for cid, (kind, ref) in gamedata.climax().items():
        if kind == "die":
            ok = f.get(f"moment.{ref}.visited", False)          # 死亡：那一时刻 visited
        else:
            ok = f.get(f"chapter.{ref}.allVisited", False)      # 失踪：整章 visited
        f[f"face.{cid}.climaxVisited"] = ok
        f[f"face.{cid}.canEdit"] = ok
        if ok:
            fillable += 1
            if f.get(f"face.{cid}.clueSeen", False):
                workable += 1
    f["facesFillable"] = fillable          # 可填写下落
    f["facesWorkable"] = workable          # 面部清晰 **且** 可填写下落

    # ---- 页面 / 区域 / 解对数
    f["pagesRevealed"] = sum(1 for k, v in f.items() if k.endswith(".pageRevealed") and v)
    f["momentsVisited"] = sum(1 for k, v in f.items() if k.endswith(".visited") and v)

    crew, ship, office = gamedata.zones()
    correct = [c for c in crew if f.get(f"face.{c}.markedCorrect")]
    f["fates.correct"] = len(correct)
    for zname, zcrew in (("Ship", ship), ("Office", office)):
        ok = sum(1 for c in zcrew if f.get(f"face.{c}.markedCorrect"))
        f[f"fates.correct.zone.{zname}"] = ok
        f[f"fates.unsolved.zone.{zname}"] = len(zcrew) - ok
        f[f"zone.{zname}.solved"] = ok == len(zcrew)

    # ---- pending：游戏自己的判定（FateEditor.cs:5486）
    #      !markedCorrect && nameId == id && IsCorrectFate(id, fateId)
    fates = gamedata.crew_fates()
    pend = 0
    for cid, a in faces.items():
        if f.get(f"face.{cid}.markedCorrect"):
            continue
        if a.get("nameId", cid) != cid:
            continue
        if a.get("fateId", "") in fates.get(cid, ()):
            pend += 1
    f["fates.pending"] = pend
    f["fates.attempted"] = sum(1 for c in crew if f.get(f"face.{c}.fateSet"))

    f["zone-complete"] = {z: f.get(f"zone.{z}.solved", False) for z in ("Ship", "Office")}


# --------------------------------------------------------------- 存档位置
def saves_dir() -> Path | None:
    """找游戏存档目录。优先复用补丁工具的实现（跨平台）。"""
    try:
        from patcher import core as pcore
        d = pcore.saves_dir()
        if d and Path(d).is_dir():
            return Path(d)
    except Exception:                                   # noqa: BLE001
        pass
    import os
    if sys.platform == "darwin":
        p = Path.home() / "Library/Application Support/co.3909.ObraDinn"
    else:
        p = Path(os.environ.get("USERPROFILE", str(Path.home()))) / \
            "AppData/LocalLow/3909/ObraDinn"
    return p if p.is_dir() else None


SLOTS = ("P1", "P2", "P3")


def auto_slot() -> str:
    """mtime 最新的那个槽位 = 玩家正在玩的。

    注意：注册表/配置里的 `ActiveSave` 是**滞后**的（`Settings.Save()` 只在关游戏时写），
    实测它写着 P1 而实际在玩 P2，所以不能用它。
    """
    d = saves_dir()
    if not d:
        return "P2"
    best, best_t = "P2", -1.0
    for s in SLOTS:
        p = d / f"ObraDinnSave-{s}.txt"
        if p.exists() and p.stat().st_mtime > best_t:
            best, best_t = s, p.stat().st_mtime
    return best


def slot_path(slot: str) -> Path | None:
    d = saves_dir()
    if not d:
        return None
    p = d / f"ObraDinnSave-{slot.upper()}.txt"
    return p if p.exists() else None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="dump 某个槽位的 facts")
    ap.add_argument("slot", nargs="?", default="P2")
    ap.add_argument("--path", default="")
    a = ap.parse_args()

    p = Path(a.path) if a.path else slot_path(a.slot)
    if not p:
        print(f"找不到存档：{a.slot}")
        return 1
    f = save_facts(p, a.slot)
    keys = sorted(f)
    print(f"=== {p}  ({len(keys)} 条 facts) ===")
    for k in keys:
        v = f[k]
        if isinstance(v, dict):
            continue
        print(f"  {k:44s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
