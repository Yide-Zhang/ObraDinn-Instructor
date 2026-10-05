# langtool

给「书页钩子」用的小工具：用 Mono.Cecil 往游戏的 `Assembly-CSharp.dll` 里，
在三个回调之后各插一句 `Game.SaveActive()`，让存档在那一刻就落盘 ——
于是提示不再等玩家走出回忆门，而是**当场**弹出来。

## 三个站点

```
书页浮现        Book/<RevealNewPages>c__AnonStorey0::<>m__1()
全章盖戳        Book/<RevealCompleteChapter>c__AnonStorey2::<>m__0()
暴风雨演出结束   ShipEnder::<Start>m__7()
```

每个站点插的都是 `ldc.i4.0` + `call Game::SaveActive`（共 6 字节，DLL 因此 +512 字节），
锚点必须是**不会被插入内容影响**的那条指令，否则重装会插两次。

## 用法

```
langtool revealhook <in.dll> <out.dll> [--deps=<Managed 目录>]   # 改写
langtool revealhook <dll> --check [--deps=<Managed 目录>]        # 只查：0=已装 1=未装 2=只装了一半
```

程序侧调用见 `instructor/hook.py`（会先备份原 DLL，改完复验通过才原子就位）。

## 发布（自包含单文件）

全是托管代码，所以**可以在 Windows 上交叉发布 macOS 版**：

```powershell
# Windows
dotnet publish LangTool.csproj -c Release -r win-x64 `
  --self-contained true -p:PublishSingleFile=true -p:PublishTrimmed=true `
  -p:TrimMode=partial -p:EnableCompressionInSingleFile=true -o pub-trim

# macOS（Intel）
dotnet publish LangTool.csproj -c Release -r osx-x64 `
  --self-contained true -p:PublishSingleFile=true -p:PublishTrimmed=true `
  -p:TrimMode=partial -p:EnableCompressionInSingleFile=true -o pub-osx-x64
```

产物路径就是 `instructor/hook.py` 会去找的位置（`pub-trim/langtool.exe` / `pub-osx-x64/langtool`）。
`classdata.tpk` 是资源相关子命令要用的表，一起带着。

⚠ 改过站点位置之后**必须重新发布**，否则 `--check` 还是会按老锚点报站点名。
