"""给游戏 DLL 装「书页浮现」钩子 —— 让存档在书页浮现的同一帧落盘。

为什么需要它
------------
游戏只在 5 个时机写存档（回忆开始的 `Music` 状态、走出回忆门之后的 `ReturnToExploring`、
幽灵显形结束、暂停菜单、窗口失焦）。而 `revealedPageInBook = true` 是在书页揭示动画里
改**内存**的，下一次落盘已经是玩家读完书、走出回忆门之后了。提示工具靠轮询存档，
所以提醒只能等到那一刻。

这个钩子在 `Book.RevealNewPages` / `Book.RevealCompleteChapter` 的动画队列最后那个
回调里（就是 `StartFlash()` 那句之后）插一句 `Game.SaveActive(...)` —— 书页「啪」地
浮现的同一帧存档就落盘，提醒随之立刻弹出。

第三个站点在 `ShipEnder`：**暴风雨演出走完、船尾船夫提示条弹出**的那一帧插一句 ——
`general.era` 0 → 1 那句赋值（`ShipEnder.cs:30`）只改内存，而后面 `era=2`（上船）、
Tally 里直接 `era=3`，磁盘上可能整轮都没有 era=1。它插的是**演出结束**而不是那句赋值，
免得提醒撞进黑屏/雷声里（那一帧 era 早就是 1，落盘照样带）。

改写本身交给 `langtool`（Mono.Cecil，判据写在 `hardcore/langtool/Program.cs` 的
`RevealHookCommand`，是语义判据不是偏移，认不出来就拒绝改）；这个模块只负责：

    找游戏目录 -> 找 langtool -> 备份 -> 改写 -> 复验 -> 原子就位

`langtool revealhook ... --check` 只查不改，用来判断钩子在不在。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import settings as SET
from . import state as S

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

DLL_NAME = "Assembly-CSharp.dll"
DATA_SUBDIRS = ("ObraDinn_Data", "Data")
#: mac 的 .app 把数据藏在下面几层
MAC_TAILS = ("Contents/Resources", "Resources", "Contents")

#: 设置文件名（`game_dir` / `saves_dir`）—— 存在用户数据目录，见 settings.py
BACKUP_DIR = "hook-backup"
BACKUP_NAME = DLL_NAME + ".before-hook"


# --------------------------------------------------------------------------
# 找 langtool
# --------------------------------------------------------------------------
def _exe_name() -> str:
    return "langtool.exe" if os.name == "nt" else "langtool"


def langtool_candidates() -> list[Path]:
    """按优先级给候选：显式指定 > 随包带的那份 > 开发期构建产物 > 项目里其它工具的副本。"""
    out: list[Path] = []
    env = os.environ.get("OBRADINN_LANGTOOL")
    if env:
        out.append(Path(env))
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots += [Path(meipass) / "instructor", Path(meipass)]
    roots += [HERE, HERE.parent, HERE.parent / "instructor"]
    for r in roots:
        out.append(r / _exe_name())
    out += [
        REPO / "hardcore" / "langtool" / "bin" / "Release" / "net8.0" / _exe_name(),
        REPO / "hardcore" / "langtool" / "pub-trim" / _exe_name(),
        REPO / "hardcore" / "langtool" / "pub-osx-x64" / "langtool",
        REPO / "patcher" / "assets" / "bin" / _exe_name(),
    ]
    w = shutil.which("langtool")
    if w:
        out.append(Path(w))
    return out


def find_langtool() -> Path | None:
    for p in langtool_candidates():
        if p.is_file():
            return p
    return None


#: 能力探测只做一次（langtool 是十来 MB 的 exe，每轮都 spawn 太浪费）
_SUPPORTS: dict = {}


def supports_hook(langtool: Path) -> bool:
    """这个 langtool 认不认识 revealhook。

    用法探针：传一个不存在的参数，langtool 会把用法打到 stderr，里面有子命令清单。
    项目里 `patcher/core.py` 的 `--check-patchdll` 就是同一个套路。
    旧版 langtool（比如只带 patchdll 的那份）会在这里露馅。
    """
    key = str(langtool)
    if key in _SUPPORTS:
        return _SUPPORTS[key]
    try:
        r = _run(langtool, ["--check-revealhook"])
        text = (r.stdout or "") + (r.stderr or "")
        ok = "revealhook" in text
    except OSError:
        ok = False
    _SUPPORTS[key] = ok
    return ok


# --------------------------------------------------------------------------
# 找游戏
# --------------------------------------------------------------------------
def data_dir_in(root: Path) -> Path | None:
    """在 root（或它的 mac .app 子层）里找数据目录。"""
    for base in (root, *(root / t for t in MAC_TAILS)):
        for name in DATA_SUBDIRS:
            if (base / name / "Managed" / DLL_NAME).is_file():
                return base / name
    return None


def looks_like_game(p: Path) -> bool:
    return p.is_dir() and data_dir_in(p) is not None


def _settings_path() -> Path:
    """设置文件（页面上的设置面板用同一份）。"""
    return SET.path()


def load_settings() -> dict:
    return SET.load()


def _save_settings(d: dict) -> None:
    SET.save(d)


def _steam_libraries(steam_root: Path) -> list[Path]:
    out: list[Path] = []
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    try:
        txt = vdf.read_text("utf-8", errors="replace")
    except OSError:
        return out
    for m in re.finditer(r'"path"\s+"([^"]+)"', txt):
        out.append(Path(m.group(1).replace("\\\\", "\\")))
    return out


def candidate_games() -> list[Path]:
    out: list[Path] = []
    env = os.environ.get("OBRADINN_GAME")
    if env:
        out.append(Path(env))

    names = ("ObraDinn", "Return of the Obra Dinn")
    if sys.platform == "darwin":
        # mac 上非 Steam 安装（GOG / 直接拖进 Applications）很常见
        for base in (Path("/Applications"), Path.home() / "Applications"):
            for n in ("Return of the Obra Dinn.app", "ObraDinn.app"):
                out.append(base / n)
        out.append(Path.home() / "Library/Application Support/Steam")

    steam_roots: list[Path] = []
    if os.name == "nt":
        for d in "CDEFGH":
            steam_roots += [
                Path(f"{d}:\\Steam"),
                Path(f"{d}:\\SteamLibrary"),
                Path(f"{d}:\\Program Files (x86)\\Steam"),
                Path(f"{d}:\\Program Files\\Steam"),
                Path(f"{d}:\\Games\\Steam"),
            ]
    else:
        steam_roots.append(Path.home() / "Library/Application Support/Steam")

    libs = list(steam_roots)
    for sr in steam_roots:
        libs += _steam_libraries(sr)
    for lib in libs:
        for n in names:
            out.append(lib / "steamapps" / "common" / n)

    if os.name == "nt":
        for d in "CDEFGH":
            for n in names:
                out += [Path(f"{d}:\\GOG Games") / n, Path(f"{d}:\\Games") / n]
    return out


def _norm_game(raw: str) -> tuple[Path | None, str]:
    s = (raw or "").strip().strip('"').strip("'")
    if not s:
        return None, "没有填游戏路径"
    p = Path(s).expanduser()
    if p.is_file():                       # 多数人拖的是 ObraDinn.exe
        p = p.parent
    cands = [
        p, p.parent,
        p / "Return of the Obra Dinn.app",
        p / "Return of the Obra Dinn.app" / "Contents" / "Resources",
        p / "ObraDinn.app" / "Contents" / "Resources",
    ]
    for c in cands:
        if looks_like_game(c):
            return c, ""
    return None, (f"这个目录里找不到游戏数据文件夹：{s}\n"
                  "  Windows 请填 ObraDinn.exe 所在的目录（含 ObraDinn_Data）\n"
                  "  mac 请填 Return of the Obra Dinn.app 或它所在的目录")


def resolve_game(raw: str = "") -> tuple[Path | None, str]:
    """归一 + 记住游戏目录。raw 为空时按「记住的 / 环境变量 / 常见位置」自动找。"""
    if raw:
        p, why = _norm_game(raw)
        if p is None:
            return None, why
        _save_settings({**load_settings(), "game_dir": str(p)})
        return p, ""
    saved = load_settings().get("game_dir")
    if saved and looks_like_game(Path(saved)):
        return Path(saved), ""
    for p in candidate_games():
        if looks_like_game(p):
            _save_settings({**load_settings(), "game_dir": str(p)})
            return p, ""
    return None, ("自动找不到游戏目录 —— 用 `--game <游戏根目录>` 指定一次，之后会记住。\n"
                  "（Windows 是含 ObraDinn_Data 的那一层，mac 是 .app）")


def autodetect() -> tuple[Path | None, str]:
    """忘掉记住的路径，重新按「环境变量 / 常见安装位置」找一遍。"""
    SET.update(game_dir=None)
    return resolve_game("")


def set_game_dir(raw: str) -> tuple[Path | None, str]:
    """页面 / CLI 用：校验并记住游戏目录（和第一次「`--game <路径>`」等价）。"""
    return resolve_game(raw)


def forget_game_dir() -> None:
    SET.update(game_dir=None)


def summary() -> dict:
    """游戏目录与钩子状态（存档目录由调用方自己拼）。"""
    game, why = resolve_game("")
    lang = find_langtool()
    hook, dll = "未知（找不到游戏目录）", ""
    if game is not None:
        try:
            dll_p, _ = dll_and_deps(game)
            dll = str(dll_p)
            hook = describe_state(dll_p, lang)
        except OSError as e:                             # noqa: BLE001
            hook = f"读不到 DLL：{e}"
    return {"game_dir": str(game) if game else "",
            "game_saved": SET.get("game_dir"),
            "game_why": "" if game is not None else why,
            "langtool": str(lang) if lang else "",
            "hook": hook,
            "dll": dll}


def dll_and_deps(game: Path) -> tuple[Path, Path]:
    d = data_dir_in(game)
    if d is None:
        raise FileNotFoundError(f"{game} 里没有游戏数据目录")
    managed = d / "Managed"
    return managed / DLL_NAME, managed


# --------------------------------------------------------------------------
# 调 langtool
# --------------------------------------------------------------------------
def no_window_kwargs() -> dict:
    """Windows 上别弹黑框。

    exe 是 `--windowed` 打包的（**没有控制台**），从这种进程里 subprocess 拉一个
    console 程序（`langtool.exe` 就是），Windows 会给它**现开一个 cmd 窗口**再关掉。
    启动时正好会拉两次 —— `supports_hook()` 探一次能力、`hook_state()` 再查一次
    状态 —— 于是「GUI 出来之前闪两下黑框」。加上 CREATE_NO_WINDOW 就干净了。
    """
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}


def _run(langtool: Path, args: list[str]) -> subprocess.CompletedProcess:
    # langtool 只在输出被重定向时才切 UTF-8（capture_output 就是重定向）
    return subprocess.run([str(langtool), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          **no_window_kwargs())


def hook_state(dll: Path, langtool: Path) -> str:
    """yes / no / half / old / unknown"""
    if not dll.is_file():
        return "unknown"
    if not supports_hook(langtool):
        return "old"
    r = _run(langtool, ["revealhook", str(dll), "--check", f"--deps={dll.parent}"])
    return {0: "yes", 1: "no", 2: "half"}.get(r.returncode, "unknown")


def describe_state(dll: Path, langtool: Path | None) -> str:
    if langtool is None:
        return "未知（找不到 langtool）"
    st = hook_state(dll, langtool)
    return {"yes": "已装", "no": "未装",
            "half": "只装了一半（站点换过位置？先 --restore 再装）",
            "old": "未知（这份 langtool 是旧版，不带 revealhook）"}.get(
        st, "认不出来（游戏版本可能没验过）")


# --------------------------------------------------------------------------
# 装 / 还原
# --------------------------------------------------------------------------
def backup_path() -> Path:
    return S.data_dir() / BACKUP_DIR / BACKUP_NAME


def _backup(dll: Path) -> tuple[bool, str]:
    """第一次装的时候留一份原样，之后不动它（最接近原始的那份最有价值）。"""
    b = backup_path()
    if b.is_file():
        return True, f"已有备份：{b}"
    try:
        b.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dll, b)
    except OSError as e:
        return False, f"备份失败：{e}"
    return True, f"已备份到：{b}"


def install(raw_game: str = "", *, langtool: Path | None = None,
            quiet: bool = False) -> int:
    def say(*a) -> None:
        if not quiet:
            print(*a)

    lt = langtool or find_langtool()
    if lt is None:
        print("✘ 找不到 langtool —— 没有它改不了 DLL。")
        print("  可以把它放到本程序目录，或用 OBRADINN_LANGTOOL=<路径> 指定。")
        return 1

    game, why = resolve_game(raw_game)
    if game is None:
        print("✘ " + why)
        return 1
    dll, managed = dll_and_deps(game)
    say(f"游戏目录  {game}")
    say(f"存档 DLL  {dll}")

    st = hook_state(dll, lt)
    if st == "yes":
        say("钩子已装，无需改动。")
        return 0
    if st == "old":
        print("✘ 这份 langtool 是旧版、不带 revealhook ——")
        print("  重新构建 hardcore/langtool 再发布，或用 OBRADINN_LANGTOOL=<新 langtool 路径> 指定。")
        return 1
    if st == "unknown":
        print("✘ langtool 认不出这个 DLL（游戏版本可能没验过），拒绝改。")
        return 1
    if st == "half":
        # ⚠ 不能再往上加：旧位置那句不会被新版本认出来，两句都在的话旧的那句先执行，
        #   提醒时间根本不变（历史上站点 3 从「era=1 赋值」挪到「暴风雨演出结束」就撞过这事）
        print("⚠ DLL 里只认得出部分钩子 —— 不再往上加，免得同一件事写两次存档。")
        print("  两种可能：")
        print("    · 站点换过位置（旧版装的那句新版认不出来）⇒ 先 `hook --restore` 还原再装")
        print("    · 这个游戏版本里某个宿主方法/锚点找不到 ⇒ 那一处只能放弃")
        print("  先看是哪一个：python -m instructor hook --report")
        return 1

    ok, msg = _backup(dll)
    say(("  " if ok else "✘ ") + msg)
    if not ok:
        return 1

    tmp = dll.with_name(dll.name + ".hooktmp")
    try:
        r = _run(lt, ["revealhook", str(dll), str(tmp), f"--deps={managed}"])
        if r.returncode != 0 or not tmp.is_file():
            print("✘ 改写失败：")
            for line in (r.stdout + r.stderr).splitlines():
                print("    " + line)
            return 1
        for line in r.stdout.splitlines():
            if line.strip():
                say("  " + line.strip())

        # ★ 写盘成功 != 改对了：拿产物再查一遍，通过了才就位
        if hook_state(tmp, lt) != "yes":
            print("✘ 复验没过，产物丢弃（游戏 DLL 没动）")
            return 1

        os.replace(tmp, dll)          # 同目录内改名，原子
    except OSError as e:
        print(f"✘ 替换 DLL 失败：{e}")
        print("  游戏正在运行吗？先关掉游戏再装。")
        return 1
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

    print("✔ 钩子已装：书页浮现的那一刻存档就会落盘，提醒会立刻弹出。")
    print(f"  想还原：python -m instructor hook --restore")
    return 0


def restore(*, quiet: bool = False) -> int:
    b = backup_path()
    if not b.is_file():
        print(f"✘ 没有备份：{b}")
        return 1
    game, why = resolve_game()
    if game is None:
        print("✘ " + why)
        return 1
    dll, _ = dll_and_deps(game)
    try:
        shutil.copy2(b, dll)
    except OSError as e:
        print(f"✘ 还原失败：{e}")
        print("  游戏正在运行吗？先关掉游戏。")
        return 1
    if not quiet:
        print(f"✔ 已从备份还原：{dll}")
    return 0


def status_line() -> str:
    """给 `run` 打一行启动提示用；任何一步不成立就返回空串（不打扰）。"""
    lt = find_langtool()
    if lt is None:
        return ""
    game, _ = resolve_game()
    if game is None:
        return ""
    try:
        dll, _ = dll_and_deps(game)
    except FileNotFoundError:
        return ""
    st = hook_state(dll, lt)
    if st == "yes":
        return "书页钩子：已装（提醒在「书页浮现」那一刻弹）"
    if st == "no":
        return ("书页钩子：**未装** —— 提醒要等你走出回忆门之后才弹。"
                "想提前到书页浮现那一刻：python -m instructor hook")
    if st == "half":
        return ("书页钩子：只装了一半 —— **先 `hook --restore` 还原再装**"
                "（直接重装会在新锚点再插一句，旧的那句还在）")
    return ""
