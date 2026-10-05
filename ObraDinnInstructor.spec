# -*- mode: python ; coding: utf-8 -*-
#
# 奥伯拉丁 · 辅助提示（app 版）
#
#   python -m PyInstaller --noconfirm ObraDinnInstructor.spec
#   -> Windows: dist/ObraDinnInstructor/ObraDinnInstructor.exe
#   -> macOS:   dist/ObraDinnInstructor.app  （spec 里按平台加 BUNDLE）
#
# 说明：
#   * one-folder（不是 one-file）—— 子集字体有 16 MB，one-file 每次启动都要解压一遍。
#   * **不带源字体**（851 有 80 MB），所以 exe 里不能重裁字体；
#     `instructor.page.ensure_fonts()` 会先问 `fonts.sources_present()`，没有源就直接用现成的子集。
#   * **不带 patcher**——`facts.saves_dir()` 里那条 `from patcher import core` 在 try 里，
#     拿不到就回落到硬编码的 `%USERPROFILE%\AppData\LocalLow\3909\ObraDinn`。
#   * `txtAssetDump` 必须打进去：`parse_assets.load_assets()` 按 `Path(__file__).parent` 找它。
#   * `langtool`（win: exe / mac: 无后缀那个）必须打进去：`instructor/hook.py` 靠它读/改
#     游戏 DLL（装「书页浮现」钩子）。它是 .NET 自包含单文件，~10 MB；
#     放进包后落点正好是 `instructor/hook.py` 旁边的 `HERE`，`find_langtool()` 第一个就找它。
#     找不到也不致命：`hook.py` 会退化成「不提供钩子」，提示时机回到走出回忆门之后。
#   * 图标：`icon-instructor.ico` 给 exe，`icon-instructor.png` 给页面 favicon
#     （`instructor/page.py` 按 `Path(__file__).parent` 找它，开发期回落到仓库根）。
import os
import sys

R = SPECPATH                      # 本 spec 所在目录 = 仓库根
_MAC = sys.platform == 'darwin'
#: langtool 的发布目录/文件名按平台不同（mac 是 .app 式的无后缀可执行文件）
_LT_DIR = 'pub-trim' if os.name == 'nt' else 'pub-osx-x64'
_LT_EXE = 'langtool.exe' if os.name == 'nt' else 'langtool'

_datas = [
    (os.path.join(R, 'instructor', 'descriptions.txt'), 'instructor'),
    (os.path.join(R, 'instructor', 'fonts'), 'instructor/fonts'),
    # 页面 favicon（浏览器 `--app=` 窗口的任务栏/标题栏图标就是它）
    (os.path.join(R, 'icon-instructor.png'), 'instructor'),
    (os.path.join(R, 'info.mp3'), 'instructor'),
    (os.path.join(R, 'txtAssetDump'), 'txtAssetDump'),
]
# langtool 不在（比如 macOS 上没构建过）就不放进包：hook.py 自己会退化成「不提供钩子」
_LT = os.path.join(R, 'hardcore', 'langtool', _LT_DIR, _LT_EXE)
if os.path.isfile(_LT):
    _datas.append((_LT, 'instructor'))

a = Analysis(
    [os.path.join(R, 'run_instructor.py')],
    pathex=[R],
    binaries=[],
    datas=_datas,
    hiddenimports=['tkinter', 'tkinter.font', 'tkinter.ttk'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 字体裁剪只用得到 pyftsubset，运行时装根本用不上
        'fontTools',
        # 常规瘦身
        'lxml', 'brotli', 'PIL', 'numpy', 'scipy', 'pandas', 'matplotlib',
        'IPython', 'pytest', 'setuptools', 'pip', 'pkg_resources',
        # 补丁器 / 存档工具那条线的东西一律不进这个包
        'patcher', 'lz4', 'arabic_reshaper', 'hardcore', 'gui', 'uabea',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ObraDinnInstructor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    # exe 的图标（资源管理器/任务栏）。源图是仓库根的 icon-instructor.png，
    # .ico 由它转出来（多尺寸 16~256，供小图标/大图标两用）。
    # macOS 下 EXE 只是 .app 里的可执行文件，图标由下面的 BUNDLE 统一给 .icns。
    icon=None if _MAC else os.path.join(R, 'icon-instructor.ico'),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ObraDinnInstructor',
)

if _MAC:
    # macOS 的 .app。图标必须是 .icns（由 icon-instructor.png 用 sips/iconutil 转）；
    # CFBundleDisplayName 用中文，Dock/启动台里显示的就是它。
    app = BUNDLE(
        coll,
        name='ObraDinnInstructor.app',
        icon=os.path.join(R, 'icon-instructor.icns'),
        bundle_identifier='com.obradinn.instructor',
        info_plist={
            'CFBundleName': 'ObraDinnInstructor',
            'CFBundleDisplayName': '奥伯拉丁的回归 · 辅助提示',
            'CFBundleShortVersionString': '1.0.0',
            'CFBundleVersion': '1.0.0',
            'LSMinimumSystemVersion': '11.0',
            'NSHighResolutionCapable': True,
            'NSRequiresAquaSystemAppearance': False,
        },
    )
