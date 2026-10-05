# instructor —— 奥伯拉丁 · 无剧透进度提示

随你在游戏里的进度，在后台检测存档里新达成的节点，弹一声提示音 + 屏幕角落一个小条，
点它打开本地提示页。**只读存档，从不写回**；页面只显示你已经解锁的内容，所以不剧透。

## 跑起来

```bash
python -m instructor run            # 正式用：页面 + 后台监视 + 提示音 + 悬浮条
python -m instructor run P2         # 指定槽位（默认自动跟随 mtime 最新的那个）
python -m instructor run --no-browser --no-bar   # 无界面（声音与页面照常）
```

常用开关：`--port 8730` `--interval 2` `--sound <info.mp3>` `--file <提示稿>` `--tab`

页面地址默认 `http://127.0.0.1:8730/`（端口被占会自动往后顺延）。
默认用 Edge/Chrome 的 `--app=` 开一个**无地址栏的窗口**（独立 profile，在数据目录的
`browser-profile/`）；加 `--tab` 就退回普通标签页。`dist/` 里打包好的 exe 就是同一套，
参数完全一致。

**怎么退出**（exe 是 `--windowed`，没有控制台，所以得有明确的退出口）：

| 方式 | 说明 |
|---|---|
| **关掉提示页窗口** | 页面向后端发 `sendBeacon("/api/bye")`，等 6 秒没有新页面接手就退出（刷新页面不会误杀） |
| **右键悬浮小条** | 直接退出（小条**没有**叉号，10 秒后自己消失；左键是打开提示页） |
| `Ctrl+C` | 只有在有控制台时才有 |

想「只要通知、不开页面」，用 `--no-browser` —— 那种模式下关页面退出这条不生效。

日志（exe 和 `python -m instructor` **两条路都会写**）：

```powershell
Get-Content "$env:LOCALAPPDATA\ObraDinnInstructor\ObraDinnInstructor.log" -Tail 20
Get-Content "$env:LOCALAPPDATA\ObraDinnInstructor\ObraDinnInstructor.log" -Wait -Tail 1
```

每一行都带 `[HH:MM:SS]`。判延迟就看这两行（正常都该 ≤ 2 秒）：

```
[02:33:53] [P2] 存档变化（档案写入于 1.6s 前）→ 新解锁 n001
[02:33:53] [通知] 解锁了新的辅助提示！ 便捷操作／追溯尸体    ← 存档写入后 1.6s
[02:33:53] [通知] 小条位置 (1489,730) 大小 194x166 屏幕 1707x960   ← 每个进程只打一次
[02:33:53] [通知] 小条已显示｜响铃 OK｜入队后 0.32s
```

### 那个小条长什么样

```
┌─────────────────────────┐   ← 1px 描边（满强度浅色，跟页面上「新」块一样）
│ 解锁了新的辅助提示！          │   ← 思源宋体 Heavy 12pt
│ - 便捷操作                │   ← 思源宋体 SemiBold 11pt
│ - 追溯尸体                │     一个块一行，最多 6 行，多了写「…还有 N 块」
│ - 填写下落                │
└─────────────────────────┘
```

* **配色 = 游戏那对颜色**：底 `#333319`、字 `#E5FFFF`（就是页面 CSS 里的 `--bg`/`--fg`）。
* **字体和主程序同步**：随包的字体子集没装进系统，所以启动时用
  `AddFontResourceExW(..., FR_PRIVATE)`（Windows）/ `CTFontManagerRegisterFontsForURL(Process)`
  （macOS）**私有注册进本进程**，Tk 就能用上 `Source Han Serif SC SemiBold / Heavy`。
  注册失败就退到系统宋体，不影响功能。
* **没有叉号**：左键 = 打开提示页，右键 = 退出程序，**10 秒**后自己消失（`BAR_AUTO_HIDE`）。
* 一行一块：正文里的 `- ` 开头就是一行（`on_new` 按节点下的**小节**展开）。

## 提醒什么时候弹（落盘钩子）

**默认情况**：提醒会比你想要的时间晚一点，甚至有的事**永远不会弹**。

原因在游戏源码里 —— 它一共只在 5 个时机写存档（`File.WriteAllText` 全工程只有
`SaveData.Save` 一处，调用它的只有 `Game.SaveActive`）：

| 时机 | 代码位置 | 说明 |
|---|---|---|
| 回忆刚开始 | `MomentLogic.cs:299`（`Music` 状态 ENTER） | 所以“存档变了但没解锁”是正常的 |
| **走出回忆门之后** | `MomentLogic.cs:656`（`ReturnToExploring`） | **新书页的证据只在这里落到磁盘上** |
| 幽灵显形结束 | `GhostReveal.cs:173` | |
| 按 Esc 开暂停菜单 / 窗口失焦 | `Game.cs:170` / `422` | 所以 alt-tab 会把内存里的状态顺便存下来 |
| 办公室 / 结案 / 填对下落 | `OfficeLogic.cs:145,282,420`、`Tally.cs:91`、`FateEditor.cs:715,718` | |

而玩家看到书页的那一下（A）发生在 `Book.RevealNewPages` 里：

```
Music 状态（此时存了一次档）→ 音乐剩 7s 时 PrepRevealingBookPages（黑 7 秒）
  → RevealingBookPages ENTER: AddVisitCountToSaveData(); RevealNewBookPages()
     └─ Book.cs:1205  momentData.revealedPageInBook = true;   ← A：只改内存
  → InBookAfterReveal（等你合上书）→ OpeningExitPortal（t=1s 时门开 = B）
  → ExitMomentDoor（1s）→ ReturnToExploring: Game.SaveActive()   ← 只有这里才写盘
```

**A 到 B 之间一个写盘点都没有**，所以轮询存档最多只能等到 B —— 你在书里读多久，
提醒就晚多久（实测有一段 110 秒的窗口）。

### 三个钩子站点

| # | 位置 | 改的是什么 | 不补会怎样 |
|---|---|---|---|
| 1 | `Book.RevealNewPages` 末尾那个 `StartFlash()` 回调 | `moment.revealedPageInBook = true` | 提醒等到你走出回忆门（上例的 110 秒） |
| 2 | `Book.RevealCompleteChapter` 同理 | `disaster.revealedDisappearancesInBook`（失踪页） | 同理 |
| 3 | `ShipEnder` 里 `notifyDialogInfo.Show(...)` 那个回调 —— 暴风雨演出（2s 雷声+雨、4s 环境音）走完、船尾船夫提示条弹出、随即 `Go(ZoneDone)` | `general.era` 0 → 1（暴风雨开始）落盘 | **可能整轮都看不到 era=1**：`era = 1` 那句（`ShipEnder.cs:30`）只改内存，上船时 `era=2`，随后 Tally 里直接写 `era=3`，文件里 0 直接跳 3 |

第 3 条的证据是真实的：拿 270 份真实快照回放提示稿，有的周目里 `[era=1时]`（n009）
**从未触发** ⇒ 它后面的 `gate_all_previous` 节点（「救救我！」整条链）被永远堵死
（那次回放停在 10/12）。

**站点 3 为什么不插在 `era = 1` 那句赋值上**：那一帧屏幕正黑着、雷声刚要响，
提醒会直接撞进演出里；而演出结束那一帧 `era` 早就已经是 1，写下去的存档照样带 `era=1`。
另外它只会在**每次暴风雨里触发一次**（`ZonePullerCallout` → `ZoneDone` 这条路只走一遭，
之后的 `Start()` 因为 `era != 0` 直接进 `ZoneDone`，那个回调不会再跑）；
如果挂在 `ZoneDone` 的 ENTER 上，则「看船夫又移开视线」这类重入也会跟着写盘。

⇒ 但 `era` 本身**也不是个好判据**：`ShipEnder.cs:28-31` 是**先**把 `era` 置 1、
**再**判断要不要先跑全章盖章动画，而盖章那一帧站点 2 的钩子就会写盘 ⇒ 磁盘上真实存在
「era 已经是 1、暴风雨演出还没播」的存档（273 份实测快照里有 4 份），
`[era>=1时]` 会在**盖章动画**那一刻就弹，比演出播完早几十秒到几分钟。

⇒ 所以「暴风雨」这条改用 `[暴风雨演出播完]`（facts 里的 `stormEnded`）：
船尾船夫提示条 `notifyDialogInfo.Show(...)`（`ShipEnder.cs:78`）→ `Dialog.Play`
→ `Dialog.cs:96` `IncStat("#dia-ship-end-notify")` —— 这条提示条**只在 era==0 起风暴那一次**播
（`era != 0` 时 `Start()` 直接进 `ZoneDone`，那个回调不会再跑），所以它就是「演出播完、可以下船」。
站点 3 的钩子正好插在这句之后 ⇒ 装钩子时那一帧落盘、提醒随即弹；没装钩子也会在下一次
自然写盘时带上它。

（`era` 触发形式保留着，但只适合写「阶段」而不是「时刻」；真要写也要用 `>=`：
`[通关至少1次后]` 用的 `era>=2` 就是这种写法 —— 实测 `era=2` 从不落盘，全靠 `>=` 才不会漏。）

### 装钩子

```bash
python -m instructor hook --game "F:\...\steamapps\common\ObraDinn"   # 填一次就会记住
python -m instructor hook --report        # 只看状态（装没装 / 认不认得出来）
python -m instructor hook --restore       # 从备份还原 DLL
```

它做的是在三个站点各插一句 `Game.SaveActive(...)`（共 6 字节/处）。判据是语义的：
先找宿主方法，再从它 `ldftn` 出来的回调里找**恰好一个**含指定锚点的 ——
站点 1/2 的锚点是 `call Book::StartFlash()`，站点 3 是 `notifyDialogInfo` 字段之后的那次 `Show(...)`。
不认偏移也不认编译器生成的名字；认不出来就**拒绝改**。
锚点还必须**不被插入改变**（否则复验时认不回同一个锚点）—— 站点 3 因此用 `Show` 那条 callvirt，
而不是笼统的「`ret` 前一条」。

⚠ **换站点要「先还原再装」**：旧 DLL 里那句旧位置的 `SaveActive` 不会被新版本认出来，
直接重跑 `hook` 会在新锚点再插一句 —— 两句都在，而旧的那句先执行，提醒时间不变。
正确做法：`hook --restore` 还原官方 DLL → 再 `hook` 一次。

实际改写交给 `langtool`（Mono.Cecil），它随包一起发；`instructor` 只负责
找游戏 → 找 langtool → 备份 → 改写 → 复验 → 原子替换。
升级到新站点只要重跑一次 `hook`—— 它会只补缺的那些。

安全性（都实测过）：

* 装之前先把 DLL 备份到 `%LOCALAPPDATA%\ObraDinnInstructor\hook-backup\`（`--restore` 就用它）。
* 改完先用 `langtool ... --check` 复验（3/3），**通过才替换**；不通过产物直接丢掉，游戏 DLL 不动。
* 用全量 IL 摘要比对（`genrecipes digest`）验过：整份 DLL 里**只有那三个回调变了**，
  每个 +6 字节，其余方法逐指令相同。
* 与难度补丁**互不影响**：先打钩子再换档、先换档再打钩子，结果逐指令一致；
  难度档位也能被 `patcher.core.probe_dll` 正常认出。
* ⚠ 但难度补丁器的“**还原原版**”会用原始 DLL 覆盖 ⇒ 钩子会被抹掉，需要重装一次。
* ⚠ 游戏在运行时 DLL 是锁着的，装之前先关掉游戏。

### 审计：还有哪些地方**不需要**额外钩子

把提示稿用到的每个事实都回溯到游戏源码查过一遍，剩下的都不缺：

| 事实 | 内存里被谁改 | 落盘 |
|---|---|---|
| `moment.*.pageRevealed` / `pagesRevealed` | `Book.RevealNewPages` | 钩子 1 ✓ |
| `disaster.*.disappearances` | `Book.RevealCompleteChapter` | 钩子 2 ✓ |
| `chapter.*.allVisited`（`visitCount > 0`） | `AddVisitCountToSaveData()` | 首次到访就在钩子 1 那一帧 ✓；重复到访不会改变 `>0` |
| `anyChapterStamped`（“盖过章了”） | `Book.RevealCompleteChapter` 里的 ×/／ 计数 | 钩子 2 ✓ |
| `disaster.*.chart`（“该章解锁”） | `Book.RevealNewPages` 里 `revealedChartInBook = true`（Book.cs:1229） | 钩子 1 ✓ |
| `moment.*.unlocked`（拉尸体） | `MomentLogic.cs:463`，3 秒后 | 同一条路径紧接着就是 `ReturnToExploring` 的存档，或新一刻的 `Music` ENTER 存档 ⇒ 几秒内 ✓ |
| `moment.*.ghosts` | `GhostReveal` 结束 | 它自己就调 `SaveActive` ✓ |
| `face.*.markedCorrect` / `nameId` / `fateId`（→ `fates.*`、`zone.*`） | `FateEditor` | 它自己就调 `SaveActive(EditFate/CorrectFates)` ✓ |
| `stat.zone-complete-office` | `UpdateZoneCompletion` ← 填对下落 | 同上 ✓ |
| `moment.*.visitCount >= 2` | `AddVisitCountToSaveData()`（重复到访那次） | 紧挨着 `ReturnToExploring` 的存档 ⇒ ✓（反正也得走出门才算一次到访） |
| `general.era == 2` | `ShipEnder` `ZoneDoneWaitingToLeave` | **不落盘**（随后 Tally 直接写 3）⇒ 所以判据必须写 `>=2`（现有的 `[通关至少1次后]` 已经是） |
| `stat.#dia-ship-end-notify`（船尾船夫提示条） | `ShipEnder` `AT_STEP(8f)` → `Dialog.Play`（`Dialog.cs:96`） | 钩子 3 ✓（没装钩子就等下一次自然写盘） |
| `face.*.clueWarning`、`stat.#dia-*`、`general.bookPageId`、`helped.*`、`inventory.*` | 各处 | 目前没有任何触发器用到；真要用再说 |

### 能不能不要它

能。不装钩子一切照常，只是提醒要等你走出回忆门之后才弹（且 `era=1` 可能彻底看不到）；
`run` 启动时会打一行状态告诉你现在是哪种。

## 打包成 exe

```bash
python -m PyInstaller --noconfirm ObraDinnInstructor.spec
# -> dist/ObraDinnInstructor/ObraDinnInstructor.exe（约 44 MB / 1000 个文件）
```

- 入口是仓库根的 `run_instructor.py`，它把命令固定成 `run` 再转发给
  `instructor/__main__.py`（**参数只有那一套**）。之所以要这个文件：
  `--windowed` 打包后 Windows 上 `sys.stdout/stderr` 是 `None`，
  所以它把输出写进日志（数据目录下 `ObraDinnInstructor.log`，超过 256 KB 自动轮转），
  致命错误再弹一个 MessageBox 告诉用户日志在哪。
- **不带源字体**（851 有 80 MB），所以 exe 里不能重裁字体 ——
  `page.ensure_fonts()` 先问 `fonts.sources_present()`，没有源就直接用现成的子集。
- **不带 `patcher`**：`facts.saves_dir()` 里那条 `from patcher import core` 在 try 里，
  拿不到就回落到硬编码的 `%USERPROFILE%\AppData\LocalLow\3909\ObraDinn`。
- `txtAssetDump` 必须打进去：`parse_assets.load_assets()` 按 `Path(__file__).parent` 找它。
- **图标**：`icon-instructor.ico`（由仓库根的 `icon-instructor.png` 转出来，多尺寸 16~256）
  当 exe 图标；那张 png 同时打进包里，给页面当 favicon（见下）。
- 用的还是用户的**真实**数据目录，所以 exe 和 `python -m instructor` 共享同一份
  `state.json` / 浏览器 profile —— 不算两份进度。

## 写提示稿（`instructor/descriptions.txt`）

这是唯一的数据源，**格式就是人写的那种**，不用改成 JSON：

```
<触发器>[:]                 ← 顶级行；也接受 [方括号] 包起来
    - 小节标题
        -- 要点
            --- 子要点
---- 分组条件 ----          ← 分隔线**本身就是这一组的触发器**
    - 小节标题
        -- 要点
```

支持的触发器：

| 你写 | 含义 | 判据（存档字段） |
|---|---|---|
| `[d090解锁]` | 该章的**图表页在书里出现**（= 该章解锁） | `disaster.<d>.revealedChartInBook` |
| `[d060的第6页解锁完毕]` | 该章第 N 页出现 | `moment.<该章第N个时刻>.pageRevealed` |
| `[任意一章全章解锁完后盖戳]` | 该章**已经盖过章**（全章揭示动画跑完） | `anyChapterStamped` = `disaster.<d>.disappearances` |
| `[任意一章全章解锁完]` | 只是所有时刻都到过（还没盖章） | `chapter.<d>.allVisited` |
| `[d030,d060,d080任意一个解锁了失踪部分]` | 任一章弹出「失踪」页 | `disaster.<d>.disappearances` |
| `[有人的面孔unblur]` | **事件**：有人面孔由模糊变清晰 | `facesUnblurred` > **地板** |
| `[有人的面孔unblur且可填写下落]` | 有人既清晰又可填下落 | `facesWorkable` > 地板 |
| `[玩家解锁的页面数>=15]` | 书里已出现的页数 | `pagesRevealed` |
| `[era=1时]` / `[era>=1时]` | 游戏阶段 | `general.era`（⚠ 只适合写「阶段」，精确时刻用下一行的） |
| `[暴风雨演出播完]` | 过场演出走完、船尾船夫提示条弹出（可以下船了） | `stormEnded` = `stat.#dia-ship-end-notify` |
| `[通关至少1次后]` | 通关 | 见下方「通关」说明 |
| `[一开始就有]` | 始终解锁 | — |
| `[以上全部解锁后]` | 前面全部解锁过（粘性） | — |

分隔线分组：`---- 以上都解锁完后… ----`、`---- 防呆（一开始就有） ----`、`---- 通关至少1次后 ----`

**逐层链**：一组的多个小节里，只要正文写了 `试试“救救我！(2)”` 这种引用，
页面就把它们当成一条链：一开始**只出一块只有标题的「救救我！」**（它自己没有内容），
点它一下就在它底下添出一块**独立的**「救救我！(1)」，再点一下添出「救救我！(2)」……
新添的紧贴标题下方，所以越往下越旧；每一层都是普通块，可以自己折起来。
十层都出来之后**标题块整个消失**（只剩那十块）。展开层数记在浏览器 localStorage，跟游戏进度无关。

**「通关」为什么不是 `officeEndedOnce`**：那个字段只在胜利音乐播完那一刻置位，
`SaveData.Rewind()`（`SaveData.cs:99`）随即把它清成 false，实测 67 份快照里全是 false。
所以改用游戏自己判断「可以倒回」的条件 —— `CanRewind()`（`SaveData.cs:88`）= `era>=2`，
这也正好是存档界面出现「倒回」按钮的时机。

## 页面长什么样

- **窗口名与图标**：页面 `<title>` 是《奥伯拉丁的回归》辅助程序 —— 浏览器 `--app=` 开出来的
  那个窗口（= 程序窗口）的名字就是它；窗口/任务栏图标是 favicon
  `icon-instructor.png`（exe 用同图转的 `.ico`）。
- **左上角那行字是「已解锁的提示」**，并且整条页头 `user-select:none`：标题不该被选中。
- **配色**：深色 `#333319` + 浅色 `#E5FFFF` 两色；中间灰阶全部由浅色降透明度得来。
- **整体随窗口缩放**：`head` 里一段小脚本按**窗口宽度**算出 `--s` 写到 `documentElement`
  （`resize` 时重算），`body{zoom:var(--s)}` —— 字体、内边距、描边、栏宽**全都按它算**。
  **正比于窗口宽、与高度无关**：参考点 1200px 宽 → 正文 18px，夹在 14~32px。
  实测：900→14px、1200→18px、1568→23.5px、1920→28.8px、≥2500→32px（封顶）。
  两个旋钮在 `page.py` 的 `PAGE` 头部：`REF_FONT` 改整体大小、`REF_W` 改「涨得多快」。
- **不显示滚动条**：`scrollbar-width:none` + `::-webkit-scrollbar{display:none}`，
  但**滚轮/触摸照样能滚**（`zoom` 只缩不放剪）。
- **整站无圆角**（`*{border-radius:0}`），块与块靠 1px 描边分开。
- **页脚只有一句**「正在追踪：第 X 个档位」（X 由 payload 里的 `slot` 算出来，
  `P1/P2/P3` → `1/2/3`；还没定位到存档就一个破折号）—— 这是页上唯一一处存档相关的字。
- **除了页脚那一句，不显示任何存档内容**（已解锁计数 / 书页 / 已登记 / era 一律不显示），
  也**不显示任何代码块**（提示稿里的反引号只去壳，不做高亮）。
- **hover 不弹任何东西**：全页一个 `title` 都没有。
- **一个一级元素（`- 小节`）= 一块**，不再按解锁时机把好几节塞进同一张卡。
- **块的顺序 = 整个提示稿从后往前读**：大类倒序（倒回 → 推理 → 探索 → 防呆），
  同类内按解锁时刻倒序，同一时刻按提示稿原序倒序，同一个节点的节内也倒序。
  于是最近得到的永远在最前。类的划法：`always` 分隔线 = 防呆，逐层链 = 推理，
  `通关` = 倒回，其余 = 探索（`render.category`）；排序见 `render.blocks`。
- **「新」标记**：解锁时刻晚于「我上次确认过的那一刻」的块，标记会**默认折起**，
  标题旁有一条反色的「新」，块描边也会变亮。**点开（展开）就算确认**，「新」随即消失；
  再折回去也不会重标。确认记录存在 localStorage 的 `obd.instr.ack`
  （`块键 -> 确认时的解锁时刻`，不是布尔，这样同一块在新周目里重新解锁时会重新变新）。
  回填的块时刻为 0，永远不标「新」。
- **两种块永远静默**（`hints.Node.silent`）：`一开始就有`（`always`）和**逐层链**
  （提示稿里写着"玩家可以自行点选查看的内容"）。它们**不响铃、不弹浮条**，
  解锁时刻记 **0** ⇒ 所以也不标「新」、排在同类的最后。理由是它们不是"游戏里刚发生的事"，
  弹出来只会打断游戏；解锁后照常出现在页面上，想看自然会去看。
  另外**首次挂上时的回填一律静默**（一个都不提醒）—— 刚装上工具就开始响铃很突兀。
- **块可以折叠**：点块标题栏 toggle（开头是 ▼ / ▶），状态记在 localStorage，默认全展开，
  唯一的例外是「新」块（见上）。逐层链的标题块**不是**折叠开关 —— 点它是「再添一层」（见上）。
- **键位直接填进正文**（`gamedata.chip_text`）：`[Zoom]` → `E（按住） / 右键（按住）`，
  `[OpenBook]` → `Tab`，`[Action]` → `空格 / 回车 / 左键`，`[Left Click]` → `左键`，
  `[点击/按下]` → `点击/按下`；切到手柄就依次变成 `LB · LT · R3（按住）` / `Y / △` /
  `A / ✕ · RB · RT · X / □` / `A / ✕`（手柄没有「左键」，就是 Action）/ `按下`。
  **不做任何特殊样式**，就是不包边、不换等宽字体的普通正文（只留一个裸 `<span>` 供 JS 换词）；
  `DEVICE_CHIP` 里的值可以写成另一个动作名，就会取那个动作的键位。
- **「新」块默认折起**；点开它（展开）才算确认，「新」随之消失。折回去不会把标记再叫回来。
- **右上角可以选操纵器**（键鼠 / 手柄）。浮层在两种情况下会自己弹出来：
  玩家点入口，或者**本地还没选过**（`obd.instr.device` 缺失）。
- **逐层链是「标题块 + 一层一块」**：初始只有一个「救救我！」标题块（无内容），
  点它添一块独立的「救救我！(X)」；新添的紧贴标题下面（越往下越旧），每层各带自己的标题栏、
  可单独折起；全揭完之后标题块**消失**。展开层数记在浏览器 localStorage，跟游戏进度无关。
- 解锁时刻记在 state 的 `unlocked{nid: unix秒}`；首次挂上时的**回填**记 0。
- **`increase` 类用「地板」当基线**（`facts.increase_floor()`），**不是**挂上那一刻的快照。
  地板 = 全新存档时的值，由游戏数据算出：`facesFillable`/`facesWorkable` = 0
  （要 `HaveVisitedClimax`，开局一个都没有）、`facesUnblurred` = 2
  （`sea9`/`pass5` 的 clue 就是 `-`，开局就不模糊）。
  于是 `fact > 地板` = 「玩家自己造成过至少一次这种变化」，与什么时候挂上无关。

## 其余命令（写触发器时很有用）

```bash
python -m instructor lint                  # 挑毛病：触发器、链断、** 没配平、链接缺 https
python -m instructor hints                 # 列出解析出来的节点与逐层链
python -m instructor facts P2              # 打印当前全部 facts
python -m instructor check P2              # 当前哪些节点已满足
python -m instructor runs P2               # 列出 Backup/ 里的所有周目
python -m instructor replay P2 --run 0     # 拿真实快照回放，报每个节点首次触发时刻
python -m instructor curve P2 --fact pagesRevealed,facesWorkable   # 某量随进度怎么涨
python -m instructor notify "文字"         # 单独试提示音 + 悬浮条
python -m instructor fonts --report       # 看字体子集状态
python -m instructor fonts --force        # 强制重裁字体子集
python -m instructor hook --report        # 看「存档钩子」装没装
python -m instructor hook --game <目录>    # 装钩子（让提醒在书页浮现那一刻弹）
python -m instructor state                # 看每个槽位已解锁了哪些节点、什么时候解锁的
python -m instructor state P2 --forget n002   # 把 n002 改回未解锁（测触发时机用）
python -m instructor page --unlock-all --out preview   # 生成静态预览页（会连带拷 fonts/）
```

## 字体

页面字体与「难度补丁」项目同源，再加三档：

| 用途 | 字体 | 变量 |
|---|---|---|
| 正文（拉丁） | IM FELL English Roman | `--font` 开头 |
| 正文（中文） | 思源宋体 SC SemiBold | `--font` 次位 |
| 粗体 `**…**` | 思源宋体 SC **Heavy** | `--font-bold` |
| 斜体 `*…*`（拉丁） | **Caveat** | `--font-hand` 首位 |
| 斜体 `*…*`（中文） | 851 手写体 | `--font-hand` 次位 |
| 键帽 / 代码 | 等宽（故意不一样） | `.chip` |

- 字体源文件放在仓库根（`font_src/` 或根目录），子集输出到 `instructor/fonts/`，
  由 `python -m instructor fonts` 生成；`page` / `run` 启动时会**自动重建过期子集**。

  | 用途 | 源文件 |
  |---|---|
  | 正文·拉丁 | `font_src/IMFeENrm28P.ttf` |
  | 正文·中文 | `font_src/SOURCEHANSERIFSC-SEMIBOLD.OTF`（**完整**那份，23.6 MB → 子集 2.5 MB） |
  | 粗体 | `SOURCEHANSERIFSC-HEAVY.OTF`（仓库根） |
  | 斜体·中文 | `851tegakizatsu.otf`（仓库根） |
  | 斜体·拉丁 | `CAVEAT-REGULAR-U.TTF`（仓库根） |

  ⚠ 中文那支的基准必须是 `font_src/SOURCEHANSERIFSC-SEMIBOLD.OTF` 这份**完整的**：
  以前写成 `font_src/SourceHanSerifSC-SemiBold-subset.otf`（别的项目早先裁过的中间产物），
  它缺 17 个上屏字符 —— 包括折叠三角 `▼▶`、`◇ △ □ ⇒ – ／ ｜` —— 那些字以前是回落
  系统宋体渲染的。换成完整源之后只缺 5 个（`⛓ ✔ ✕ ✘ 🔇`，都是 CLI 输出用的，
  终端自己有回落）。
- 字体是**按需裁剪**的：字符集 = 符号区间 + `instructor/*.py` 里的字符串字面量
  + 整份 `descriptions.txt` + GB2312 一级字库。改了提示稿/代码会自动包含新字。
- ⚠️ **斜体栈里 Caveat 必须排在 851 前面**——851 自带完整 ASCII（95/95），
  排在前面会把英文斜体也抢走。已验证：`Caveat,Hand851` 渲染 `Abcg` 与
  `Caveat` 单独完全同宽（65.72），而汉字与 `Hand851` 单独完全同墨（153×72）。
- 静态导出（`--out`）会把字体拷到输出旁的 `fonts/`，`@font-face` 用相对路径，
  所以 `file://` 双击直接看也不会缺字。
- ⚠ **`@font-face` 的 URL 挂着子集文件的 mtime**（`page.font_query()`，
  形如 `...SemiBold-subset.otf?v=1791198500`）：子集文件名不变，若 URL 也不变，
  浏览器（HTTP 那条给了 `max-age=86400`，`file://` 那条也有磁盘缓存）会一直用**旧子集**，
  看起来就是「字体明明重裁了，字形却没变」。重放字体后 URL 自己就变了，不靠手动清缓存。

## 几个必须知道的坑（都踩过）

- **采样必须盯主存档文件**，不能只靠 `Backup/`：`-Recent`/`-EditFate` 会被覆盖，
  像 `era=1` 这种瞬时态在实测里**整个被错过**（所以 `era==1` 会漏，用 `era>=1`）。
- **`Backup/` 会混多个周目**（实测 P2 有 9 个）。按 `playTime` 排序会串成假时间线，
  回放结果全错。`replay`/`curve` 现在按文件 mtime 切周目，`-CopiedOver-` 直接排除。
- **解锁是粘性的**：一旦满足过就永久解锁，否则 `era=1` 这种瞬时条件会把它后面的
  「以上全部解锁后」永远堵死。
- **基线必须用「地板」而不是「挂上那一刻的快照」**。用快照的话，半路挂上一个打了很久的
  存档时 `increase` 触发器永远不成立（实测 `58 > 58` 为假），而它后面还有
  `gate_all_previous` 的节点要靠它 —— 会把整条「救救我！」链永远堵死
  （就算玩到 60/60 也没救了）。现在基线是算出来的，旧状态会在下一轮 tick 自愈
  （代价：多弹一次通知 + 那几条带一下「新」标记）。
- **首次挂上某槽位做静默回填**（已满足的节点直接标记，不弹通知），只对「一开始就有」
  那类提醒一次，否则老玩家一开就炸出十几条。
- **同槽位开新周目**（`playTime` 倒退超过 60 秒）会自动重置该槽位状态。
- **独占全屏下系统通知看不到**，所以用「声音 + 置顶小条」；声音走 Windows 自带 MCI
  （零依赖，不弹窗口）。小条每次显示都要**重新** `attributes("-topmost", True)` + `lift()` ——
  `withdraw()`/`deiconify()` 之后 topmost 会失效，不重设就会「弹了但压在游戏下面」。
- ⚠ 通知回调链（tkinter `after`）必须写在 `finally` 里重排：抛一次非 `queue.Empty`
  的异常，整条链就永远断了，之后一个通知都不会有。
- ⚠ 页面那个 3 秒轮询在**后台会被 Chrome 节流**（被游戏盖住时几乎不跑），
  所以「看一眼才刷出来」是意料之中的；但它只是参考页，真正的通知走小条 + 声音。
- ⚠ **exe 是 `--windowed`（没有控制台）**：从它里面 subprocess 拉一个 console 程序，
  Windows 会给那个程序**现开一个 cmd 窗口**再关掉 —— 启动时正是这样闪两下黑框
  （`supports_hook()` 探一次能力 + `hook_state()` 查一次状态，都拉 `langtool.exe`）。
  凡是这种拉法都要带 `creationflags=CREATE_NO_WINDOW`，`hook.no_window_kwargs()` 就是干这个的。

## 文件

```
instructor/
  gamedata.py    游戏静态数据：时刻表 / 章节号 / clue 表达式 / 区域 / 键位
  facts.py       存档 -> 扁平 facts（含全部派生量）
  hints.py       解析提示稿 + 触发器求值 + lint
  render.py      排版（markdown-lite）+ 键帽
  page.py        本地 HTTP 服务 + 页面（含字体 @font-face）
  fonts.py       字体子集裁剪（pyftsubset）
  fonts/         裁好的子集（生成物，不必进版本控制）
  state.py       每槽位持久状态（已解锁 / 基线 / 是否已挂上）
  notify.py      提示音 + 悬浮小条
  watcher.py     后台监视
  __main__.py    CLI
```

状态与日志写在 `%LOCALAPPDATA%\ObraDinnInstructor\`（macOS 是
`~/Library/Application Support/ObraDinnInstructor/`）。
提示音默认找 `instructor/info.mp3` → `instructor/sounds/info.mp3` → 仓库根 `info.mp3`。
