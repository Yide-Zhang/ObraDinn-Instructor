"""提示稿的极简排版（markdown-lite）-> HTML。

支持作者已经在用的写法：
    **粗体**   *斜体*   [链接文字](url)   [按键名]
`[Zoom]` 这类按键**不做任何特殊样式**，就是把键位文字直接填进正文里
（键鼠 / 手柄两套文字同时写在 `data-kbm` / `data-pad` 上，由页面按玩家选的操纵器换）。
代码字面量（反引号）同样不做高亮，只把反引号去掉。
"""
from __future__ import annotations

import html
import re

from . import gamedata

LINK_RE = re.compile(r"\[([^\[\]]*)\]\(([^)\s]+)\)")
CODE_RE = re.compile(r"`([^`]+)`")
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
ITAL_RE = re.compile(r"\*([^*\n]+)\*")
CHIP_RE = re.compile(r"\[([^\[\]]+)\]")

_PH = "\x00{}\x00"


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def chip_html(name: str) -> str:
    """`[按键名]` -> 直接摊成正文里的键位文字（**不加任何样式**）。

    只包一层裸 `<span>` 是为了让页面能按操纵器换词；它不携带任何 CSS。
    """
    kbm, pad = gamedata.chip_text(name)
    if not kbm and not pad:                 # 不是按键，原样显示
        return esc(name)
    return (f'<span data-kbm="{esc(kbm)}" data-pad="{esc(pad)}">'
            f'{esc(kbm)}</span>')


def inline(text: str) -> str:
    """把一行正文渲染成 HTML（不含块级标签）。"""
    store: list[str] = []

    def keep(s: str) -> str:
        store.append(s)
        return _PH.format(len(store) - 1)

    # 1) 链接（必须最先，否则 [文字](url) 会被当成键帽）
    def _link(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        if "://" not in url:
            url = "https://" + url.lstrip("/")
        return keep(f'<a href="{esc(url)}" target="_blank" rel="noreferrer">'
                    f'{esc(label)}</a>')

    t = LINK_RE.sub(_link, text)
    t = CODE_RE.sub(lambda m: m.group(1), t)     # 不渲染代码块，只去反引号
    t = BOLD_RE.sub(lambda m: keep(f"<b>{esc(m.group(1))}</b>"), t)
    t = ITAL_RE.sub(lambda m: keep(f"<i>{esc(m.group(1))}</i>"), t)

    t = esc(t)                      # 转义剩余文本（占位符不含特殊字符，安全）

    t = CHIP_RE.sub(lambda m: chip_html(m.group(1)), t)

    return re.sub(r"\x00(\d+)\x00", lambda m: store[int(m.group(1))], t)


# --------------------------------------------------------------- 大类与「块」
# 页面上「一个一级元素（`- 小节`）= 一块」，不再按解锁时机把好几节塞进同一张卡。
# 四类的**获得顺序**是 防呆 → 探索 → 推理 → 倒回，页面整体**从后往前**排
# （大类倒序、节点倒序、节内也倒序）—— 最近得到的永远在最前。
CAT_PRIMER, CAT_EXPLORE, CAT_REASON, CAT_REWIND = (
    "PRIMER", "EXPLORE", "REASON", "REWIND")
CAT_RANK = {CAT_PRIMER: 0, CAT_EXPLORE: 1, CAT_REASON: 2, CAT_REWIND: 3}
CAT_NAME = {CAT_PRIMER: "防呆", CAT_EXPLORE: "探索",
            CAT_REASON: "推理", CAT_REWIND: "倒回"}

_PRIMER_RE = re.compile(r"一开始|开局|一上来|从头|防呆")


def category(nd) -> str:
    """把节点归入四类之一 —— 只用来决定页面上块的先后。"""
    if nd.chain:                        # 「救救我！」逐层链 = 推理
        return CAT_REASON
    gt = nd.group_text or ""
    spec = nd.spec or {}
    if "通关" in gt or (spec.get("fact") == "era" and spec.get("value") == 2):
        return CAT_REWIND
    if spec.get("kind") == "always" or _PRIMER_RE.search(gt):
        return CAT_PRIMER
    return CAT_EXPLORE


def blocks(nodes, unlocked, times: dict | None = None) -> list[dict]:
    """把已解锁的节点摊平成「一级元素 = 块」，并排好序。

    排序键：大类倒序 → 解锁时刻倒序 → 提示稿原序倒序 → 节内倒序。
    也就是说：**提示稿从后往前读**，连大类也是从后往前 —— 最近得到的永远在最前。
    逐层链的一层层小节在这里仍是独立条目（页面按 nid 合成一块，见 page.py 的 chainHTML）。
    """
    times = times or {}
    out: list[dict] = []
    for src, nd in enumerate(nodes):
        if nd.nid not in unlocked:
            continue
        cat = category(nd)
        t = float(times.get(nd.nid, 0.0))
        for i, s in enumerate(nd.sections):
            out.append({
                "nid": nd.nid, "idx": i, "cat": cat, "t": t, "src": src,
                "chain": bool(nd.chain),
                "title": inline(s.title) if s.title else "",
                "items": [{"text": inline(it["text"]),
                           "subs": [inline(x) for x in it["subs"]]}
                          for it in s.items],
            })
    out.sort(key=lambda b: (-CAT_RANK[b["cat"]], -b["t"], -b["src"], -b["idx"]))
    return out


_MOMENT_PAGE_RE = re.compile(r"moment\.(d\d{3})-(.+?)\.pageRevealed")
_DISASTER_RE = re.compile(r"disaster\.(d\d{3})\.disappearances")


def describe_spec(spec: dict | None) -> str:
    """把触发器翻译成一句人话。

    页面上**不显示**它（悬停也不弹），只给 CLI 用：`python -m instructor hints`。
    """
    spec = spec or {}
    kind = spec.get("kind")
    if kind == "always":
        return "开局必读"
    if kind == "gate_all_previous":
        return "以上全部解锁后"

    def one(sp: dict) -> str:
        if sp.get("kind") == "increase":
            return {"facesWorkable": "有人面孔既变清晰又可填写下落",
                    "facesUnblurred": "有人面孔变清晰",
                    "facesFillable": "有人可以填写下落"}.get(sp["fact"], "进度变化")
        fact, op, val = sp.get("fact", ""), sp.get("op", ""), sp.get("value")
        m = _MOMENT_PAGE_RE.fullmatch(fact)
        if m:
            ch, suffix = m.group(1), m.group(2)
            mid = next((x for x in gamedata.chapters().get(ch, ())
                        if x.endswith(suffix)), "")
            lvl = gamedata.level_of_moment().get(mid, "")
            if "." in lvl:
                roman, page = lvl.split(".", 1)
                return f"第 {roman} 章 第 {page} 页解锁"
            return f"第 {gamedata.ROMAN.get(ch, ch)} 章解锁"
        m = _DISASTER_RE.fullmatch(fact)
        if m:
            return f"第 {gamedata.ROMAN.get(m.group(1), m.group(1))} 章出现「失踪」页"
        if fact == "anyChapterComplete":
            return "任一章节全部走完（盖戳）"
        if fact == "pagesRevealed":
            return f"书本已解锁 {val} 页"
        if fact == "era":
            if op in (">=", "==") and val == 2:
                return "通关后（可以「倒回」）"
            if op in (">=", "==") and val == 1:
                return "暴风雨来临（全部闪回已追溯完）"
            return f"游戏阶段 {op}{val}"
        if fact == "office.endedOnce":
            return "通关后"
        return f"{fact} {op} {val}"

    if kind == "any":
        subs = [one(s) for s in spec.get("specs", [])]
        head = subs[0] if subs else ""
        return ("任一：" + head.split(" 第")[0] + "…") if len(subs) > 1 else head
    if kind == "all":
        return "同时满足：" + " + ".join(one(s) for s in spec.get("specs", []))
    if kind in ("fact", "increase"):
        return one(spec)
    return "提示"

