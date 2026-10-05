"""通知：提示音 + 屏幕角落的悬浮小条。

为什么不是系统托盘气泡：ObraDinn 默认**独占全屏**，Windows 的 Toast/气泡
在独占全屏下基本看不到。所以这里用
  ① 声音（一定能听到）
  ② 一个 tkinter 的置顶小条（overrideredirect，不抢焦点）
  ③ 点小条就打开提示页

tkinter 必须在主线程跑，所以 watcher 在后台线程、通知走 queue。
"""
from __future__ import annotations

import queue
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 悬浮小条露头后多久自己隐藏。
# 注意：这直接影响「我听到声音、过一会儿才切出来看」能不能看到那一条。
BAR_AUTO_HIDE = 45.0


def _ts() -> str:
    return time.strftime("%H:%M:%S")


def log(msg: str) -> None:
    """带时间戳的日志（和 `watcher.log` 一个格式）。"""
    print(f"[{_ts()}] {msg}")


# ------------------------------------------------------------------ 提示音
def find_sound(explicit: str = "") -> Path | None:
    cands = []
    if explicit:
        cands.append(Path(explicit))
    cands += [HERE / "info.mp3", HERE / "sounds" / "info.mp3",
              HERE.parent / "info.mp3"]
    for c in cands:
        if c.exists():
            return c
    return None


_MCI_ALIAS = "obd_instructor_snd"
_mci_opened = False
_mci_lock = threading.Lock()


def _mci(path: Path) -> bool:
    """Windows 上直接用系统自带的 MCI 播 mp3 —— 零依赖，也不弹窗口。"""
    global _mci_opened
    import ctypes
    winmm = ctypes.WinDLL("winmm.dll")
    buf = ctypes.create_unicode_buffer(256)

    def send(cmd: str) -> int:
        return winmm.mciSendStringW(cmd, buf, 256, None)

    with _mci_lock:
        if not _mci_opened:
            if send(f'open "{path}" type mpegvideo alias {_MCI_ALIAS}') != 0:
                # MCI 对含空格/非 ASCII 的路径不友好 → 拷到临时目录再来一次
                import tempfile
                tmp = Path(tempfile.gettempdir()) / "_obd_instructor_info.mp3"
                try:
                    shutil.copy2(path, tmp)
                except Exception:                          # noqa: BLE001
                    return False
                if send(f'open "{tmp}" type mpegvideo alias {_MCI_ALIAS}') != 0:
                    return False
            _mci_opened = True
        send(f"seek {_MCI_ALIAS} to start")
        return send(f"play {_MCI_ALIAS}") == 0


def play_sound(path: Path | None, block: bool = False) -> bool:
    """尽力播放；失败就静默返回 False（不能因为没声音就崩）。"""
    if not path:
        return False
    try:
        if sys.platform == "win32":
            if _mci(path):
                return True
        elif sys.platform == "darwin":
            cmd = ["afplay", str(path)]
            (subprocess.run if block else subprocess.Popen)(cmd)      # noqa: S603
            return True
        # 通用退路：ffplay（静音画面）
        ffplay = shutil.which("ffplay")
        if ffplay:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen([ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet",
                              str(path)], creationflags=flags)        # noqa: S603
            return True
        # 最后：winsound（只支持 wav）
        if sys.platform == "win32" and path.suffix.lower() == ".wav":
            import winsound
            winsound.PlaySound(str(path), winsound.SND_ASYNC | winsound.SND_FILENAME)
            return True
    except Exception:                                          # noqa: BLE001
        pass
    return False


# ------------------------------------------------------------------ 悬浮小条
# 游戏调色板（与页面 CSS 里的 --bg / --fg 是同一对值）
GAME_BG = "#333319"
GAME_FG = "#E5FFFF"

# 悬浮小条露头后多久自己隐藏。
# 注意：这直接影响「我听到声音、过一会儿才切出来看」能不能看到那一条。
BAR_AUTO_HIDE = 10.0

#: 小条的标题行（下面接一串 `- 块名`）
BAR_TITLE = "解锁了新的辅助提示！"
#: 最多列几块，超了写「…还有 N 块」（免得小条把屏幕占满）
BAR_MAX_LINES = 6

#: 要用的字体族（真名，不是页面里的 CSS 名）。
#: 需要调 `_register_fonts()` 把它们注册进本进程，否则 Tk 认不出来。
FONT_BODY_KEYS = ("Source Han Serif SC SemiBold", "Source Han Serif SC",
                  "Songti SC", "SimSun", "Microsoft YaHei UI", "Arial")
FONT_BOLD_KEYS = ("Source Han Serif SC Heavy", "Source Han Serif SC SemiBold",
                  "Source Han Serif SC", "Songti SC", "SimSun",
                  "Microsoft YaHei UI", "Arial")
FONT_FILES = ("SourceHanSerifSC-SemiBold-subset.otf",
              "SourceHanSerifSC-Heavy-subset.otf",
              "IMFeENrm28P.ttf", "851tegakizatsu-subset.otf",
              "Caveat-Regular.ttf")


def _mac_register(path: Path) -> bool:
    """macOS：CoreText 的 CTFontManagerRegisterFontsForURL（scope = Process）。"""
    import ctypes
    cf = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    ct = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreText.framework/CoreText")
    cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
    cf.CFURLCreateFromFileSystemRepresentation.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    ct.CTFontManagerRegisterFontsForURL.restype = ctypes.c_bool
    ct.CTFontManagerRegisterFontsForURL.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
    raw = str(path).encode("utf-8")
    url = cf.CFURLCreateFromFileSystemRepresentation(None, raw, len(raw), False)
    if not url:
        return False
    ok = bool(ct.CTFontManagerRegisterFontsForURL(url, 1, None))   # 1 = Process
    cf.CFRelease(url)
    return ok


def register_fonts() -> list[Path]:
    """把随包的字体子集**私有**注册进本进程，让 Tk 也能用和页面一样的字体。

    磁盘上的子集没装进系统，所以必须显式注册：
      Windows  gdi32.AddFontResourceExW(..., FR_PRIVATE = 0x10)  （不改系统）
      macOS    CTFontManagerRegisterFontsForURL(scope = Process)
    失败就只是用不上那几个字面，自动退到系统字体，不影响功能。
    """
    d = HERE / "fonts"
    if not d.is_dir():
        return []
    added: list[Path] = []
    for name in FONT_FILES:
        p = d / name
        if not p.is_file():
            continue
        try:
            if sys.platform == "win32":
                import ctypes
                fr_private = 0x10
                if ctypes.windll.gdi32.AddFontResourceExW(str(p), fr_private, 0) == 0:
                    continue
            elif sys.platform == "darwin":
                if not _mac_register(p):
                    continue
            else:
                continue
        except Exception:                                    # noqa: BLE001
            continue
        added.append(p)
    return added


def _pick_family(keys: tuple[str, ...], available: set[str]) -> str:
    for k in keys:
        if k.lower() in available:
            return k
    return keys[-1]        # 实在没有就用候选表最后一个（通常是系统字体）


class Bar:
    """屏幕右下角的置顶小条。`run()` 要在主线程调用。"""

    def __init__(self, on_open, sound: Path | None = None,
                 auto_hide: float = BAR_AUTO_HIDE):
        self.on_open = on_open
        self.sound = sound
        self.auto_hide = auto_hide
        self.q: queue.Queue = queue.Queue()
        self._root = None
        self._label = None
        self._title = None
        self._hide_job = None
        self._placed_logged = False
        self._pending: list[str] = []

    def push(self, text: str, title: str = BAR_TITLE) -> None:
        """后台线程调这个。带上游时间戳，好在日志里量出「入队→显示」的延迟。

        `text` 是小条正文（一行一块，形如 `- 块名`，可多行）。
        """
        self.q.put((time.time(), title, text))

    # ---- 主线程
    def run(self, exit_after: float = 0.0) -> None:
        """`exit_after > 0` 时到点自动退出（`notify` 自测用，不然要 Ctrl+C）。"""
        import tkinter as tk
        import tkinter.font as tkfont

        register_fonts()                                       # 悄悄失败没关系
        root = tk.Tk()
        self._root = root
        root.overrideredirect(True)
        root.attributes("-topmost", True)

        bg, fg = GAME_BG, GAME_FG
        try:
            have = {f.lower() for f in tkfont.families(root)}
        except Exception:                                       # noqa: BLE001
            have = set()
        fam_body = _pick_family(FONT_BODY_KEYS, have)
        fam_bold = _pick_family(FONT_BOLD_KEYS, have)

        # 描边用满强度 fg —— 页面上「新」块的描边就是这么变亮的
        frame = tk.Frame(root, bg=bg, bd=0, highlightthickness=1,
                         highlightbackground=fg)
        frame.pack(fill="both", expand=True)
        self._title = tk.Label(frame, text=BAR_TITLE, bg=bg, fg=fg,
                               font=(fam_bold, 12), padx=14, pady=0,
                               anchor="w", justify="left", cursor="hand2")
        self._title.pack(anchor="w", pady=(10, 3))
        self._label = tk.Label(frame, text="", bg=bg, fg=fg,
                               font=(fam_body, 11), padx=14, pady=0,
                               anchor="w", justify="left", cursor="hand2",
                               wraplength=460)
        self._label.pack(anchor="w", pady=(0, 10))

        # 没有叉号：想提前收起就左键（会顺手打开提示页），10 秒后自己消失。
        # 右键 = 退出整个程序（exe 是 --windowed，没有控制台）。
        for w in (self._label, self._title, frame):
            w.bind("<Button-1>", self._clicked)
            w.bind("<Button-3>", lambda _e: self._quit())

        # 先摆到屏幕外，等第一条通知再露头
        root.geometry("+0+0")
        root.withdraw()
        root.after(250, self._poll)
        if exit_after > 0:
            root.after(int(exit_after * 1000), root.destroy)
        self._root_ok = True
        root.mainloop()

    def _place(self) -> None:
        r = self._root
        r.update_idletasks()
        w, h = r.winfo_width(), r.winfo_height()
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        r.geometry(f"+{sw - w - 24}+{sh - h - 64}")
        # geometry() 要到下一轮 idle 才生效 —— 不 update 的话读回的还是旧位置（差点把我骗了）
        r.update_idletasks()

    def _show(self, title: str, text: str) -> None:
        self._title.config(text=title or BAR_TITLE)
        self._label.config(text=text)
        self._root.deiconify()
        # ⚠ withdraw/deiconify 之后 Windows 上 topmost 属性会失效，
        #    不重新设一次的话小条其实弹了、但被压在游戏底下 ——
        #    表现就是「等你切回来才看到」。
        try:
            self._root.attributes("-topmost", True)
        except Exception:                                   # noqa: BLE001
            pass
        try:
            self._root.lift()
        except Exception:                                   # noqa: BLE001
            pass
        self._place()
        if not self._placed_logged:
            self._placed_logged = True
            r = self._root
            log(f"[通知] 小条位置 ({r.winfo_rootx()},{r.winfo_rooty()})"
                f" 大小 {r.winfo_width()}x{r.winfo_height()}"
                f" 屏幕 {r.winfo_screenwidth()}x{r.winfo_screenheight()}")
        if self._hide_job:
            self._root.after_cancel(self._hide_job)
        if self.auto_hide > 0:
            self._hide_job = self._root.after(int(self.auto_hide * 1000), self._hide)

    def _hide(self) -> None:
        self._hide_job = None
        self._root.withdraw()

    def _clicked(self, _evt) -> None:
        self._hide()
        log("[通知] 被点击 → 打开提示页")
        try:
            self.on_open()
        except Exception:                                   # noqa: BLE001
            pass

    def _quit(self) -> None:
        """右键小条 = 退出整个程序。

        没这个就没有别的办法退了：exe 是 `--windowed`（没控制台），
        而 ✕ 只是收起这次通知。
        """
        log("[退出] 小条上点了右键 —— 退出程序")
        try:
            self._root.destroy()
        except Exception:                                   # noqa: BLE001
            pass

    def _poll(self) -> None:
        # ⚠ 一定要写在 finally 里重排。这是 tkinter 的 after 回调链：
        #    只要这里抛一次非 queue.Empty 的异常，`after` 就不会排下一轮，
        #    **之后永远不再有任何通知**（那时你只剩页面轮询一条路，
        #    而页面轮询在后台是被 Chrome 掉帧的）。
        try:
            while True:
                t0, title, text = self.q.get_nowait()
                ok = play_sound(self.sound)                  # 每条通知响一次
                self._show(title, text)
                log(f"[通知] 小条已显示｜响铃 {'OK' if ok else '**失败**'}"
                    f"｜入队后 {time.time() - t0:.2f}s")
        except queue.Empty:
            pass
        except Exception as e:                              # noqa: BLE001
            log(f"[通知] 显示失败：{type(e).__name__}: {e}")
        finally:
            try:
                self._root.after(250, self._poll)
            except Exception:                               # noqa: BLE001
                pass

    # ---- 后台线程调用
    def open_page(self, url: str) -> None:
        webbrowser.open(url)


def main() -> int:
    snd = find_sound()
    print(f"提示音: {snd}")
    print("播放中…", "OK" if play_sound(snd, block=True) else "失败")
    return 0


if __name__ == "__main__":
    sys.exit(main())
