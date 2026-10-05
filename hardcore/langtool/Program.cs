using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using AssetsTools.NET;
using AssetsTools.NET.Extra;
using Mono.Cecil;
using Mono.Cecil.Cil;

namespace LangTool
{
    /// <summary>
    /// 语言包（lang-*）读写工具，引擎用 UABEA 自带的 AssetsTools.NET 3.0。
    ///
    ///     langtool list  &lt;bundle&gt;                 列出包内文件与资源
    ///     langtool dump  &lt;bundle&gt; [out.txt]       导出 LangPack 的 key/val 对照    ///     langtool api   [名字片段]                反射打印 AssetsTools.NET 的真实 API    /// </summary>
    internal static class Program
    {
        /// <summary>--pack[=lz4|lzma]：写完后重新压一遍（默认不压，写出的包会大很多）。</summary>
        private static string s_pack;

        /// <summary>--deps=&lt;目录&gt;（可多段，用 ; 分隔）：patchdll 解析依赖用的搜索目录。</summary>
        private static string s_deps;

        /// <summary>--check：revealhook 只查不改（给提示工具判断钩子在不在用）。</summary>
        private static bool s_check;

        private static int Main(string[] args)
        {
            // ★ 输出被重定向（管道/文件）时，.NET 默认按控制台的 OEM 代码页输出，
            //   非 ASCII（德语 ü、中文、阿拉伯语…）会被破坏 —— 上层脚本读到的就是乱码。
            //   所以只在重定向时切到 UTF-8；终端直连时保持原样，免得 PowerShell 显示乱码。
            if (Console.IsOutputRedirected)
            {
                Console.OutputEncoding = new System.Text.UTF8Encoding(false);
            }

            var rest = new List<string>();
            foreach (var a in args)
            {
                if (a.StartsWith("--pack", StringComparison.Ordinal))
                {
                    var eq = a.IndexOf('=');
                    s_pack = eq >= 0 ? a.Substring(eq + 1).ToLowerInvariant() : "lz4";
                }
                else if (a.StartsWith("--deps", StringComparison.Ordinal))
                {
                    var eq = a.IndexOf('=');
                    if (eq >= 0)
                    {
                        s_deps = a.Substring(eq + 1);
                    }
                }
                else if (a == "--check")
                {
                    s_check = true;
                }
                else
                {
                    rest.Add(a);
                }
            }
            args = rest.ToArray();

            if (args.Length < 2)
            {
                Usage();
                return 2;
            }

            try
            {
                switch (args[0])
                {
                    case "list":
                        return ListCommand(args[1]);
                    case "dump":
                        return DumpCommand(args[1], args.Length > 2 ? args[2] : null);
                    case "api":
                        return ApiCommand(args.Length > 1 ? args[1] : "");
                    case "set":
                        return SetCommand(args[1], args[2], args[3]);
                    case "export":
                        return ExportCommand(args[1], args[2]);
                    case "keys":
                        return KeysCommand(args[1], Shift(args, 2));
                    case "patchdll":
                        return PatchDllCommand(args);
                    case "revealhook":
                        return RevealHookCommand(args);
                    default:
                        Usage();
                        return 2;
                }
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("[X] " + ex.GetType().Name + ": " + ex.Message);
                Console.Error.WriteLine(ex.StackTrace);
                var inner = ex.InnerException;
                while (inner != null)
                {
                    Console.Error.WriteLine("  -- 内部: " + inner.GetType().Name + ": " + inner.Message);
                    Console.Error.WriteLine(inner.StackTrace);
                    inner = inner.InnerException;
                }
                return 1;
            }
        }

        private static void Usage()
        {
            Console.Error.WriteLine("用法:");
            Console.Error.WriteLine("  langtool list  <bundle>");
            Console.Error.WriteLine("  langtool dump  <bundle> [out.txt]");
            Console.Error.WriteLine("  langtool api   [名字片段]");
            Console.Error.WriteLine("  langtool set   <in> <out> <edits.txt>");
            Console.Error.WriteLine("  langtool export <in> <out.tsv>");
            Console.Error.WriteLine("  langtool keys  <in> <key> [key ...]   （输出 key<TAB>值，已转义）");
            Console.Error.WriteLine("  langtool patchdll <in.dll> <out.dll> <档位> [--deps=<Managed 目录>]");
            Console.Error.WriteLine("  langtool revealhook <in.dll> <out.dll> [--deps=<Managed 目录>]");
            Console.Error.WriteLine("     在书页揭示动画最后那个回调里插一句 SaveActive，让存档在「书页浮现」的");
            Console.Error.WriteLine("     同一帧落盘 —— 提示工具靠它把提醒从「走出回忆门之后」提前到那一刻。");
            Console.Error.WriteLine("     （另一处站点在 ShipEnder 暴风雨演出结束那一刻，让 era=1 落盘。）");
            Console.Error.WriteLine("  langtool revealhook <dll> --check   只查不改：有钩子退 0，没钩子退 1");
        }

        // ================================================================ api
        private static int ApiCommand(string filter)
        {
            var asm = typeof(AssetsManager).Assembly;
            Console.WriteLine("assembly: " + asm.FullName);

            Type[] types;
            try
            {
                types = asm.GetTypes();
            }
            catch (ReflectionTypeLoadException ex)
            {
                types = ex.Types;
            }

            foreach (var t in types)
            {
                if (t == null || !t.IsPublic)
                {
                    continue;
                }
                if (filter.Length > 0
                    && t.FullName.IndexOf(filter, StringComparison.OrdinalIgnoreCase) < 0)
                {
                    continue;
                }

                Console.WriteLine();
                Console.WriteLine("=== " + t.FullName);
                foreach (var m in t.GetMembers(BindingFlags.Public | BindingFlags.Instance
                                              | BindingFlags.Static | BindingFlags.DeclaredOnly))
                {
                    if (m is MethodInfo mi)
                    {
                        if (mi.IsSpecialName)
                        {
                            continue;
                        }
                        var ps = string.Join(", ", Array.ConvertAll(mi.GetParameters(),
                            p => p.ParameterType.Name + " " + p.Name
                                 + (p.HasDefaultValue ? " = " + (p.DefaultValue ?? "null") : "")));
                        Console.WriteLine("    " + mi.ReturnType.Name + " " + mi.Name + "(" + ps + ")");
                        continue;
                    }
                    Console.WriteLine("    " + m.MemberType + "  " + m);
                }
            }
            return 0;
        }

        /// <summary>建一个装好 classdata.tpk 的 AssetsManager（MonoBehaviour 的类型信息靠它）。</summary>
        private static AssetsManager NewManager()
        {
            var am = new AssetsManager();
            var tpk = Path.Combine(AppContext.BaseDirectory, "classdata.tpk");
            if (File.Exists(tpk))
            {
                am.LoadClassPackage(tpk);
            }
            else
            {
                Console.Error.WriteLine("[!] 找不到 classdata.tpk，MonoBehaviour 可能解析不出字段");
            }
            return am;
        }

        private static AssetsFileInstance LoadFirst(AssetsManager am, string path, out BundleFileInstance bun)
        {
            bun = am.LoadBundleFile(path, true);
            var inst = am.LoadAssetsFileFromBundle(bun, 0, true);
            if (inst == null)
            {
                throw new InvalidDataException(
                    "LoadAssetsFileFromBundle 返回 null（包内第 0 项=" + bun.file.BlockAndDirInfo.DirectoryInfos[0].Name + "）");
            }
            return inst;
        }

        // ================================================================ list
        private static int ListCommand(string path)
        {
            var am = NewManager();
            var inst = LoadFirst(am, path, out var bun);

            Console.WriteLine("包文件 : " + path);
            var hdr = bun.file.Header;
            Console.WriteLine("  头部 : sig=" + Show(hdr.Signature)
                              + "  ver=" + hdr.Version
                              + "  gen=" + Show(hdr.GenerationVersion)
                              + "  engine=" + Show(hdr.EngineVersion));
            Console.WriteLine("  Hash : " + bun.file.BlockAndDirInfo.Hash);
            var dirs = bun.file.BlockAndDirInfo.DirectoryInfos;
            Console.WriteLine("包内条目 " + dirs.Length + " 个:");
            foreach (var dir in dirs)
            {
                Console.WriteLine(string.Format("  {0,-46} 解压后={1,10}  flags=0x{2:X}",
                    dir.Name, dir.DecompressedSize, dir.Flags));
            }

            var f = inst.file;
            Console.WriteLine();
            if (f == null)
            {
                Console.WriteLine("[X] inst.file 为 null");
                return 1;
            }
            Console.WriteLine("Metadata       : " + (f.Metadata == null ? "null" : "ok"));
            if (f.Metadata != null)
            {
                var tt = f.Metadata.TypeTreeTypes;
                Console.WriteLine("TypeTreeTypes  : " + (tt == null ? "null" : tt.Count.ToString()));
            }
            var infos = f.AssetInfos;
            Console.WriteLine("AssetInfos     : " + (infos == null ? "null" : infos.Count.ToString()));
            if (infos == null)
            {
                Console.WriteLine("  试 GenerateQuickLookup() …");
                f.GenerateQuickLookup();
                infos = f.AssetInfos;
                Console.WriteLine("AssetInfos     : " + (infos == null ? "null" : infos.Count.ToString()));
            }
            if (infos == null)
            {
                return 1;
            }

            foreach (var info in infos)
            {
                var typeId = info.GetTypeId(f);
                Console.WriteLine(string.Format("  pathId={0,-8} typeId={1,-4} byteSize={2}{3}",
                    info.PathId, typeId, info.ByteSize,
                    typeId == 114 ? "  <- MonoBehaviour" : ""));
            }
            return 0;
        }

        // ================================================================ dump
        private static int DumpCommand(string path, string outPath)
        {
            TextWriter w = Console.Out;
            if (outPath != null)
            {
                w = new StreamWriter(outPath, false, new System.Text.UTF8Encoding(false));
            }

            try
            {
                var am = NewManager();
                var inst = LoadFirst(am, path, out var bun);
                var f = inst.file;

                var monos = new List<AssetFileInfo>();
                foreach (var info in f.AssetInfos)
                {
                    if (info.GetTypeId(f) == 114)
                    {
                        monos.Add(info);
                    }
                }

                w.WriteLine("包文件 : " + path);
                foreach (var info in monos)
                {
                    var bf = am.GetBaseField(inst, info);
                    w.WriteLine();
                    w.WriteLine("--- MonoBehaviour pathId=" + info.PathId
                                + "  byteSize=" + info.ByteSize + " ---");

                    foreach (var nm in new[] { "m_Name", "code", "hash", "stringsHash",
                                               "spritesHash", "buildDate" })
                    {
                        w.WriteLine(string.Format("  {0,-12} = {1}", nm, bf[nm].AsString));
                    }

                    var strings = bf["strings"]["Array"];
                    var n = strings.Children.Count;
                    w.WriteLine("  strings      : " + n + " 条");
                    for (var i = 0; i < Math.Min(6, n); i++)
                    {
                        var e = strings.Children[i];
                        w.WriteLine(string.Format("      [{0}] {1} = {2}",
                            i, e["key"].AsString, Short(e["val"].AsString, 44)));
                    }
                    if (n > 6)
                    {
                        w.WriteLine(string.Format("      ... 共 {0} 条", n));
                    }

                    var sprites = bf["sprites"]["Array"];
                    w.WriteLine("  sprites      : " + sprites.Children.Count + " 条");
                    var errors = bf["errors"]["Array"];
                    w.WriteLine("  errors       : " + errors.Children.Count + " 条");

                    w.WriteLine();
                    w.WriteLine("  === key 含 welldone / correct 的条目 ===");
                    for (var i = 0; i < n; i++)
                    {
                        var e = strings.Children[i];
                        var k = e["key"].AsString;
                        if (k != null
                            && (k.IndexOf("welldone", StringComparison.OrdinalIgnoreCase) >= 0
                                || k.IndexOf("correct", StringComparison.OrdinalIgnoreCase) >= 0))
                        {
                            w.WriteLine(string.Format("      {0,-22} = {1}", k, e["val"].AsString));
                        }
                    }
                }
            }
            finally
            {
                if (outPath != null)
                {
                    w.Flush();
                    w.Dispose();
                    Console.WriteLine("已写出: " + outPath);
                }
            }
            return 0;
        }

        private static string Show(string s)
        {
            return s == null ? "<null>" : "\"" + s + "\"";
        }

        private static string[] Shift(string[] args, int n)
        {
            var outArr = new string[Math.Max(0, args.Length - n)];
            Array.Copy(args, n, outArr, 0, outArr.Length);
            return outArr;
        }

        // ================================================================ keys
        /// <summary>取出指定键的值，输出 `key<TAB>值`（转义格式与 set 的输入一致）。</summary>
        private static int KeysCommand(string path, string[] keys)
        {
            var am = NewManager();
            var inst = LoadFirst(am, path, out var bun);
            var f = inst.file;
            var mono = FindMonoBehaviour(f);
            if (mono == null)
            {
                Console.Error.WriteLine("[X] 包内没有 MonoBehaviour");
                return 1;
            }

            var bf = am.GetBaseField(inst, mono);
            var arr = bf["strings"]["Array"];
            var byKey = new Dictionary<string, string>();
            for (var i = 0; i < arr.Children.Count; i++)
            {
                var e = arr.Children[i];
                var k = e["key"].AsString;
                if (k != null && !byKey.ContainsKey(k))
                {
                    byKey[k] = e["val"].AsString;
                }
            }

            foreach (var k in keys)
            {
                if (byKey.TryGetValue(k, out var v))
                {
                    Console.WriteLine(k + "\t" + Escape(v));
                }
                else
                {
                    Console.Error.WriteLine("[X] 没有这个 key: " + k);
                    return 1;
                }
            }
            return 0;
        }

        private static string Short(string s, int max)
        {
            if (s == null)
            {
                return "(null)";
            }
            s = Escape(s);
            return s.Length <= max ? s : s.Substring(0, max) + "...";
        }

        /// <summary>把换行/制表/反斜杠转义成单行形式（set 的 ReadEdits 能反向解回）。</summary>
        private static string Escape(string s)
        {
            return s.Replace("\\", "\\\\").Replace("\r", "\\r")
                    .Replace("\n", "\\n").Replace("\t", "\\t");
        }

        // ================================================================ export
        /// <summary>导出全部 key/val 为 TSV（转义格式与 set 的输入一致，可双向回环）。</summary>
        private static int ExportCommand(string path, string outPath)
        {
            var am = NewManager();
            var inst = LoadFirst(am, path, out var bun);
            var f = inst.file;
            var mono = FindMonoBehaviour(f);
            if (mono == null)
            {
                Console.Error.WriteLine("[X] 包内没有 MonoBehaviour");
                return 1;
            }

            var bf = am.GetBaseField(inst, mono);
            var arr = bf["strings"]["Array"];

            using (var w = new StreamWriter(outPath, false, new System.Text.UTF8Encoding(false)))
            {
                w.WriteLine("# code=" + bf["code"].AsString
                            + "  buildDate=" + bf["buildDate"].AsString
                            + "  strings=" + arr.Children.Count);
                for (var i = 0; i < arr.Children.Count; i++)
                {
                    var e = arr.Children[i];
                    w.WriteLine(e["key"].AsString + "\t" + Escape(e["val"].AsString));
                }
            }

            Console.WriteLine("已导出 " + arr.Children.Count + " 条 -> " + outPath);
            return 0;
        }

        // ================================================================ set
        /// <summary>
        /// 按 key 替换文案。edits.txt 每行 `key\t新值`，支持 \\n \\t \\r \\\\ 转义，
        /// `#` 开头为注释。任何 key 在包里找不到就**拒绝写出**（只认已验证输入）。
        /// 写完会重新打开输出自验证。
        /// </summary>
        private static int SetCommand(string inPath, string outPath, string mapPath)
        {
            var edits = ReadEdits(mapPath);
            Console.WriteLine("编辑项 " + edits.Count + " 条（来自 " + mapPath + "）");

            var am = NewManager();
            var inst = LoadFirst(am, inPath, out var bun);
            var f = inst.file;

            var mono = FindMonoBehaviour(f);
            if (mono == null)
            {
                Console.Error.WriteLine("[X] 包内没有 MonoBehaviour");
                return 1;
            }

            var bf = am.GetBaseField(inst, mono);
            var arr = bf["strings"]["Array"];
            var byKey = BuildKeyIndex(arr);
            Console.WriteLine("原包：code=" + bf["code"].AsString
                              + "  strings=" + arr.Children.Count
                              + "  唯一 key=" + byKey.Count);
            Console.WriteLine();

            var missing = new List<string>();
            foreach (var edit in edits)
            {
                if (!byKey.TryGetValue(edit[0], out var fld))
                {
                    missing.Add(edit[0]);
                    continue;
                }
                Console.WriteLine("  [OK] " + edit[0]);
                Console.WriteLine("       旧 -> " + Short(fld["val"].AsString, 74));
                fld["val"].AsString = edit[1];
                Console.WriteLine("       新 -> " + Short(edit[1], 74));
            }

            if (missing.Count > 0)
            {
                Console.Error.WriteLine();
                Console.Error.WriteLine("[X] 这些 key 在包里不存在，拒绝写出: " + string.Join(", ", missing));
                return 1;
            }

            // 写回：把改过的 MonoBehaviour 作为替换项，重建包。
            // ⚠ 名字必须给真实的条目名：传 null 时重写目录项会拿到 null 名字，
            //   最终在 AssetBundleBlockAndDirInfo.Write -> WriteNullTerminated(null) 抛 ArgumentNullException。
            var replacers = new List<AssetsReplacer>();
            replacers.Add(new AssetsReplacerFromMemory(f, mono, bf));

            var entryName = bun.file.GetFileName(0);
            Console.WriteLine("包内第 0 项: " + entryName);
            var bundleReplacers = new List<BundleReplacer>();
            bundleReplacers.Add(new BundleReplacerFromAssets(entryName, entryName, f, replacers, 0, null));

            using (var fs = File.Create(outPath))
            {
                bun.file.Write(new AssetsFileWriter(fs), bundleReplacers, null);
            }
            Console.WriteLine();
            Console.WriteLine("已写出: " + outPath + "  " + new FileInfo(outPath).Length + " bytes");

            if (s_pack != null)
            {
                Repack(outPath, s_pack);
            }

            return VerifyEdits(outPath, edits);
        }

        /// <summary>
        /// 把刚写出的（未压缩）包重压一遍。
        /// AssetBundleFile.Write 默认不压：13 个语言包会从 395 KB 涨到 1.78 MB。
        /// lz4 约 576 KB，lzma 更接近原体积。
        /// </summary>
        private static void Repack(string path, string kind)
        {
            var tmp = path + ".unpacked";
            var ok = false;
            try
            {
                File.Move(path, tmp);

                // ⚠ AssetBundleFile 会把自己 Read 时用的 reader 存进 Reader 字段，Pack 用的是它。
                //   所以这个 reader 必须活到 Pack 结束 —— 不能在 Read 之后关掉。
                using (var rs = File.OpenRead(tmp))
                {
                    var reader = new AssetsFileReader(rs);
                    var bun = new AssetBundleFile();
                    bun.Read(reader);

                    using (var ws = File.Create(path))
                    {
                        var comp = kind == "lzma"
                            ? AssetBundleCompressionType.LZMA
                            : AssetBundleCompressionType.LZ4;
                        bun.Pack(reader, new AssetsFileWriter(ws), comp, false, null);
                    }
                }

                ok = true;
                Console.WriteLine("已用 " + kind.ToUpperInvariant() + " 重压: "
                                  + new FileInfo(path).Length + " bytes");
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("[!] 重压失败，退回未压缩版: "
                                        + ex.GetType().Name + ": " + ex.Message);
            }
            finally
            {
                if (ok)
                {
                    if (File.Exists(tmp))
                    {
                        File.Delete(tmp);
                    }
                }
                else
                {
                    if (File.Exists(path))
                    {
                        File.Delete(path);
                    }
                    if (File.Exists(tmp))
                    {
                        File.Move(tmp, path);
                    }
                }
            }
        }

        /// <summary>重新打开刚写出的包，逐条比对。不通过就报错。</summary>
        private static int VerifyEdits(string path, List<string[]> edits)
        {
            Console.WriteLine();
            Console.WriteLine("=== 自验证：重新读取输出 ===");

            var am = NewManager();
            var inst = LoadFirst(am, path, out var bun);
            var f = inst.file;
            var mono = FindMonoBehaviour(f);
            if (mono == null)
            {
                Console.Error.WriteLine("  [X] 重新打开后找不到 MonoBehaviour");
                return 1;
            }

            var bf = am.GetBaseField(inst, mono);
            var arr = bf["strings"]["Array"];
            var values = new Dictionary<string, string>();
            for (var i = 0; i < arr.Children.Count; i++)
            {
                var e = arr.Children[i];
                var k = e["key"].AsString;
                if (k != null && !values.ContainsKey(k))
                {
                    values[k] = e["val"].AsString;
                }
            }
            Console.WriteLine("  code=" + bf["code"].AsString
                              + "  buildDate=" + bf["buildDate"].AsString
                              + "  strings=" + arr.Children.Count);

            var bad = 0;
            foreach (var edit in edits)
            {
                if (!values.TryGetValue(edit[0], out var got))
                {
                    Console.Error.WriteLine("  [X] " + edit[0] + " -> 条目丢失");
                    bad++;
                }
                else if (got != edit[1])
                {
                    Console.Error.WriteLine("  [X] " + edit[0] + " -> 值不符: " + Short(got, 60));
                    bad++;
                }
                else
                {
                    Console.WriteLine("  [OK] " + edit[0]);
                }
            }

            Console.WriteLine();
            Console.WriteLine(bad == 0 ? "自验证通过" : "自验证有 " + bad + " 处问题");
            return bad == 0 ? 0 : 1;
        }

        private static AssetFileInfo FindMonoBehaviour(AssetsFile f)
        {
            foreach (var info in f.AssetInfos)
            {
                if (info.GetTypeId(f) == 114)
                {
                    return info;
                }
            }
            return null;
        }

        private static Dictionary<string, AssetTypeValueField> BuildKeyIndex(AssetTypeValueField arr)
        {
            var byKey = new Dictionary<string, AssetTypeValueField>();
            for (var i = 0; i < arr.Children.Count; i++)
            {
                var e = arr.Children[i];
                var k = e["key"].AsString;
                if (k != null && !byKey.ContainsKey(k))
                {
                    byKey[k] = e;
                }
            }
            return byKey;
        }

        private static List<string[]> ReadEdits(string path)
        {
            var list = new List<string[]>();
            var lines = File.ReadAllLines(path, System.Text.Encoding.UTF8);
            for (var n = 0; n < lines.Length; n++)
            {
                var line = lines[n];
                if (line.Length == 0 || line[0] == '#')
                {
                    continue;
                }
                var tab = line.IndexOf('\t');
                if (tab < 0)
                {
                    throw new InvalidDataException(
                        "第 " + (n + 1) + " 行缺少 Tab 分隔: " + line);
                }
                list.Add(new[] { line.Substring(0, tab), Unescape(line.Substring(tab + 1)) });
            }
            return list;
        }

        private static string Unescape(string s)
        {
            var sb = new System.Text.StringBuilder();
            for (var i = 0; i < s.Length; i++)
            {
                if (s[i] != '\\' || i + 1 >= s.Length)
                {
                    sb.Append(s[i]);
                    continue;
                }
                var c = s[++i];
                switch (c)
                {
                    case 'n': sb.Append('\n'); break;
                    case 't': sb.Append('\t'); break;
                    case 'r': sb.Append('\r'); break;
                    case '\\': sb.Append('\\'); break;
                    default: sb.Append('\\').Append(c); break;
                }
            }
            return sb.ToString();
        }

        /// <summary>递归打印字段，depth 控制展开层数（数组只展前几项）。</summary>
        private static void DumpField(TextWriter w, AssetTypeValueField field, string indent, int depth, int maxDepth)
        {
            if (field == null)
            {
                return;
            }

            var value = field.Value == null ? "" : field.Value.AsString;
            if (value != null && value.Length > 60)
            {
                value = value.Substring(0, 60) + "…";
            }

            w.WriteLine(string.Format("{0}{1} ({2}) = {3}",
                indent, field.FieldName, field.TypeName, value));

            if (depth >= maxDepth)
            {
                return;
            }

            var n = field.Children.Count;
            if (n == 0)
            {
                return;
            }

            var isArray = field.TemplateField != null && field.TemplateField.IsArray;
            var shown = isArray ? Math.Min(n, 3) : n;
            for (var i = 0; i < shown; i++)
            {
                if (isArray)
                {
                    w.WriteLine(string.Format("{0}  [{1}]", indent, i));
                }
                DumpField(w, field.Children[i], indent + (isArray ? "    " : "  "),
                          depth + 1, maxDepth);
            }
            if (n > shown)
            {
                w.WriteLine(string.Format("{0}  … 共 {1} 项", indent, n));
            }
        }

        // ================================================================ patchdll
        //
        // 就地给玩家的 Assembly-CSharp.dll 打难度补丁（A / B1 / B2 / C 四处，
        // 配方见 hardcore/PATCH-SPEC.md）。
        //
        // 关键：**按类型名 + 方法名 + 语义定位，不用绝对偏移、也不用哈希白名单**
        // ⇒ 对任何游戏 build 都通用。这正是不再用「预编译整份 DLL 覆盖」的原因：
        // 整份覆盖会把玩家自己那个 build 的代码整份换掉，就地改只动这四个点，
        // 玩家 build 里别的东西原样保留。
        //
        //     langtool patchdll <in.dll> <out.dll> <档位> [--deps=<Managed 目录>]
        //
        // 读完一个**已经打过补丁**的 DLL 再打也是安全的：A 总能改（它只是换常量），
        // B1/B2/C 找不到现场就跳过 —— 结果等价于「只换档位」。
        private static int PatchDllCommand(string[] args)
        {
            if (args.Length < 4)
            {
                Usage();
                return 2;
            }

            var inPath = args[1];
            var outPath = args[2];
            int level;
            if (!int.TryParse(args[3], out level))
            {
                Console.Error.WriteLine("[X] 档位不是数字: " + args[3]);
                return 2;
            }
            if (!File.Exists(inPath))
            {
                Console.Error.WriteLine("[X] 找不到输入 DLL: " + inPath);
                return 1;
            }

            // ★ Cecil 写盘时要解析 UnityEngine.* 才能重建元数据（凡是带默认值的参数
            //   都会触发 GetConstantType -> Resolve），所以必须能搜到这些程序集。
            //   优先 --deps 指的目录（就是游戏里的 Managed），其次输入 DLL 自己所在目录。
            var resolver = new DefaultAssemblyResolver();
            var search = new List<string>();
            if (!string.IsNullOrEmpty(s_deps))
            {
                foreach (var d in s_deps.Split(new[] { ';' }, StringSplitOptions.RemoveEmptyEntries))
                {
                    if (Directory.Exists(d))
                    {
                        search.Add(d);
                    }
                }
            }
            var inDir = Path.GetDirectoryName(Path.GetFullPath(inPath));
            if (!string.IsNullOrEmpty(inDir) && Directory.Exists(inDir))
            {
                search.Add(inDir);
            }
            if (search.Count == 0)
            {
                Console.Error.WriteLine("[X] 没有可用的依赖目录：请加 --deps=<游戏 ObraDinn_Data/Managed>");
                return 1;
            }
            foreach (var d in search)
            {
                resolver.AddSearchDirectory(d);
            }

            var changed = new List<string>();
            var inLen = new FileInfo(inPath).Length;

            try
            {
                using (var asm = AssemblyDefinition.ReadAssembly(inPath, new ReaderParameters
                {
                    ReadSymbols = false,
                    InMemory = true,
                    AssemblyResolver = resolver,
                }))
                {
                    // ---------------------------------------------------------- A
                    var ug = FindTypeMethod(asm, "FateEditor", "UpdateFateGuesses", 2);
                    if (ug == null)
                    {
                        Console.Error.WriteLine("[X] 找不到 FateEditor.UpdateFateGuesses(Book, String)");
                        Console.Error.WriteLine("    这个 DLL 认不出来，拒绝改（宁可不让用，也不盲改）");
                        return 1;
                    }

                    var aIl = ug.Body.GetILProcessor();
                    var aIns = ug.Body.Instructions;
                    Instruction constIns = null;
                    for (var i = 0; i < aIns.Count && constIns == null; i++)
                    {
                        if (aIns[i].OpCode != OpCodes.Callvirt ||
                            aIns[i].Operand is not MethodReference mref ||
                            mref.Name != "GetZoneUnsolvedCount")
                        {
                            continue;
                        }

                        // 紧跟其后（跳过 stloc）的第一条 ldc.i4* 就是批大小常量
                        for (var j = i + 1; j < Math.Min(i + 5, aIns.Count); j++)
                        {
                            if (IsLdcI4(aIns[j]))
                            {
                                constIns = aIns[j];
                                break;
                            }
                        }
                    }

                    if (constIns == null)
                    {
                        Console.Error.WriteLine(
                            "[X] 在 UpdateFateGuesses 里找不到 GetZoneUnsolvedCount 之后的 ldc.i4 常量");
                        return 1;
                    }

                    var oldVal = LdcI4Value(constIns);
                    var aOffset = constIns.Offset;
                    aIl.Replace(constIns, LdcI4(level));
                    changed.Add(string.Format("A  批大小 num: {0} -> {1}   (IL_{2:X4})",
                        oldVal, level, aOffset));

                    // ---------------------------------------------------- B / C
                    var rcg = FindTypeMethod(asm, "Book", "RevealCorrectGuesses", 1);
                    if (rcg == null)
                    {
                        Console.Error.WriteLine("[X] 找不到 Book.RevealCorrectGuesses(List<String>)");
                        return 1;
                    }

                    var bIl = rcg.Body.GetILProcessor();
                    var bIns = rcg.Body.Instructions;

                    // B1 —— 让 2 元素数组变死代码。
                    // ⚠ 不能只靠「最近的 ldc.i4.2 + 分支」定位：同一方法里有三处满足该形状。
                    //   这里多一条判据：前面必须紧跟 get_Count。
                    var b1done = false;
                    for (var i = 1; i + 1 < bIns.Count && !b1done; i++)
                    {
                        if (!IsLdcI4Const(bIns[i], 2))
                        {
                            continue;
                        }

                        var branch = bIns[i + 1];
                        if (branch.OpCode.Code != Code.Bne_Un && branch.OpCode.Code != Code.Bne_Un_S)
                        {
                            continue;
                        }

                        if (bIns[i - 1].OpCode != OpCodes.Callvirt ||
                            bIns[i - 1].Operand is not MethodReference cm || cm.Name != "get_Count")
                        {
                            continue;
                        }

                        // ★ 决定性判据（PATCH-SPEC）：这个分支的**目标**必须是
                        //   `ldc.i4.3; newarr` —— 即「建 3 元素数组」那一处。
                        //   同方法里还有两处 ldc.i4.2 + 分支也紧跟在 get_Count 后面
                        //   （welldoneId 的 Count != 2），只靠 get_Count 会撞上错的那一处：
                        //   对**已打过补丁**的 DLL 实测就撞到了 IL_00F2，把无关的分支也改成了 br。
                        var target = branch.Operand as Instruction;
                        if (target == null || target.OpCode.Code != Code.Ldc_I4_3
                            || target.Next == null || target.Next.OpCode.Code != Code.Newarr)
                        {
                            continue;
                        }

                        var b1Offset = branch.Offset;
                        bIl.Replace(branch, branch.OpCode.Code == Code.Bne_Un_S
                            ? Instruction.Create(OpCodes.Br_S, target)
                            : Instruction.Create(OpCodes.Br, target));
                        changed.Add(string.Format(
                            "B1 2 元素数组分支变死代码   (IL_{0:X4})", b1Offset));
                        b1done = true;
                    }

                    if (!b1done)
                    {
                        Console.Error.WriteLine("[!] B1 没找到现场（若已打过补丁则正常）");
                    }

                    // B2 —— array[num] -> array[num % 3]，不取模批次 >3 时会越界崩溃。
                    var b2done = false;
                    foreach (var ins in bIns.ToList())
                    {
                        if (ins.OpCode.Code != Code.Ldelem_Ref
                            || ins.Previous == null || ins.Previous.Previous == null)
                        {
                            continue;
                        }
                        if (ins.Previous.OpCode.Code != Code.Ldloc_1
                            || ins.Previous.Previous.OpCode.Code != Code.Ldloc_2)
                        {
                            continue;
                        }

                        // ⚠ ldc.i4.3 是 0x19，不是 0x18（那是 ldc.i4.2）；写成 18 会变成 num % 2
                        bIl.InsertBefore(ins, Instruction.Create(OpCodes.Ldc_I4_3));
                        bIl.InsertBefore(ins, Instruction.Create(OpCodes.Rem));
                        changed.Add(string.Format(
                            "B2 音效索引 num -> num % 3   (IL_{0:X4} 之前)", ins.Offset));
                        b2done = true;
                        break;
                    }

                    if (!b2done)
                    {
                        Console.Error.WriteLine("[!] B2 没找到现场（若已打过补丁则正常）");
                    }

                    // C —— 盖章步进间隔 1.2f -> 2.4f/(Count-1)，任意批次总时长恒定 2.4s
                    var sealSite = FindSealStepInterval(bIns);
                    MethodReference countRef = null;
                    foreach (var x in bIns)
                    {
                        if (x.OpCode == OpCodes.Callvirt && x.Operand is MethodReference gmr
                            && gmr.Name == "get_Count" && gmr.Parameters.Count == 0)
                        {
                            countRef = gmr;
                            break;
                        }
                    }

                    var cDone = false;
                    if (sealSite == null)
                    {
                        Console.Error.WriteLine("[!] C 没找到 1.2f 步进间隔现场（若已打过补丁则正常）");
                    }
                    else if (countRef == null)
                    {
                        Console.Error.WriteLine("[!] C 找不到可复用的 List<String>::get_Count 引用");
                    }
                    else
                    {
                        // ⚠ 复用同一条 get_Count 的 MethodReference 是安全的，但必须**新建指令对象**：
                        //   Cecil 的指令是链表节点，同一个对象不能同时出现在两处。
                        var sealOffset = sealSite.Offset;
                        var seq = new[]
                        {
                            Instruction.Create(OpCodes.Ldc_R4, 2.4f),
                            Instruction.Create(OpCodes.Ldarg_1),
                            Instruction.Create(OpCodes.Callvirt, countRef),
                            Instruction.Create(OpCodes.Ldc_I4_1),
                            Instruction.Create(OpCodes.Sub),
                            Instruction.Create(OpCodes.Conv_R4),
                            Instruction.Create(OpCodes.Div),
                        };
                        foreach (var s in seq)
                        {
                            bIl.InsertBefore(sealSite, s);
                        }
                        bIl.Remove(sealSite);
                        cDone = true;
                        changed.Add(string.Format(
                            "C  盖章步进 1.2f -> 2.4f/(Count-1)   (IL_{0:X4}，总时长恒定)", sealOffset));
                    }

                    // 插入使求值栈峰值上升（B2 -> 4，C -> 4），MaxStack 给足
                    if ((b2done || cDone) && rcg.Body.MaxStackSize < 4)
                    {
                        changed.Add("   顺带把 MaxStackSize " + rcg.Body.MaxStackSize + " -> 4");
                        rcg.Body.MaxStackSize = 4;
                    }

                    asm.Write(outPath, new WriterParameters { WriteSymbols = false });
                }
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("[X] " + ex.GetType().Name + ": " + ex.Message);
                var inner = ex.InnerException;
                while (inner != null)
                {
                    Console.Error.WriteLine("  -- 内部: " + inner.GetType().Name + ": " + inner.Message);
                    inner = inner.InnerException;
                }
                return 1;
            }

            Console.WriteLine("== 已改写 ==");
            foreach (var c in changed)
            {
                Console.WriteLine("  " + c);
            }
            Console.WriteLine();
            Console.WriteLine("输出: " + outPath + "  (" + new FileInfo(outPath).Length + " bytes)");
            Console.WriteLine("原文件: " + inPath + "  (" + inLen + " bytes)");
            return 0;
        }

        /// <summary>
        /// 找 C 的现场：方法末尾「盖章计数」循环里 MakeFunc(..., 1.2f, ...) 的那个 1.2f。
        /// 判据：全方法**唯一**的 ldc.r4 1.2f，且相邻指令必须是
        /// `newobj BookAnim/Func::.ctor` 与 `ldnull`。认不出返回 null（按设计拒绝盲改）。
        /// </summary>
        private static Instruction FindSealStepInterval(IList<Instruction> ins)
        {
            Instruction hit = null;
            var n = 0;
            foreach (var i in ins)
            {
                if (i.OpCode != OpCodes.Ldc_R4 || i.Operand is not float f || Math.Abs(f - 1.2f) > 1e-6f)
                {
                    continue;
                }
                n++;
                hit = i;
            }

            if (n != 1 || hit == null || hit.Previous == null || hit.Next == null)
            {
                return null;
            }
            if (hit.Previous.OpCode != OpCodes.Newobj || hit.Next.OpCode != OpCodes.Ldnull)
            {
                return null;
            }

            var ctor = hit.Previous.Operand as MethodReference;
            if (ctor == null || ctor.Name != ".ctor"
                || ctor.DeclaringType == null
                || ctor.DeclaringType.FullName.IndexOf("BookAnim", StringComparison.Ordinal) < 0)
            {
                return null;
            }
            return hit;
        }

        // ============================================================== revealhook

        /// <summary>
        /// 一个「钩子站点」：在宿主方法 ldftn 出来的某个动画回调里找一条锚点指令，
        /// 紧跟在它后面插一句 Game.SaveActive。
        ///
        /// Anchor 返回「要插在它之后」的那条指令；返回 null 表示这个回调不是我们要的。
        /// </summary>
        private sealed class HookSite
        {
            public string Type;
            public string Method;
            public int ParamCount;
            public string Label;
            public Func<IList<Instruction>, Instruction> Anchor;
        }

        /// <summary>
        /// 三个站点，全部用语义判据定位 —— 不认文件偏移，也不认编译器生成的 lambda 名字；
        /// 认不出来就拒绝改（与 patchdll 一样的策略）。
        ///
        ///   Book.RevealNewPages / RevealCompleteChapter  —— 书页浮现 / 全章盖戳
        ///   ShipEnder.Start                            —— 暴风雨演出结束（船尾船夫提示条）
        /// </summary>
        private static readonly HookSite[] s_sites =
        {
            new HookSite
            {
                Type = "Book", Method = "RevealNewPages", ParamCount = 1,
                Label = "书页浮现",
                Anchor = ins => FindCall(ins, "Book", "StartFlash"),
            },
            new HookSite
            {
                Type = "Book", Method = "RevealCompleteChapter", ParamCount = 1,
                Label = "全章盖戳 / 失踪页",
                Anchor = ins => FindCall(ins, "Book", "StartFlash"),
            },
            new HookSite
            {
                Type = "ShipEnder", Method = "Start", ParamCount = 0,
                Label = "暴风雨演出结束（船尾船夫提示条）",
                Anchor = ins => FindFieldCall(ins, "notifyDialogInfo"),
            },
        };

        /// <summary>
        /// 打三个「即时落盘」钩子：在动画回调（或状态机回调）里的关键那一句之后，
        /// 插一句 Game.SaveActive(Game.SaveMilestone.Normal)。
        ///
        /// 为什么需要它：游戏只有 5 个时机写存档（回忆开始 / 走出回忆门之后 / 幽灵显形结束 /
        /// 暂停菜单 / 失焦）。而下面这几件事都是改**内存**的，下一次落盘可能已经过了很久：
        ///
        ///   1. Book.RevealNewPages       —— revealedPageInBook = true（玩家看到新书页的那一刻），
        ///      落盘要等到玩家读完书、走出回忆门；
        ///   2. Book.RevealCompleteChapter —— revealedDisappearancesInBook（失踪页）同理；
        ///   3. ShipEnder                 —— era 0 -> 1（暴风雨开始）。实测有整周目快照里
        ///      根本没出现过 era=1 —— 文件直接 0 -> 2 的话，等于这次「暴风雨」从没被磁盘记下过。
        ///      改的是**演出结束那一帧**（船尾船夫提示条弹出、随即 Go(ZoneDone)），不是
        ///      `era = 1` 那句赋值：赋值那一帧屏幕正黑着、雷声刚要响，提醒会撞进演出里；
        ///      而这时 era 早就已经是 1，写下去的存档照样带 era=1。
        ///
        /// 站点判据（全部语义判据）：
        ///   1. 宿主方法必须是表里那个；
        ///   2. 宿主里 ldftn 取地址的那些 lambda 中，**函数体里有指定锚点的只有一个**；
        ///      0 个或多个就认为判据失效，拒绝改。
        ///   3. 插在锚点之后（这些位置求值栈都为空，插 ldc.i4.0 + call 正好）；
        ///      锚点本身必须**不被插入改变**，否则复验时认不回同一个锚点
        ///      —— 所以站点 3 用的是 Show 那条 callvirt，不是「ret 前一条」
        /// </summary>
        private static int RevealHookCommand(string[] args)
        {
            if (args.Length < 2)
            {
                Usage();
                return 2;
            }

            // --check：只查不改。给提示工具判断「钩子在不在」用，也方便人肉排查。
            if (s_check)
            {
                return RevealHookCheck(args[1]);
            }

            if (args.Length < 3)
            {
                Usage();
                return 2;
            }

            var inPath = args[1];
            var outPath = args[2];
            if (!File.Exists(inPath))
            {
                Console.Error.WriteLine("[X] 找不到输入 DLL: " + inPath);
                return 1;
            }

            string err;
            var resolver = MakeDllResolver(inPath, out err);
            if (resolver == null)
            {
                Console.Error.WriteLine("[X] " + err);
                return 1;
            }

            var inLen = new FileInfo(inPath).Length;
            var changed = new List<string>();
            var already = new List<string>();
            var missing = new List<string>();

            try
            {
                using (var asm = AssemblyDefinition.ReadAssembly(inPath, new ReaderParameters
                {
                    ReadSymbols = false,
                    InMemory = true,
                    AssemblyResolver = resolver,
                }))
                {
                    var saveActive = FindTypeMethod(asm, "Game", "SaveActive", 1);
                    if (saveActive == null)
                    {
                        Console.Error.WriteLine("[X] 找不到 Game.SaveActive(Game/SaveMilestone)");
                        Console.Error.WriteLine("    这个 DLL 认不出来，拒绝改（宁可不让用，也不盲改）");
                        return 1;
                    }

                    foreach (var site in s_sites)
                    {
                        var where = site.Type + "." + site.Method;
                        var host = FindTypeMethod(asm, site.Type, site.Method, site.ParamCount);
                        if (host == null)
                        {
                            missing.Add(site.Label + "：" + where + " 不存在");
                            continue;
                        }

                        MethodDefinition lambda;
                        Instruction anchor;
                        if (!FindLambdaWithAnchor(host, site.Anchor, out lambda, out anchor))
                        {
                            missing.Add(site.Label + "：在 " + where
                                        + " 的 ldftn 回调里找不到唯一的锚点");
                            continue;
                        }

                        // 幂等：已经有钩子就不要再插一句（重复插会写两次存档）
                        if (FindCall(lambda.Body.Instructions, "Game", "SaveActive") != null)
                        {
                            already.Add(site.Label);
                            continue;
                        }

                        var il = lambda.Body.GetILProcessor();
                        var ldc = Instruction.Create(OpCodes.Ldc_I4_0);
                        var call = Instruction.Create(OpCodes.Call, saveActive);
                        il.InsertAfter(anchor, ldc);
                        il.InsertAfter(ldc, call);

                        // 插入后求值栈峰值是 1，但保守起见给到 2（与 patchdll 同样的做法）
                        if (lambda.Body.MaxStackSize < 2)
                        {
                            lambda.Body.MaxStackSize = 2;
                        }

                        changed.Add(string.Format("{0}：在锚点之后插 SaveActive   (IL_{1:X4}，改的是 {2})",
                            site.Label, anchor.Offset, lambda.FullName));
                    }

                    if (changed.Count == 0)
                    {
                        foreach (var m in missing)
                        {
                            Console.Error.WriteLine("[X] " + m);
                        }
                        if (already.Count > 0 && missing.Count == 0)
                        {
                            if (!string.Equals(Path.GetFullPath(inPath), Path.GetFullPath(outPath),
                                    StringComparison.OrdinalIgnoreCase))
                            {
                                File.Copy(inPath, outPath, true);
                            }
                            Console.WriteLine("已有钩子，原样输出: " + outPath);
                            return 0;
                        }
                        Console.Error.WriteLine("[X] 一处也改不了，拒绝写盘");
                        return 1;
                    }

                    foreach (var m in missing)
                    {
                        Console.Error.WriteLine("[!] 跳过（没找到现场）: " + m);
                    }
                    foreach (var a in already)
                    {
                        Console.WriteLine("  -  " + a + "  已有钩子，跳过");
                    }

                    asm.Write(outPath, new WriterParameters { WriteSymbols = false });
                }
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("[X] " + ex.GetType().Name + ": " + ex.Message);
                var inner = ex.InnerException;
                while (inner != null)
                {
                    Console.Error.WriteLine("  -- 内部: " + inner.GetType().Name + ": " + inner.Message);
                    inner = inner.InnerException;
                }
                return 1;
            }

            Console.WriteLine("== 已改写 ==");
            foreach (var c in changed)
            {
                Console.WriteLine("  " + c);
            }

            // ★ 复验：重新读一遍产物，确认钩子真的在 StartFlash 之后、而且栈上先压了 0。
            //   写盘成功 != 改对了，所以必须走这一步（与 patchdll 的 verify_patched_dll 同理）。
            var problems = new List<string>();
            var resolver2 = MakeDllResolver(outPath, out err);
            try
            {
                using (var asm2 = AssemblyDefinition.ReadAssembly(outPath, new ReaderParameters
                {
                    ReadSymbols = false,
                    InMemory = true,
                    AssemblyResolver = resolver2,
                }))
                {
                    foreach (var site in s_sites)
                    {
                        var host = FindTypeMethod(asm2, site.Type, site.Method, site.ParamCount);
                        if (host == null)
                        {
                            problems.Add(site.Label + "：方法不见了");
                            continue;
                        }
                        MethodDefinition lambda;
                        Instruction anchor;
                        if (!FindLambdaWithAnchor(host, site.Anchor, out lambda, out anchor))
                        {
                            problems.Add(site.Label + "：认不出锚点所在的那个回调");
                            continue;
                        }
                        var ldc = anchor.Next;
                        var call = ldc == null ? null : ldc.Next;
                        if (ldc == null || !IsLdcI4Const(ldc, 0))
                        {
                            problems.Add(site.Label + "：锚点之后不是 ldc.i4.0");
                            continue;
                        }
                        if (call == null || call.OpCode.Code != Code.Call
                            || call.Operand is not MethodReference mr || mr.Name != "SaveActive")
                        {
                            problems.Add(site.Label + "：ldc.i4.0 之后不是 call Game::SaveActive");
                            continue;
                        }
                        if (lambda.Body.MaxStackSize < 2)
                        {
                            problems.Add(site.Label + "：MaxStackSize 还是 " + lambda.Body.MaxStackSize
                                          + "，会 JIT 失败");
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                problems.Add("复验时读不回来: " + ex.GetType().Name + ": " + ex.Message);
            }

            if (problems.Count > 0)
            {
                Console.Error.WriteLine("[X] 复验失败，产物**不可用**：");
                foreach (var p in problems)
                {
                    Console.Error.WriteLine("      " + p);
                }
                return 1;
            }

            Console.WriteLine();
            Console.WriteLine("复验通过：三个站点的钩子都各就各位");
            Console.WriteLine("输出: " + outPath + "  (" + new FileInfo(outPath).Length + " bytes)");
            Console.WriteLine("原文件: " + inPath + "  (" + inLen + " bytes)");
            return 0;
        }

        /// <summary>
        /// 只查不改：每个站点的回调里有没有那句 SaveActive。
        /// 全部有 → 0；全都没有或认不出 → 1；只有一部分 → 2。
        /// </summary>
        private static int RevealHookCheck(string dllPath)
        {
            if (!File.Exists(dllPath))
            {
                Console.Error.WriteLine("[X] 找不到 DLL: " + dllPath);
                return 1;
            }

            string err;
            var resolver = MakeDllResolver(dllPath, out err);
            try
            {
                using (var asm = AssemblyDefinition.ReadAssembly(dllPath, new ReaderParameters
                {
                    ReadSymbols = false,
                    InMemory = true,
                    AssemblyResolver = resolver,
                }))
                {
                    var have = 0;
                    var total = 0;
                    foreach (var site in s_sites)
                    {
                        var host = FindTypeMethod(asm, site.Type, site.Method, site.ParamCount);
                        if (host == null)
                        {
                            Console.Error.WriteLine("[X] " + site.Type + "." + site.Method + "：没有这个方法");
                            return 1;
                        }
                        MethodDefinition lambda;
                        Instruction anchor;
                        if (!FindLambdaWithAnchor(host, site.Anchor, out lambda, out anchor))
                        {
                            Console.Error.WriteLine("[X] " + site.Type + "." + site.Method
                                                    + "：认不出锚点所在的那个回调");
                            return 1;
                        }
                        total++;
                        var call = FindCall(lambda.Body.Instructions, "Game", "SaveActive");
                        Console.WriteLine((call != null ? "  [有] " : "  [无] ") + site.Label
                                          + "  " + lambda.FullName);
                        if (call != null)
                        {
                            have++;
                        }
                    }

                    if (have == total)
                    {
                        Console.WriteLine("钩子: 已装（" + have + "/" + total + "）");
                        return 0;
                    }
                    if (have == 0)
                    {
                        Console.WriteLine("钩子: 未装（0/" + total + "）");
                        return 1;
                    }
                    Console.WriteLine("[!] 钩子只装了一半（" + have + "/" + total + "）");
                    return 2;
                }
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("[X] " + ex.GetType().Name + ": " + ex.Message);
                return 1;
            }
        }

        private static bool FindLambdaWithAnchor(
            MethodDefinition host,
            Func<IList<Instruction>, Instruction> anchorFinder,
            out MethodDefinition lambda,
            out Instruction anchor)
        {
            lambda = null;
            anchor = null;
            if (host == null || !host.HasBody)
            {
                return false;
            }

            var hits = new List<MethodDefinition>();
            foreach (var ins in host.Body.Instructions)
            {
                if (ins.OpCode != OpCodes.Ldftn || ins.Operand is not MethodReference mr)
                {
                    continue;
                }
                var def = TryResolve(mr);
                if (def == null || !def.HasBody)
                {
                    continue;
                }
                var a = anchorFinder(def.Body.Instructions);
                if (a == null)
                {
                    continue;
                }
                if (hits.Any(h => h.FullName == def.FullName))
                {
                    continue;
                }
                hits.Add(def);
                lambda = def;
                anchor = a;
            }
            return hits.Count == 1;      // 0 个或多个都算判据失效
        }

        /// <summary>
        /// 找「用到指定字段的那个回调里、紧跟该字段之后的那次方法调用」，
        /// 用于 ShipEnder 里这一句：
        ///
        ///     this.notifyDialogInfo.Show(this.boatPullerAudioSource);
        ///     this.stater.Go(ShipEnder.State.ZoneDone, false);
        ///
        /// 它是 `ZonePullerCallout` 的 AT_STEP(8f) 回调 —— 暴风雨演出（2s 雷声 + 雨、
        /// 4s 环境音）走完、船尾船夫提示条弹出的那一帧，而 `era` 早在 8 秒前就是 1 了，
        /// 所以在这一帧插 SaveActive，落盘的存档就带着 era=1，而且只在每次暴风雨里触发一次
        /// （挂在 ZoneDone 的 ENTER 上会连带「回头看船夫」那些重入一起写盘）。
        ///
        /// 返回 Show 那条 call：它后面求值栈是空的（插 ldc.i4.0 + call 正好），
        /// 而且插入不会改动它本身 —— 复验时能认出同一个锚点。
        /// 只认字段名，不认编译器生成的 lambda 名。
        /// </summary>
        private static Instruction FindFieldCall(IList<Instruction> ins, string fieldName)
        {
            for (var i = 0; i + 1 < ins.Count; i++)
            {
                if (ins[i].Operand is not FieldReference fr || fr.Name != fieldName)
                {
                    continue;
                }
                for (var j = i + 1; j < ins.Count; j++)
                {
                    var code = ins[j].OpCode.Code;
                    if (code == Code.Call || code == Code.Callvirt)
                    {
                        return ins[j];
                    }
                    if (code == Code.Ret || code == Code.Newobj)
                    {
                        break;      // 兜底：别越界跑到别的语句里
                    }
                }
            }
            return null;
        }

        /// <summary>找第一条 call/callvirt &lt;typeName&gt;::&lt;methodName&gt;。找不到返回 null。</summary>
        private static Instruction FindCall(IList<Instruction> ins, string typeName, string methodName)
        {
            foreach (var i in ins)
            {
                if (i.OpCode.Code != Code.Call && i.OpCode.Code != Code.Callvirt)
                {
                    continue;
                }
                if (i.Operand is not MethodReference mr || mr.Name != methodName)
                {
                    continue;
                }
                var dt = mr.DeclaringType;
                if (dt != null && (dt.Name == typeName || dt.FullName == typeName))
                {
                    return i;
                }
            }
            return null;
        }

        private static MethodDefinition TryResolve(MethodReference mr)
        {
            try
            {
                return mr.Resolve();
            }
            catch
            {
                return null;
            }
        }

        /// <summary>按 --deps + 输入 DLL 所在目录建 Cecil 解析器（写盘时要解析 UnityEngine.*）。</summary>
        private static DefaultAssemblyResolver MakeDllResolver(string inPath, out string error)
        {
            var resolver = new DefaultAssemblyResolver();
            var search = new List<string>();
            if (!string.IsNullOrEmpty(s_deps))
            {
                foreach (var d in s_deps.Split(new[] { ';' }, StringSplitOptions.RemoveEmptyEntries))
                {
                    if (Directory.Exists(d))
                    {
                        search.Add(d);
                    }
                }
            }
            var inDir = Path.GetDirectoryName(Path.GetFullPath(inPath));
            if (!string.IsNullOrEmpty(inDir) && Directory.Exists(inDir))
            {
                search.Add(inDir);
            }
            error = null;
            if (search.Count == 0)
            {
                error = "没有可用的依赖目录：请加 --deps=<游戏 ObraDinn_Data/Managed>";
                return null;
            }
            foreach (var d in search)
            {
                resolver.AddSearchDirectory(d);
            }
            return resolver;
        }

        private static MethodDefinition FindTypeMethod(
            AssemblyDefinition asm, string typeName, string name, int paramCount)
        {
            foreach (var mod in asm.Modules)
            {
                foreach (var type in mod.GetTypes())
                {
                    if (type.FullName != typeName && type.Name != typeName)
                    {
                        continue;
                    }
                    foreach (var m in type.Methods)
                    {
                        if (m.Name == name && m.Parameters.Count == paramCount)
                        {
                            return m;
                        }
                    }
                }
            }
            return null;
        }

        private static bool IsLdcI4(Instruction i)
        {
            var c = i.OpCode.Code;
            return c == Code.Ldc_I4 || c == Code.Ldc_I4_S
                   || c == Code.Ldc_I4_M1 || (c >= Code.Ldc_I4_0 && c <= Code.Ldc_I4_8);
        }

        /// <summary>取出 ldc.i4 系列的值。★ 短形态（ldc.i4.0~8 / ldc.i4.m1）**没有操作数**，
        /// 值由操作码本身决定 —— 直接读 Operand 会空引用。</summary>
        private static int LdcI4Value(Instruction i)
        {
            switch (i.OpCode.Code)
            {
                case Code.Ldc_I4_M1: return -1;
                case Code.Ldc_I4_0: return 0;
                case Code.Ldc_I4_1: return 1;
                case Code.Ldc_I4_2: return 2;
                case Code.Ldc_I4_3: return 3;
                case Code.Ldc_I4_4: return 4;
                case Code.Ldc_I4_5: return 5;
                case Code.Ldc_I4_6: return 6;
                case Code.Ldc_I4_7: return 7;
                case Code.Ldc_I4_8: return 8;
                default: return Convert.ToInt32(i.Operand);
            }
        }

        private static bool IsLdcI4Const(Instruction i, int v)
        {
            return IsLdcI4(i) && LdcI4Value(i) == v;
        }

        /// <summary>挑最小的 ldc.i4 编码：0..8 用单字节，-128..127 用 ldc.i4.s，其余 ldc.i4。</summary>
        private static Instruction LdcI4(int v)
        {
            switch (v)
            {
                case 0: return Instruction.Create(OpCodes.Ldc_I4_0);
                case 1: return Instruction.Create(OpCodes.Ldc_I4_1);
                case 2: return Instruction.Create(OpCodes.Ldc_I4_2);
                case 3: return Instruction.Create(OpCodes.Ldc_I4_3);
                case 4: return Instruction.Create(OpCodes.Ldc_I4_4);
                case 5: return Instruction.Create(OpCodes.Ldc_I4_5);
                case 6: return Instruction.Create(OpCodes.Ldc_I4_6);
                case 7: return Instruction.Create(OpCodes.Ldc_I4_7);
                case 8: return Instruction.Create(OpCodes.Ldc_I4_8);
                default:
                    return v >= -128 && v <= 127
                        ? Instruction.Create(OpCodes.Ldc_I4_S, (sbyte)v)
                        : Instruction.Create(OpCodes.Ldc_I4, v);
            }
        }
    }
}
