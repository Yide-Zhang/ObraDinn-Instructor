"""游戏的静态数据（时刻表 / 章节 / clue 表达式 / 区域划分）。

全部来自游戏自己的表：
  - `Moments`  CSV -> 时刻 id、`r` 列（书里的「章.节」编号）、`unlock`
  - `Crew`     CSV -> `clue` 列（BookContent.Eval 的 token 表达式）
  - `Story.cs`       -> climax 构建（Ship 58 人 / Office 2 人）

复刻的源码规则：
  - `Manifest.cs:563`   crew.clueMomentIds = clue 列按空格切分
  - `Manifest.cs:586-599` token 为 `&`/`|` 时原样保留，`-` 保留，
                        其余用 `Story.MatchMomentIdEnd()` 转成时刻 id
  - `Story.cs:321`      MatchMomentIdEnd = 第一个 `id.EndsWith(end)` 的时刻
  - `SaveData.cs:409`   HaveVisitedEntireDisaster = 该章所有时刻 visited
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from make_envelope_save import build_zones          # noqa: E402
from parse_assets import load_assets, parse_csv     # noqa: E402

# 书里的章号（罗马数字）——Moments.csv 的 r 列前缀，仅用于展示
ROMAN = {"d000": "I", "d010": "II", "d020": "III", "d030": "IV", "d040": "V",
         "d050": "VI", "d060": "VII", "d070": "VIII", "d080": "IX", "d090": "X"}


@lru_cache(maxsize=1)
def moments() -> tuple[dict, ...]:
    """按 Moments.csv 的行序返回全部时刻（顺序有意义：MatchMomentIdEnd 取第一个）。"""
    _, rows = parse_csv(load_assets()["Moments"])
    return tuple(rows)


@lru_cache(maxsize=1)
def moment_ids() -> tuple[str, ...]:
    return tuple(m["id"] for m in moments())


@lru_cache(maxsize=1)
def chapters() -> dict[str, tuple[str, ...]]:
    """disasterId -> 该章的时刻 id（CSV 行序 = 书中页序）"""
    out: dict[str, list[str]] = {}
    for m in moments():
        out.setdefault(m["id"].split("-")[0], []).append(m["id"])
    return {k: tuple(v) for k, v in out.items()}


@lru_cache(maxsize=1)
def level_of_moment() -> dict[str, str]:
    """时刻 id -> 书里的「章.节」，如 d010-cold-m00-seac -> II.1"""
    return {m["id"]: m.get("r", "") for m in moments()}


@lru_cache(maxsize=1)
def crew_clue() -> dict[str, tuple[str, ...]]:
    """crewId -> clue token 列表（已按 Manifest.cs 的规则处理）"""
    _, rows = parse_csv(load_assets()["Crew"])
    out: dict[str, tuple[str, ...]] = {}
    for r in rows:
        cid = r.get("id", "").strip()
        if not cid:
            continue
        toks = [t.strip() for t in r.get("clue", "").split(" ") if t.strip()]
        out[cid] = tuple(toks)
    return out


@lru_cache(maxsize=1)
def clue_tokens() -> dict[str, tuple[str, ...]]:
    """crewId -> 展开后的 token（`&`/`|`/`-` 原样，其余换成时刻 id）"""
    def match_end(end: str) -> str | None:
        for mid in moment_ids():            # CSV 行序，取第一个命中
            if mid.endswith(end):
                return mid
        return None

    out: dict[str, tuple[str, ...]] = {}
    for cid, toks in crew_clue().items():
        conv = []
        for t in toks:
            if t in ("&", "|", "-"):
                conv.append(t)
            else:
                conv.append(match_end(t) or "")
        out[cid] = tuple(conv)
    return out


# Story.cs:122-124 手写死的失踪名单（这些人没有尸体，climax = 整章走完）
DISAPPEAR_CREW = {
    "d030": ("sea5", "sea1"),
    "d060": ("top5", "sea2", "sead", "purser", "top8", "sea9", "bosunmate"),
    "d080": ("pass3", "pass4", "stewm4", "surgeon"),
}


@lru_cache(maxsize=1)
def climax() -> dict[str, tuple[str, str]]:
    """crewId -> (kind, ref)

    kind = "die"        ref = 该人死亡所在的时刻 id      （Story.ClimaxType.Die）
    kind = "disappear"  ref = 该人失踪所在的 disaster id （Story.ClimaxType.Disappear）

    对应 Story.cs 里 climax 的构建：先按 Moments.csv 的 `die` 列，
    再用 Story.cs:122-124 写死的失踪名单覆盖。
    """
    out: dict[str, tuple[str, str]] = {}
    for m in moments():
        for cid in (x.strip() for x in (m.get("die") or "").split(",")):
            if cid and cid != "-":
                out[cid] = ("die", m["id"])
    for did, ids in DISAPPEAR_CREW.items():
        for cid in ids:
            out[cid] = ("disappear", did)
    return out


@lru_cache(maxsize=1)
def zones() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """(全部船员, Ship 区, Office 区)"""
    crew, ship, office = build_zones()
    return tuple(crew), tuple(ship), tuple(office)


@lru_cache(maxsize=1)
def crew_fates() -> dict[str, tuple[str, ...]]:
    """crewId -> 该船员可接受的 fateId 列表（Crew.csv 的 fate 列）"""
    _, rows = parse_csv(load_assets()["Crew"])
    out = {}
    for r in rows:
        f = tuple(x.strip() for x in r.get("fate", "").split(",") if x.strip())
        if f:
            out[r["id"]] = f
    return out


# 键位来自实解结果，见 `joystickDump/按键映射表.md`
#   动作名 -> (键盘, 手柄, 鼠标)
CONTROLS = {
    "Action":   ("空格 / 回车", "A / ✕ · RB · RT · X / □", "左键"),
    "Zoom":     ("E（按住）", "LB · LT · R3（按住）", "右键（按住）"),
    "Manifest": ("Tab", "Y / △", ""),
    "Pause":    ("Esc / `", "Start / Menu", ""),
}

# 提示稿里 [方括号] 的写法和上面的动作名的对应
CHIP_ALIAS = {
    "OpenBook": "Manifest", "Open Book": "Manifest", "Book": "Manifest",
    "CloseBook": "Manifest", "Close Book": "Manifest",
    "Action": "Action", "Zoom": "Zoom", "Pause": "Pause",
}

# 键帽文字随「玩家指定的操纵器」变，只有两种：
#   kbm = 键鼠（键盘列 + 鼠标列里可用的那些拼起来）
#   pad = 手柄
DEVICES = ("kbm", "pad")
DEVICE_NAME = {"kbm": "键鼠", "pad": "手柄"}
DEVICE_NOTE = {"kbm": "键盘 / 鼠标", "pad": "Xbox · PlayStation 布局"}

# 不在 CONTROLS 里、但同样要随操纵器换词的键帽。
# 值可以是**另一个动作名**（如 "Action"）—— 那就取那个动作在这一列的文字。
DEVICE_CHIP = {
    "点击/按下":  ("点击/按下", "按下"),
    "Left Click": ("左键", "Action"),      # 手柄上没有「左键」，就是 Action
}


def chip_text(name: str) -> tuple[str, str]:
    """`[方括号]` 里的写法 -> （键鼠该显示的文字, 手柄该显示的文字）。

    两个都为空串就表示这不是一个按键，只是个普通占位。
    """
    if name in DEVICE_CHIP:
        kbm, pad = DEVICE_CHIP[name]
        ctl = CONTROLS.get(CHIP_ALIAS.get(pad, pad))
        return kbm, (ctl[1] if ctl else pad)
    ctl = CONTROLS.get(CHIP_ALIAS.get(name, name))
    if not ctl:
        return "", ""
    return " / ".join(x for x in (ctl[0], ctl[2]) if x), ctl[1]


def chapter_moment(chapter: str, page: int) -> str | None:
    """章节的第 page 页（1-based）对应的时刻 id"""
    ms = chapters().get(chapter, ())
    if 1 <= page <= len(ms):
        return ms[page - 1]
    return None


def main() -> int:
    print(f"时刻 {len(moment_ids())} 个 / 章节 {len(chapters())} 个")
    for c, ms in chapters().items():
        print(f"  {c} (第{ROMAN.get(c, '?')}章) {len(ms)} 页")
    print(f"\n有 clue 的船员 {sum(1 for v in crew_clue().values() if v)} 人")
    for cid in list(crew_clue())[:5]:
        print(f"  {cid:14s} {crew_clue()[cid]} -> {clue_tokens()[cid]}")
    crew, ship, office = zones()
    print(f"\n区域: 全部 {len(crew)} / Ship {len(ship)} / Office {len(office)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
