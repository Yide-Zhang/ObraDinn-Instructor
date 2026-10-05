"""界面字体 —— 与「难度补丁」项目同款，另加斜体 / 粗体各一款。

| 用途 | 字族 | 来源 |
|---|---|---|
| 正文拉丁 | `IMFe` = IM FELL English Roman | `font_src/IMFeENrm28P.ttf` |
| 正文中文 | `SourceHanSerif` SemiBold | `font_src/SOURCEHANSERIFSC-SEMIBOLD.OTF`（**完整**那份） |
| **粗体** | `SourceHanSerif` **Heavy** | `SOURCEHANSERIFSC-HEAVY.OTF` |
| **斜体·中文** | `Hand851` 手写体 | `851tegakizatsu.otf` |
| **斜体·拉丁** | `Caveat` | `CAVEAT-REGULAR-U.TTF` |

⚠️ `851tegakizatsu` **自带完整 ASCII**（实测 A-Z 26/26、a-z 26/26），所以 CSS 里
斜体栈必须把 **Caveat 放在 851 前面** —— Latin 走 Caveat，汉字才落到 851。

原始字体太大（851 有 80 MB、Heavy 23 MB），所以按**实际会出现的字符集**裁剪到
`instructor/fonts/`（跟 `subset_fonts.py` 同一套口径：源码里的字符串字面量
+ 提示稿全文 + GB2312 一级字表 + 基础区间）。

    python -m instructor fonts            # 裁一次（有变更时才重裁）
    python -m instructor fonts --force    # 强制重裁
    python -m instructor fonts --report   # 只看字符集与现有子集大小
"""
from __future__ import annotations

import ast
import contextlib
import io
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "fonts"
CHARSET_FILE = OUT / "_charset.txt"

# 输出名 -> (源文件, 说明)
FONTS = {
    "IMFeENrm28P.ttf": (
        ROOT / "font_src/IMFeENrm28P.ttf", "IM FELL English Roman（拉丁正文）"),
    "SourceHanSerifSC-SemiBold-subset.otf": (
        # ⚠ 基准必须是 font_src 里那份**完整的** Semibold（24 MB）。
        #   以前这里写的是 `font_src/SourceHanSerifSC-SemiBold-subset.otf` ——
        #   那是别的项目早先裁过一轮的中间产物，它缺字：缺的字只能回落系统宋体。
        ROOT / "font_src/SOURCEHANSERIFSC-SEMIBOLD.OTF",
        "思源宋体 SemiBold（中文正文）"),
    "SourceHanSerifSC-Heavy-subset.otf": (
        ROOT / "SOURCEHANSERIFSC-HEAVY.OTF", "思源宋体 Heavy（粗体）"),
    "851tegakizatsu-subset.otf": (
        ROOT / "851tegakizatsu.otf", "851 手写体（斜体·中文）"),
    "Caveat-Regular.ttf": (
        ROOT / "CAVEAT-REGULAR-U.TTF", "Caveat Regular（斜体·拉丁）"),
}

EXTRA_RANGES = [
    (0x0020, 0x007E),   # ASCII 可打印
    (0x00A0, 0x00FF),   # Latin-1 补充（· × 等）
    (0x2000, 0x206F),   # 常用标点（— – … “ ” ‘ ’ 等）
    (0x2190, 0x21FF),   # 箭头
    (0x2500, 0x257F),   # 制表符
    (0x25A0, 0x25FF),   # 几何图形（◇ ◆ △ ○ 等）
    (0x2600, 0x26FF),   # 杂项符号（💡 的图形部分）
    (0x2700, 0x27BF),   # 装饰符号（✕ ✓ 等）
    (0x3000, 0x303F),   # CJK 标点
    (0xFF00, 0xFFEF),   # 全角形式
]


def _gb2312(level: str = "level1") -> set[str]:
    """GB2312 汉字（内置编解码器枚举，无需外部字表）—— 给将来改稿留余量。"""
    hi_range = range(0xB0, 0xD8) if level == "level1" else range(0xB0, 0xF8)
    out: set[str] = set()
    for hi in hi_range:
        for lo in range(0xA1, 0xFF):
            try:
                out.add(bytes([hi, lo]).decode("gb2312"))
            except UnicodeDecodeError:
                pass
    return out


def _string_literals(paths) -> set[str]:
    """只取字符串字面量，不取注释/docstring（跟 subset_fonts.py 同口径）。"""
    chars: set[str] = set()
    for p in paths:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), str(p))
        except (OSError, SyntaxError):
            continue
        docs = set()
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(body, list) and body:
                first = body[0]
                if (isinstance(first, ast.Expr)
                        and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    docs.add(id(first.value))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docs):
                chars.update(node.value)
    return chars


def charset(cjk: str = "level1") -> str:
    chars: set[str] = set()
    for lo, hi in EXTRA_RANGES:
        chars.update(chr(c) for c in range(lo, hi + 1))
    # 1) 本包所有 .py 的字符串字面量（界面文案都在这儿）
    chars |= _string_literals(sorted(HERE.glob("*.py")))
    # 2) 提示稿全文（作者写的字必须全覆盖）
    hp = HERE / "descriptions.txt"
    if hp.exists():
        chars |= set(hp.read_text(encoding="utf-8"))
    if cjk != "none":
        chars |= _gb2312(cjk)
    chars = {c for c in chars if c.isprintable() and c not in "\r\n\t"}
    return "".join(sorted(chars))


def human(n: int) -> str:
    return f"{n/1024:.1f} KB" if n < 1024 * 1024 else f"{n/1024/1024:.2f} MB"


def sources_present() -> bool:
    """源字体在不在。

    打包成 exe 后**故意不带**源字体（851 有 80 MB），所以那里没得重裁，
    直接用现成的子集就行 —— 否则每次启动都会白白试一次。
    """
    return all(src.exists() for src, _ in FONTS.values())


def up_to_date() -> bool:
    if not CHARSET_FILE.exists():
        return False
    stamp = CHARSET_FILE.stat().st_mtime
    newest = 0.0
    for p in [HERE / "descriptions.txt", *HERE.glob("*.py")]:
        if p.exists():
            newest = max(newest, p.stat().st_mtime)
    return newest <= stamp and all((OUT / n).exists() for n in FONTS)


def build(force: bool = False, cjk: str = "level1", quiet: bool = False) -> dict[str, Path]:
    """裁出子集，返回 {输出名: 路径}。已是最新则直接返回。"""
    OUT.mkdir(parents=True, exist_ok=True)
    if not force and up_to_date():
        return {n: OUT / n for n in FONTS}

    try:
        from fontTools.subset import main as pyftsubset
    except ImportError:
        if not quiet:
            print("[-] 需要 fonttools：python -m pip install fonttools")
        return {}

    cs = charset(cjk)
    CHARSET_FILE.write_text(cs, encoding="utf-8")
    n_cjk = sum(1 for c in cs if "\u4e00" <= c <= "\u9fff")
    if not quiet:
        print(f"[i] 字符集 {len(cs)} 个（汉字 {n_cjk}）-> {CHARSET_FILE.name}")

    # pyftsubset 会往 stderr 喷 `WARNING: FFTM NOT subset; dropped` 之类的无害噪声，
    # 而且它在内部自己 `configLogger(level=WARNING)` —— 改 logger 级别没用，
    # 它会把级别改回去。所以安静模式直接接住 stderr。
    if quiet:
        with contextlib.redirect_stderr(io.StringIO()):
            return _subset_all(pyftsubset, quiet)
    return _subset_all(pyftsubset, quiet)


def _subset_all(pyftsubset, quiet: bool) -> dict[str, Path]:
    out_paths: dict[str, Path] = {}
    for name, (src, desc) in FONTS.items():
        dst = OUT / name
        if not src.exists():
            if not quiet:
                print(f"[-] 找不到源字体 {src}")
            continue
        tmp = dst.with_suffix(dst.suffix + ".tmp")
        rc = pyftsubset([
            str(src),
            f"--text-file={CHARSET_FILE}",
            f"--output-file={tmp}",
            "--layout-features=*",
            "--name-IDs=*",
            "--recalc-bounds",
            "--drop-tables+=DSIG",
        ])
        if rc not in (0, None) or not tmp.exists():
            if not quiet:
                print(f"[-] {name} 子集化失败 (rc={rc})")
            continue
        before = src.stat().st_size
        shutil.move(str(tmp), str(dst))
        after = dst.stat().st_size
        out_paths[name] = dst
        if not quiet:
            print(f"[+] {desc}\n    {human(before)} -> {human(after)}  "
                  f"(-{100 * (1 - after / before):.0f}%)  {name}")
    return out_paths


def report() -> int:
    print(f"输出目录 {OUT}")
    print(f"字符集文件 {'有' if CHARSET_FILE.exists() else '没有'} "
          f"（{CHARSET_FILE.stat().st_size if CHARSET_FILE.exists() else 0} B）")
    print(f"是否最新：{'是' if up_to_date() else '否（跑 python -m instructor fonts）'}")
    for name, (src, desc) in FONTS.items():
        dst = OUT / name
        have = human(dst.stat().st_size) if dst.exists() else "—"
        have_src = human(src.stat().st_size) if src.exists() else "缺失"
        print(f"  {desc}\n    源 {have_src}   子集 {have}   {name}")
    return 0


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="裁剪界面字体")
    ap.add_argument("--force", action="store_true", help="强制重裁")
    ap.add_argument("--report", action="store_true", help="只看状态")
    ap.add_argument("--cjk", choices=["none", "level1", "full"], default="level1",
                    help="额外纳入的 GB2312 汉字量（默认 level1 = 3755 常用字）")
    a = ap.parse_args()
    if a.report:
        return report()
    build(force=a.force, cjk=a.cjk)
    print()
    return report()


if __name__ == "__main__":
    sys.exit(main())
