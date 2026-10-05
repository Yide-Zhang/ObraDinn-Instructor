# 奥伯拉丁的回归 · 辅助提示

一个边玩边看的小助手，给《Return of the Obra Dinn》用。

它只显示**你已经解锁过**的那些提示 —— 不会提前告诉你后面有什么。

![界面](docs/screenshot.png)

---

## 它做什么

- 在后台盯着你的游戏存档（**只读**，绝不改存档）
- 一有新解锁，屏幕右下角弹一条小条，响一声提示音
- 同时在提示页里把新解锁的块标上「新」
- 提示页是**本机**的服务（`127.0.0.1`），不联网、不上传任何数据
- 页面上所有文字都不能被选中（防止手滑复制，也方便截图）

提示页的样子：左边是折叠的块，点标题展开；带「新」的是这次新解锁的。

---

## 下载

| 平台 | 文件 |
|---|---|
| Windows 10/11（64 位） | `ObraDinnInstructor-1.0.0-windows-x64.zip` |
| macOS 11+（Intel） | `ObraDinnInstructor-1.0.0-macos-x86_64.zip` |

在仓库右侧的 **Releases** 页面下载，解压后：

- **Windows**：整个文件夹解压出来，双击 `ObraDinnInstructor.exe`
  （`_internal` 文件夹要跟 exe 放在一起，别只拖 exe）
- **macOS**：把 `ObraDinnInstructor.app` 拖进「应用程序」文件夹，再双击

### 系统要求

| | |
|---|---|
| Windows | 10 / 11（64 位） |
| macOS | 11 或更高；这是 x86_64 版，Apple Silicon 上通过 Rosetta 2 运行 |
| 浏览器 | 建议装 Edge 或 Chrome（用来开无地址栏窗口；没有就退回默认浏览器，就是个普通标签页） |

### 第一次打开被系统拦下？

- **Windows**：出现蓝色的「Windows 已保护你的电脑」→ 点「更多信息」→「仍要运行」
  （没买代码签名证书，属正常）
- **macOS**：在 Finder 里**右键**点它 →「打开」→ 弹窗里再点一次「打开」

---

## 怎么用

双击打开后：

1. 它会起一个本地页面（默认 `http://127.0.0.1:8730/`）
2. 用 Edge / Chrome 的「应用模式」开一个没有地址栏的窗口
3. 屏幕右下角准备着悬浮小条

- **关掉那个页面窗口 = 退出整个程序**
- 悬浮小条 10 秒后自动收起，点它可以马上打开提示页
- 小条上**右键**可以立刻收起

### 提示页上的操作

| 操作 | 效果 |
|---|---|
| 点一条的标题 | 展开 / 折叠这一块 |
| 点「救救我！」左边那个 **＋** | 再揭开一层「救救我！(X)」（逐层给，不想看就别点） |
| 右上角「操纵器」 | 键鼠 / 手柄 —— 决定提示里按键怎么写 |

展开一个新块 = 确认看过它了，之后它就不再带「新」。

---

## 它怎么知道有新解锁：两种方式

**1. 看存档（默认，不需要任何改动）**

程序每 2 秒看一眼存档文件，发现变了就刷新。
缺点是游戏只在「离开回忆时」等时机写存档，所以提示会稍微晚一点。

**2. 书页钩子（可选，推荐）**

给游戏的 `Assembly-CSharp.dll` 打一个小补丁，让它在「书页浮现 / 全章盖戳 / 暴风雨演出结束」
这**三个时刻立刻写一次存档**，于是提示能当场弹出来。

三个站点：

```
书页浮现        Book/<RevealNewPages>c__AnonStorey0::<>m__1()
全章盖戳        Book/<RevealCompleteChapter>c__AnonStorey2::<>m__0()
暴风雨演出结束   ShipEnder::<Start>m__7()
```

装它之前**先退出游戏**：

```bash
# Windows（在程序目录里）
ObraDinnInstructor.exe hook            # 安装（会自动备份原 DLL）
ObraDinnInstructor.exe hook --report   # 看状态
ObraDinnInstructor.exe hook --restore  # 还原

# macOS
/Applications/ObraDinnInstructor.app/Contents/MacOS/ObraDinnInstructor hook
```

- 原 DLL 备份在状态目录的 `hook-backup/` 里，随时能还原
- **游戏更新过要重装一次**（更新会把 DLL 换回去）
- 不装也完全可以用，只是提示晚一点

---

## 常见问题

**Q：没有声音？**
Windows 用系统 `winsound` / `afplay`（macOS）播放 `info.mp3`。虚拟机里可能报
`AudioQueueStart failed`，程序照常工作，只是不响。可以用 `--sound 路径` 换一个音频文件。

**Q：提示太早 / 太晚？**
- 太晚 ⇒ 去装书页钩子（上面第 2 种方式）
- 太早 ⇒ 那是钩子打在旧位置了，`hook --restore` 之后重装

**Q：它会不会剧透？**
不会。页面只显示**你已经解锁**的提示；没解锁的内容根本不会发给页面
（页面只拿到已解锁的那部分数据）。

**Q：杀毒软件报警？**
因为没买签名证书，有些杀软会对「PyInstaller 打包的 exe」报警。
不认识它就别运行；想自己确认，可以直接看源码或照下面自己构建。

**Q：怎么换档位 / 换端口？**

```bash
ObraDinnInstructor.exe --slot P2 --port 8800 --interval 1
ObraDinnInstructor.exe --no-bar        # 不要悬浮小条
ObraDinnInstructor.exe --tab           # 用普通标签页打开
ObraDinnInstructor.exe check           # 命令行看当前满足哪些提示
```

**Q：数据都在哪？**

| | Windows | macOS |
|---|---|---|
| 游戏存档 | `%USERPROFILE%\AppData\LocalLow\3909\ObraDinn\` | `~/Library/Application Support/co.3909.ObraDinn/` |
| 程序状态 | `%LOCALAPPDATA%\ObraDinnInstructor\` | `~/Library/Application Support/ObraDinnInstructor/` |
| 日志 | 同上目录里的 `ObraDinnInstructor.log` | 同上 |

出问题先看日志。想重置（忘了自己看过什么）就删掉 `state.json`。

---

## 自己构建

需要 **Python 3.12** 和 PyInstaller：

```bash
pip install pyinstaller
python -m PyInstaller --noconfirm ObraDinnInstructor.spec
```

- Windows：`powershell -ExecutionPolicy Bypass -File packaging\build-windows.ps1`
- macOS：`bash packaging/build-macos.sh`（脚本里含 `.icns` 生成、`.app` 打包与 ad-hoc 重签名）

「书页钩子」用的 `langtool` 是 .NET 8 写的，可以在 Windows 上交叉发布：

```powershell
dotnet publish hardcore/langtool/LangTool.csproj -c Release -r win-x64 `
  --self-contained true -p:PublishSingleFile=true -p:PublishTrimmed=true `
  -p:TrimMode=partial -p:EnableCompressionInSingleFile=true -o hardcore/langtool/pub-trim

# macOS（Intel）：把 -r win-x64 换成 -r osx-x64，输出到 pub-osx-x64
```

---

## 目录说明

```
run_instructor.py         入口（打包后的 exe / .app 里跑的就是它）
instructor/               程序本体：页面、判据、监视、通知、钩子
  descriptions.txt        全部提示文案（**含剧透**，就是程序显示的那些内容）
  fonts/                  裁好的字体子集（思源宋体 / IM Fell / Caveat / 851）
parse_assets.py           从 txtAssetDump 读游戏数据
make_envelope_save.py     存档加解密（只读用得到）
tea_decrypt.py            XXTEA 实现
txtAssetDump/             从游戏资源里导出的数据表
hardcore/langtool/        给「书页钩子」用的小工具（Mono.Cecil 改 DLL），含源码与预编译
docs/                     截图
packaging/                打包脚本
```

---

## 致谢与版权

- 字体：**思源宋体**（Source Han Serif，SIL OFL 1.1）、**IM FELL English**、
  **Caveat**、**851 手書き** —— 均只做了子集裁剪，未改动字形
- 《Return of the Obra Dinn》(c) Lucas Pope / 3909 LLC。
  本工具与作者无关；`txtAssetDump/` 与 `descriptions.txt` 里含有游戏数据的摘录，
  仅为让工具正常工作
- 本工具**只读**游戏存档；「书页钩子」会改写游戏 DLL，但会先备份、随时可还原

## 许可

仅供个人游玩使用。仓库内的游戏相关数据版权归原作者所有；
如权利人提出异议，会立即移除相关内容。
