"""解析 `descriptions.txt`（人写的提示稿）并求值触发器。

—— 设计原则：**不要求作者改格式**。文件保持现在这种写法，本模块把它读成结构化节点。

文件语法
--------
    <触发器>[:]                     <- 顶级行；也接受 [方括号] 包起来
        - 小节标题                   <- 一个触发器下可以有多个小节
            -- 要点
                --- 子要点
    ---- 分隔线 ----
        - 这一组默认在「以上全部解锁后」才出现

支持的触发器（全部对应存档里可读的字段）
    d090解锁                                该章的图表页在书里出现（= 该章解锁）
    d060的第6页解锁完毕                      该章第 N 页在书里出现
    任意一章全章解锁完后盖戳 / 任意一章盖完章   该章已经盖过戳（全章揭示动画跑完）
    任意一章全章解锁完                          该章所有时刻都到过（还没盖戳）
    有人的面孔unblur                         首次出现「有人面孔由模糊变清晰」这个**事件**
    d030,d060,d080任意一个解锁了失踪部分      任一 disaster 的 revealedDisappearancesInBook
    玩家解锁的页面数>=15                     书里已出现的页数
    era>=1时 / era=1时                       general.era 比较（建议用 >=，理由见下）
    以上全部解锁后 / 分隔线后的默认值          等前面全部解锁

静默规则（`Node.silent`）
    两种节点**永远不响铃、不弹浮条**：
      * `always`（“一开始就有”）—— 不是游戏里发生的事
      * 逐层链（提示稿里写着“玩家可自行点选查看的内容”）—— 想看自然会去看
    它们解锁时刻记 0，所以也不再标「新」；页面上照常显示。

⚠ `era` 的瞬时值不可靠：`era=1`（暴风雨）与 `era=2`（上船）游戏都可能不落盘
（文件里 0 直接跳 3），而 `era=1` 缺失会把后面 `gate_all_previous` 的节点永远堵死
（实测有周目卡在 10/12）。装了「落盘钩子」时 `>=1` 与 `==1` 行为完全一样，
没装钩子时 `>=` 也不会堵死 —— 所以写 `era` 一律用 `>=`。
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import gamedata

DIVIDER_RE = re.compile(r"^\s*-{4,}\s*(.*?)\s*-{4,}\s*$")
SUB_RE = re.compile(r"^\s*---\s*(.*)$")
ITEM_RE = re.compile(r"^\s*--\s*(.*)$")
SEC_RE = re.compile(r"^\s*-\s+(.*)$")

CHAPTERS = tuple(gamedata.chapters())


@dataclass
class Section:
    title: str
    items: list = field(default_factory=list)     # [{text, subs:[str]}]
    key: str = ""          # 归一化后的节名，如 "救救我!(1)"
    next_key: str = ""     # 正文里 `试试“X”` 引到的下一节


REF_RE = re.compile(r"试试\s*[“\"]([^”\"]+)")
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


def norm_key(s: str) -> str:
    s = s.strip().replace("（", "(").replace("）", ")")
    return s.replace("！", "!").replace("?", "?").strip()


@dataclass
class Node:
    n: int
    trigger_raw: str
    spec: dict | None
    sections: list = field(default_factory=list)  # [Section]
    note: str = ""
    chain: bool = False          # 分隔线后的「逐层」内容：由玩家点选一层层展开
    chain_warn: str = ""
    group_text: str = ""         # 所属分隔线的原文（如「防呆（一开始就有）」）
    # 「自取型内容」：**永远静默** —— 不响铃、不弹浮条，解锁时刻记 0（所以也不标「新」）。
    #   * `always`（一开始就有）= 不是游戏里发生的事，是开场就该知道的东西；
    #   * 逐层链 = 提示稿里写明的「玩家可以自行点选查看的内容」，想看自然会去看。
    #   两类都不是「刚刚得到的新提示」，弹出来只会打断游戏。
    silent: bool = False

    @property
    def nid(self) -> str:
        return f"n{self.n:03d}"

    @property
    def label(self) -> str:
        return self.trigger_raw or (self.sections[0].title if self.sections else f"节点{self.n}")


# ------------------------------------------------------------------ 触发器
def parse_group_trigger(text: str) -> tuple[dict | None, str]:
    """分隔线的文字本身就是这一组的触发器。

    例如：
      `---- 以上都解锁完后，以下是玩家可以自行点选查看的内容（逐层） ----`
      `---- 防呆（一开始就有） ----`
      `---- 通关至少1次后 ----`
    """
    t = text.strip()
    if not t:
        return {"kind": "gate_all_previous"}, ""
    if re.search(r"以上.{0,8}(都|全部)?\s*解锁", t):
        return {"kind": "gate_all_previous"}, ""
    if re.search(r"(一开始|开局|一上来|从头|最开头)", t):
        return {"kind": "always"}, ""
    if "通关" in t:
        # ⚠ 存档里**没有**「通关过」的永久标志：
        #   - general.officeEndedOnce 只在胜利音乐播完那一刻置 true，随即被
        #     SaveData.Rewind()（SaveData.cs:99）清成 false，且实测 67 份快照里全是 false
        #   - 新开一局存档整个重置
        # 所以改用游戏自己判断「可以倒回」的条件：CanRewind() = era==2 || era==3
        # （SaveData.cs:88，也是存档界面「倒回」按钮的出现条件 ProfilesMenu.cs:160）
        return ({"kind": "fact", "fact": "era", "op": ">=", "value": 2},
                "「通关」没有永久标志，改用游戏自己的「可以倒回」条件 CanRewind()：era>=2")
    return parse_trigger(t)


def parse_trigger(raw: str) -> tuple[dict | None, str]:
    """返回 (spec, 说明)。spec 为 None 表示看不懂（会提示作者）。"""
    t = raw.strip().strip("[]").strip().rstrip("：:").strip()
    if not t:
        return None, "触发器为空"

    if t in ("以上全部解锁后", "以上全部解锁", "全部解锁后"):
        return {"kind": "gate_all_previous"}, ""

    if re.fullmatch(r"(一开始就有|开局就有|一上来就有|从一开始|一直可用|始终可用)", t):
        return {"kind": "always"}, ""

    if re.fullmatch(r"通关至少\s*1\s*次(后)?", t):
        return ({"kind": "fact", "fact": "era", "op": ">=", "value": 2},
                "「通关」没有永久标志，改用 CanRewind()：era>=2")

    m = re.fullmatch(r"玩家解锁的页面数\s*(>=|<=|==|>|<)\s*(\d+)", t)
    if m:
        return {"kind": "fact", "fact": "pagesRevealed",
                "op": m.group(1), "value": int(m.group(2))}, ""

    # 「盖戳」不是「全章到过」：全章到过是玩家还在**回忆里**那一刻（visitCount 变正），
    # 而盖戳要等回到船上才开始（MomentLogic.cs:129 的 AT_INTERP 里调
    # Game.RevealCompleteChapter）。游戏自己的判据是 disaster.revealedDisappearancesInBook
    # （SaveData.cs:370 GetWantRevealCompleteDisasterId：「全章到过 **且** 还没盖过戳」）。
    if re.fullmatch(r"任意一章(全章)?解锁(完)?后?\s*盖\s*(完)?\s*(戳|章)", t):
        return {"kind": "fact", "fact": "anyChapterStamped", "op": "==", "value": True}, ""

    if re.fullmatch(r"任意一章(全章)?解锁(完)?(后)?", t):
        return {"kind": "fact", "fact": "anyChapterComplete", "op": "==", "value": True}, ""

    # ---- 面孔类短语：都是「事件」，所以用 increase（相对首次观测基线上涨）----
    #      原因：clue 为 `-` 的人开局就不模糊（实测基线 8 人），纯状态判断会立刻误触发。
    FACE_PHRASES = {
        "有人的面孔unblur": ("facesUnblurred", "面部清晰（unblur）"),
        "有人的面孔可填写下落": ("facesFillable", "可填写下落（到过其死亡/失踪场景）"),
        "有人的面孔unblur且可填写下落": ("facesWorkable", "面部清晰且可填写下落"),
        "有人的面孔可填其下落": ("facesFillable", "可填写下落"),
    }
    for phrase, (fact, _desc) in FACE_PHRASES.items():
        if t == phrase:
            return {"kind": "increase", "fact": fact}, ""

    # 通用 `且` 组合（各子句都是状态量，用 all 是精确的）
    if "且" in t:
        specs = []
        for part in (p.strip() for p in t.split("且")):
            if not part:
                continue
            sp, note = parse_trigger(part)
            if sp is None:
                return None, f"「{part}」{note}"
            specs.append(sp)
        if specs:
            return {"kind": "all", "specs": specs}, ""

    if re.fullmatch(r"有人的?面孔\s*(unblur|清晰|解除模糊)", t, re.I):
        return {"kind": "increase", "fact": "facesUnblurred"}, ""

    m = re.fullmatch(r"([\s\S]*?)任意一个解锁了失踪部分", t)
    if m:
        chs = [c.strip() for c in re.split(r"[,，\s]+", m.group(1)) if c.strip()]
        bad = [c for c in chs if c not in CHAPTERS]
        if bad:
            return None, f"不认识的章节：{bad}"
        return {"kind": "any", "specs": [
            {"kind": "fact", "fact": f"disaster.{c}.disappearances", "op": "==", "value": True}
            for c in chs]}, ""

    m = re.fullmatch(r"era\s*(==|=|>=|>|<=|<)\s*(\d+)\s*时?", t)
    if m:
        op = "==" if m.group(1) == "=" else m.group(1)
        return {"kind": "fact", "fact": "era", "op": op, "value": int(m.group(2))}, ""

    # ★ 「暴风雨」的准确时点不是 `era>=1`：`ShipEnder.cs:28-31` 先把 era 置 1、再判断
    #   要不要先跑全章盖章动画，而盖章那一帧站点 2 的钩子就写盘 ⇒ `era>=1` 会在
    #   **盖章**那一刻就成立（实测 273 份快照里有 4 份是「era=1 但演出还没播」）。
    #   演出真正播完的标志是船尾船夫提示条：`ShipEnder.cs:78` notifyDialogInfo.Show
    #   → Dialog.Play → `Dialog.cs:96` IncStat("#dia-ship-end-notify")，
    #   而它只在 era==0 起风暴那一次播。
    if re.fullmatch(r"(暴风雨|过场|演出)(演出|过场|动画)?(播完|演完|结束|过后|已过)"
                    r"|暴风雨|船夫召唤|可以下船", t):
        # 判据放在 facts.stormEnded；这里不写 note —— lint 会把 note 当「问题」列出来，
        # 而这条只是「为什么不是 era>=1」的解释，README 的触发表里已经有。
        return {"kind": "fact", "fact": "stormEnded", "op": "==", "value": True}, ""

    m = re.fullmatch(r"(d\d{3})\s*的?\s*第\s*(\d+)\s*页\s*(?:解锁完毕|解锁完了|解锁|出现)?", t)
    if m:
        ch, page = m.group(1), int(m.group(2))
        if ch not in CHAPTERS:
            return None, f"不认识的章节：{ch}"
        mid = gamedata.chapter_moment(ch, page)
        if not mid:
            return None, f"{ch} 没有第 {page} 页（共 {len(gamedata.chapters()[ch])} 页）"
        return {"kind": "fact", "fact": f"moment.{mid}.pageRevealed",
                "op": "==", "value": True}, ""

    # ★ 「d0X0 解锁」= 该章**图表页在书里出现**，不是「该章第 1 个时刻的书页出现」。
    #   书页出现的顺序 = 玩家的探索顺序，所以后者要求玩家碰巧第一个进的就是第 1 页：
    #   实测玩家先进了 `d060-krak-m07-pass1`（CSV 第 8 个），第 VII 章的图表页已经出现
    #   （章已经解锁），但 CSV 第 1 个时刻的页面从没出现过 ⇒ 触发器永远不成立。
    #   `disaster.revealedChartInBook` 由 `Book.RevealNewPages` 在该章**任意**第一个
    #   书页浮现时置位（Book.cs:1229），所以它就是「该章解锁」的判据。
    m = re.fullmatch(r"(d\d{3})\s*的?\s*(?:章节?)?解锁", t)
    if m:
        ch = m.group(1)
        if ch not in CHAPTERS:
            return None, f"不认识的章节：{ch}"
        return {"kind": "fact", "fact": f"disaster.{ch}.chart",
                "op": "==", "value": True}, ""

    return None, "触发器写法不认识"


# ------------------------------------------------------------------ 解析
def parse(text: str) -> list[Node]:
    nodes: list[Node] = []
    cur: Node | None = None
    pending: list[str] = []
    group_spec: dict | None = None          # 当前分隔线定义的分组触发器
    group_note: str = ""
    group_text: str = ""

    def flush() -> None:
        nonlocal cur, pending
        if cur is None and not pending:
            return
        raw = " ".join(pending).strip()
        if not raw:
            if group_spec is None:
                spec, note = None, "还没写触发器（也不在任何分隔线分组里）"
            else:
                spec, note = group_spec, group_note
        else:
            spec, note = parse_trigger(raw)
            if spec is not None and group_spec is not None \
                    and group_spec.get("kind") != "always":
                spec = {"kind": "all", "specs": [group_spec, spec]}
        n = len(nodes) + 1
        nodes.append(Node(n=n, trigger_raw=raw, spec=spec,
                          sections=cur.sections if cur else [], note=note,
                          group_text=group_text))
        cur, pending = None, []

    def finish(nodes_: list[Node]) -> None:
        """填好每节的 key / next_key，并标出哪些节点是「逐层」链。"""
        for nd in nodes_:
            for s in nd.sections:
                s.key = norm_key(s.title)
            keys = {s.key for s in nd.sections if s.key}
            for s in nd.sections:
                for it in s.items:
                    m = REF_RE.search(it["text"])
                    if m:
                        ref = re.sub(r"[\s*。.”\"、]+$", "", m.group(1)).strip()
                        s.next_key = norm_key(ref)
                        break
            if len(keys) >= 2 and any(s.next_key for s in nd.sections):
                nd.chain = True
                unknown = [s.next_key for s in nd.sections
                           if s.next_key and norm_key(s.next_key) not in keys]
                if unknown:
                    nd.chain_warn = "指向不存在的节：" + ", ".join(unknown)

            # 自取型内容 -> 永远静默（见 Node.silent 的注释）
            nd.silent = bool(nd.chain or (nd.spec or {}).get("kind") == "always")

    for ln in text.splitlines():
        m = DIVIDER_RE.match(ln)
        if m:
            flush()
            group_text = m.group(1).strip()
            group_spec, group_note = parse_group_trigger(group_text)
            continue
        if not ln.strip():
            continue
        m = SUB_RE.match(ln)
        if m:
            if cur is None:
                cur = Node(n=0, trigger_raw="", spec=None)
            if cur.sections and cur.sections[-1].items:
                cur.sections[-1].items[-1]["subs"].append(m.group(1).strip())
            else:
                cur.sections.append(Section(title=f"(无标题) {m.group(1).strip()}"))
            continue
        m = ITEM_RE.match(ln)
        if m:
            if cur is None:
                cur = Node(n=0, trigger_raw="", spec=None)
            if not cur.sections:
                cur.sections.append(Section(title=""))
            cur.sections[-1].items.append({"text": m.group(1).strip(), "subs": []})
            continue
        m = SEC_RE.match(ln)
        if m:
            if cur is None:
                cur = Node(n=0, trigger_raw="", spec=None)
            cur.sections.append(Section(title=m.group(1).strip()))
            continue
        # 其余顶级行 = 新触发器
        flush()
        pending.append(ln.strip())

    flush()
    finish(nodes)
    return nodes


def load(path: Path) -> list[Node]:
    return parse(Path(path).read_text(encoding="utf-8"))


def lint(nodes: list[Node]) -> list[str]:
    """挑提示稿里的毛病 —— 供作者自查。"""
    out: list[str] = []
    for nd in nodes:
        if nd.spec is None:
            out.append(f"{nd.nid}  触发器没写/看不懂：{nd.trigger_raw!r}")
        elif nd.note:
            out.append(f"{nd.nid}  {nd.note}")
        if nd.chain_warn:
            out.append(f"{nd.nid}  {nd.chain_warn}")

        keys = [s.key for s in nd.sections if s.key]
        for k in sorted({k for k in keys if keys.count(k) > 1}):
            out.append(f"{nd.nid}  重名的小节：{k}")

        # 逐层链：除第一节外每节都应被上一节引用到
        if nd.chain:
            referenced = {s.next_key for s in nd.sections if s.next_key}
            for i, s in enumerate(nd.sections):
                if i == 0:
                    continue
                if s.key and s.key not in referenced:
                    out.append(f"{nd.nid}  「{s.title}」没有任何前一节指向它（链断了？）")

        for s in nd.sections:
            if not s.items:
                out.append(f"{nd.nid}  空小节：{s.title!r}")
            for it in s.items:
                for text in [it["text"], *it["subs"]]:
                    if text.count("**") % 2:
                        out.append(f"{nd.nid}  「{s.title}」粗体 `**` 没配平：{text[:34]}…")
                    for _t, url in LINK_RE.findall(text):
                        if "://" not in url:
                            out.append(f"{nd.nid}  链接缺协议头（网页上点不开）：{url}")
    return out


# ------------------------------------------------------------------ 求值
def eval_spec(spec: dict, facts: dict, base: dict) -> bool:
    k = spec.get("kind")
    if k == "always":
        return True
    if k == "gate_all_previous":
        return bool(base.get("__all_previous__", False))
    if k == "any":
        return any(eval_spec(s, facts, base) for s in spec["specs"])
    if k == "all":
        return all(eval_spec(s, facts, base) for s in spec["specs"])
    if k == "increase":
        # 「事件」语义：相对**地板**（全新存档时的值）上涨
        # -> 「玩家自己造成过至少一次这种变化」。地板由 facts.increase_floor 算，
        # 基线缺席时按 0（= 不假设有白送的局面）。
        return facts.get(spec["fact"], 0) > base.get(spec["fact"], 0)
    if k == "fact":
        cur, op, want = facts.get(spec["fact"], 0), spec["op"], spec["value"]
        try:
            return {"==": cur == want, "!=": cur != want, ">=": cur >= want,
                    "<=": cur <= want, ">": cur > want, "<": cur < want}[op]
        except KeyError:
            return False
    return False


def evaluate(nodes: list[Node], facts: dict, base: dict,
             unlocked: object = ()) -> list[Node]:
    """返回当前满足条件的节点。

    `unlocked` = **已解锁集合**（节点 id）。
    解锁是**粘性**的：一个节点一旦满足过就永久解锁 —— 否则像 `era=1` 这种瞬时条件
    在后续快照里不再成立，会把它后面的「以上全部解锁后」永远堵死。
    `gate_all_previous` 的语义是「**前面所有**节点都已解锁」（累计与）。
    """
    done = set(unlocked or ())
    out: list[Node] = []
    b = dict(base)
    all_prev = True
    for nd in nodes:
        if nd.nid in done:
            ok = True
        else:
            b["__all_previous__"] = all_prev
            ok = eval_spec(nd.spec, facts, b) if nd.spec else all_prev
        if ok:
            out.append(nd)
        all_prev = all_prev and ok
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="解析并列出 descriptions.txt 的节点")
    ap.add_argument("--file", default=str(Path(__file__).parent / "descriptions.txt"))
    a = ap.parse_args()
    nodes = load(Path(a.file))
    print(f"共 {len(nodes)} 个节点\n")
    for nd in nodes:
        flag = "OK " if nd.spec else "!! "
        print(f"{flag}{nd.nid}  trigger={nd.trigger_raw!r}")
        if nd.spec:
            print(f"       spec = {nd.spec}")
        if nd.note:
            print(f"       note = {nd.note}")
        for s in nd.sections:
            print(f"       - {s.title}  ({len(s.items)} 条)")
            for it in s.items:
                print(f"           -- {it['text'][:46]}")
                for sub in it["subs"]:
                    print(f"              --- {sub[:44]}")
        print()
    bad = [n for n in nodes if n.spec is None]
    print(f"看不懂 / 未写：{len(bad)} 个 -> {[n.nid for n in bad]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
