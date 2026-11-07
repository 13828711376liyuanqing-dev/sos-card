// SAM | 2026-10-30 15:40 +08:00 | Standalone tool 4: set the version of both firmwares (GR header + CAT1 main.lua), then compile by hand; check each firmware's size
// against its limit and read the CAT1 free space from the device over a selectable COM port (cat_at OTA_FS). No other tool is linked in; the CAT1 script
// size is measured by calling the sibling Cat1UsbImport.exe when it is next to this tool (the toolkit layout).
// Build: csc (C# 5, .NET Framework 4). GUI when started without arguments, CLI otherwise.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Ports;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Forms;

namespace YpVersion
{
    class Report
    {
        public readonly List<string> Errors = new List<string>();
        readonly Action<string, string> say;
        public Report(Action<string, string> say) { this.say = say; }
        public void Log(string s) { say(null, s); }
        public void Ok(string s) { say(null, "  OK    " + s); }
        public void Good(string s) { say("green", "  OK    " + s); }
        public void Warn(string s) { say("orange", "  WARN  " + s); }
        public void Error(string s) { Errors.Add(s); say("red", "  ERROR " + s); }
        public string Summary() { return Errors.Count == 0 ? "结果：通过" : "结果：失败（错误 " + Errors.Count + "）"; }
    }

    static class Core
    {
        public const string ToolVersion = "1.0";
        public const uint GrStart = 0x00202000;
        public const int GrSlot = 442368, SigBytes = 904, GrBudget = GrSlot - SigBytes, FsReserve = 16384, LuaDb = 524288;
        static readonly UTF8Encoding Utf8 = new UTF8Encoding(false);

        public class Ver { public int A, B, C; public override string ToString() { return A + "." + B + "." + C; } public string Canon() { return string.Format("{0:D3}.{1:D3}.{2:D3}", A, B, C); }
            public int Cmp(Ver o) { return A != o.A ? A.CompareTo(o.A) : B != o.B ? B.CompareTo(o.B) : C.CompareTo(o.C); } }

        public static Ver Parse(string s)
        {
            var m = Regex.Match((s ?? "").Trim(), @"^(\d{1,3})\.(\d{1,3})(?:\.(\d{1,3}))?$");
            if (!m.Success) return null;
            return new Ver { A = int.Parse(m.Groups[1].Value), B = int.Parse(m.Groups[2].Value), C = m.Groups[3].Success ? int.Parse(m.Groups[3].Value) : 0 };
        }

        static string Read(string p) { return File.ReadAllText(p, Utf8); }
        static string Eol(string s) { return s.Contains("\r\n") ? "\r\n" : "\n"; }
        static string Stamp() { return DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8)).ToString("yyyy-MM-dd HH:mm"); }

        public class Ident { public string Product, Canon; public int Build = -1; }

        public static Ident ReadHeader(string path, Report rep)
        {
            string t = Read(path); var id = new Ident();
            var v = Regex.Match(t, @"(?m)^#define\s+YP001_FW_VERSION\s+""(\d{3}\.\d{3}\.\d{3})""");
            var p = Regex.Match(t, @"(?m)^#define\s+YP001_PRODUCT_VERSION\s+""([0-9.]+)""");
            var b = Regex.Match(t, @"(?m)^#define\s+YP001_FW_BUILD\s+(\d+)U");
            if (!v.Success || !p.Success || !b.Success) { rep.Error("GR 版本头文件里找不到 YP001_FW_VERSION / YP001_PRODUCT_VERSION / YP001_FW_BUILD：" + path); return null; }
            id.Canon = v.Groups[1].Value; id.Product = p.Groups[1].Value; id.Build = int.Parse(b.Groups[1].Value); return id;
        }

        public static Ident ReadLua(string path, Report rep)
        {
            string t = Read(path); var id = new Ident();
            var v = Regex.Matches(t, @"(?m)^VERSION\s*=\s*""(\d{3}\.\d{3}\.\d{3})""");
            var p = Regex.Matches(t, @"(?m)^PRODUCT_VERSION\s*=\s*""([0-9.]+)""");
            var b = Regex.Matches(t, @"(?m)^FW_RELEASE_BUILD\s*=\s*(\d+)");
            if (v.Count != 1 || p.Count != 1 || b.Count != 1) { rep.Error("CAT1 main.lua 里 VERSION / PRODUCT_VERSION / FW_RELEASE_BUILD 必须各出现一次：" + path); return null; }
            id.Canon = v[0].Groups[1].Value; id.Product = p[0].Groups[1].Value; id.Build = int.Parse(b[0].Groups[1].Value); return id;
        }

        // Shows the current identities of both firmwares; returns false when one cannot be read.
        public static bool Show(string header, string lua, Report rep)
        {
            bool ok = true;
            if (header != null) { var g = ReadHeader(header, rep); if (g == null) ok = false; else rep.Log("  GR   版本 " + g.Product + "（" + g.Canon + "），build " + g.Build + "    " + header); }
            if (lua != null) { var c = ReadLua(lua, rep); if (c == null) ok = false; else rep.Log("  CAT1 版本 " + c.Product + "（" + c.Canon + "），FW_RELEASE_BUILD " + c.Build + "    " + lua); }
            return ok;
        }

        // Sets the identity of both firmwares. Same rules as tools/ota/Set-FirmwareVersion.ps1: no going back; a new version needs a higher build; the same version keeps its build.
        public static bool Apply(string header, string lua, string version, int? build, Report rep)
        {
            var nv = Parse(version);
            if (nv == null) { rep.Error("版本号格式不对：" + version + "（例如 1.5.3，每段 0..999）"); return false; }
            if (header == null || lua == null) { rep.Error("请同时选择 GR 版本头文件和 CAT1 的 main.lua"); return false; }
            if (!File.Exists(header)) { rep.Error("找不到 GR 版本头文件：" + header); return false; }
            if (!File.Exists(lua)) { rep.Error("找不到 CAT1 main.lua：" + lua); return false; }
            var g = ReadHeader(header, rep); var c = ReadLua(lua, rep);
            if (g == null || c == null) return false;
            var cur = Parse(g.Product);
            if (g.Canon != c.Canon || g.Build != c.Build) rep.Warn("两边现在的版本不一致：GR " + g.Canon + "/b" + g.Build + "，CAT1 " + c.Canon + "/b" + c.Build + "（改完会统一成新版本）");
            int cmp = nv.Cmp(cur);
            if (cmp < 0) { rep.Error("新版本 " + nv + " 低于当前 " + cur + "：不允许版本倒退"); return false; }
            int nb;
            if (cmp == 0)
            {
                nb = g.Build;
                if (build.HasValue && build.Value != g.Build) { rep.Error("版本没变（" + nv + "），构建号不能改（当前 " + g.Build + "，填了 " + build.Value + "）"); return false; }
            }
            else
            {
                nb = build ?? g.Build + 1;
                if (nb <= g.Build) { rep.Error("新版本的构建号必须大于当前的 " + g.Build + "（填了 " + nb + "）"); return false; }
            }
            if (nb < 1 || nb > 65535) { rep.Error("构建号要在 1..65535 之间"); return false; }
            if (cmp == 0 && g.Build == nb && g.Canon == c.Canon && c.Build == nb) { rep.Ok("两边已经是 " + nv + " / build " + nb + "，没有改动"); return true; }

            string root = Path.GetFullPath(Path.Combine(Path.GetDirectoryName(Path.GetFullPath(header)), "..", "..", ".."));
            string backup = Path.Combine(Directory.Exists(Path.Combine(root, "logs")) ? Path.Combine(root, "logs", "firmware_versions") : Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "version_backup"),
                "set_" + DateTime.Now.ToString("yyyyMMdd_HHmmss"));
            Directory.CreateDirectory(backup);
            File.Copy(header, Path.Combine(backup, "gr_version_before.h"), true);
            File.Copy(lua, Path.Combine(backup, "cat1_main_before.lua"), true);

            string canon = nv.Canon(), stamp = Stamp();
            string h = Read(header), eh = Eol(h);
            h = Regex.Replace(h, @"(?m)^#define\s+YP001_FW_VERSION\s+""[0-9.]+""", "#define YP001_FW_VERSION \"" + canon + "\"");
            h = Regex.Replace(h, @"(?m)^#define\s+YP001_PRODUCT_VERSION\s+""[0-9.]+""", "#define YP001_PRODUCT_VERSION \"" + nv + "\"");
            h = Regex.Replace(h, @"(?m)^#define\s+YP001_FW_BUILD\s+\d+U", "#define YP001_FW_BUILD " + nb + "U");
            h = Regex.Replace(h, @"(?m)^#define\s+YP001_FW_BUILD_TEXT\s+""\d+""", "#define YP001_FW_BUILD_TEXT \"" + nb + "\"");
            h = Regex.Replace(h, @"^/\* SAM \|[^\r\n]*\*/", "/* SAM | " + stamp + " +08:00 | Release identity set by YpVersionTool " + nv + "/build " + nb + "; rebuild before use. */");
            File.WriteAllText(header, h, Utf8);

            string l = Read(lua), el = Eol(l);
            l = Regex.Replace(l, @"(?m)^VERSION\s*=\s*""[0-9.]+""", "VERSION = \"" + canon + "\"");
            l = Regex.Replace(l, @"(?m)^PRODUCT_VERSION\s*=\s*""[0-9.]+""", "PRODUCT_VERSION = \"" + nv + "\"");
            l = Regex.Replace(l, @"(?m)^FW_RELEASE_BUILD\s*=\s*\d+", "FW_RELEASE_BUILD = " + nb);
            l = Regex.Replace(l, @"(?m)^-- SAM \| [^\r\n]* \| (Generated source identity|Source identity set by YpVersionTool);[^\r\n]*\r?\n", "");
            l = Regex.Replace(l, @"(?m)^VERSION\s*=", "-- SAM | " + stamp + " +08:00 | Source identity set by YpVersionTool; rebuild GR and CAT1 before use." + el + "VERSION =");
            File.WriteAllText(lua, l, Utf8);

            string meta = Path.Combine(root, "firmware_version.json");
            if (File.Exists(meta))
            {
                string m = Read(meta);
                m = Regex.Replace(m, @"""release_version""\s*:\s*""[0-9.]+""", "\"release_version\":  \"" + nv + "\"");
                m = Regex.Replace(m, @"""component_version""\s*:\s*""[0-9.]+""", "\"component_version\":  \"" + canon + "\"");
                m = Regex.Replace(m, @"""gr_build""\s*:\s*\d+", "\"gr_build\":  " + nb);
                m = Regex.Replace(m, @"""updated_local""\s*:\s*""[^""]*""", "\"updated_local\":  \"" + stamp + " +08:00\"");
                File.WriteAllText(meta, m, Utf8);
                rep.Ok("已同步 " + meta);
            }
            rep.Good("版本已改为 " + nv + "（" + canon + "），build " + nb + "；改前的文件备份在 " + backup);
            rep.Log("  下一步：在 Keil 里重新编译 GR（F7）；CAT1 用 3 号工具重新生成包。这个工具没有编译、没有烧录。");
            if (c.Canon != canon) rep.Log("  注意：CAT1 的 OTA_TRIAL_SOURCE / OTA_TRIAL_TARGET 没有改，请核对它们和这次的版本范围一致。");
            return true;
        }

        // ---- sizes -----------------------------------------------------------------------------------------------------------------------
        public class GrInfo { public int Payload; public bool Signed; public string Marker; public int ImageBytes { get { return Payload + SigBytes; } } }

        public static GrInfo CheckGr(string file, string expectCanon, Report rep)
        {
            if (!File.Exists(file)) { rep.Error("找不到 GR 固件：" + file); return null; }
            string ext = Path.GetExtension(file).ToLowerInvariant();
            if (ext != ".hex" && ext != ".bin") { rep.Error("GR 固件只接受 .hex 或 .bin（Keil、GCC 导出的都行）"); return null; }
            byte[] data; bool signed = false;
            try
            {
                if (ext == ".bin")
                {
                    data = File.ReadAllBytes(file);
                    if (data.Length >= 912) { int at = data.Length - SigBytes; signed = data[at] == 'Y' && data[at + 1] == 'P' && data[at + 2] == 'G' && data[at + 3] == 'R' && BitConverter.ToUInt32(data, at + 4) == (uint)at; }
                    if (signed) { var p = new byte[data.Length - SigBytes]; Array.Copy(data, p, p.Length); data = p; }
                }
                else data = DecodeHex(file);
            }
            catch (Exception ex) { rep.Error("GR 固件读不了：" + ex.Message); return null; }
            var info = new GrInfo { Payload = data.Length, Signed = signed };
            long left = GrBudget - (long)data.Length;
            if (left < 0) { rep.Error("GR 应用共 " + data.Length + " 字节，超过上限 " + GrBudget + " 字节 " + (-left) + " 字节（槽 " + GrSlot + "，含 " + SigBytes + " 字节签名）。要减小固件后重新编译"); return info; }
            int pct = (int)(data.Length * 100L / GrBudget);
            string line = "GR 应用 " + data.Length + " 字节，上限 " + GrBudget + "，余 " + left + " 字节（已用 " + pct + "%）" + (signed ? "，输入带签名尾部" : "");
            if (pct >= 95) rep.Warn(line + "：余量很小，下一版很容易超"); else rep.Good(line);
            // SAM | 2026-11-04 +08:00 | OTA red line (budget.json): the signed image must fit the CAT1 file system, far below the slot.
            long signedSize = data.Length + SigBytes;
            string glv = Yp001.Budget.Level(signedSize, Yp001.Budget.GrSignedYellow, Yp001.Budget.GrSignedRed);
            string gline = "GR 签名镜像 " + signedSize + " 字节，OTA 红线 " + Yp001.Budget.GrSignedRed + "，离红线 " + (Yp001.Budget.GrSignedRed - signedSize);
            if (glv == "red") rep.Error("超过" + gline + "：CAT1 放不下，整机 OTA 会失败，要减小固件");
            else if (glv == "yellow") rep.Warn("接近" + gline + "：加功能前先减小固件");
            else rep.Good(gline);
            string text = Encoding.GetEncoding(28591).GetString(data);
            var ms = Regex.Matches(text, @"YP001_FW\|GR5526\|(\d{3}\.\d{3}\.\d{3})\|(\d+)\|END");
            if (ms.Count != 1) rep.Error("固件里的版本标记应有且只有一个，实际 " + ms.Count + " 个：不是本项目的固件，或没有用新的版本头文件重新编译");
            else
            {
                info.Marker = ms[0].Groups[1].Value + "/b" + ms[0].Groups[2].Value;
                rep.Ok("固件里的版本标记：" + ms[0].Groups[1].Value + "，build " + ms[0].Groups[2].Value);
                if (expectCanon != null && ms[0].Groups[1].Value != expectCanon) rep.Error("固件里的版本 " + ms[0].Groups[1].Value + " 与版本头文件的 " + expectCanon + " 不一致：改完版本后还没有重新编译，或选错了固件文件");
            }
            return info;
        }

        public static byte[] DecodeHex(string file)
        {
            var mem = new SortedDictionary<uint, byte>(); uint bas = 0; bool eof = false;
            foreach (string raw in File.ReadLines(file))
            {
                string line = raw.Trim(); if (line.Length == 0) continue;
                if (eof || line[0] != ':' || line.Length % 2 != 1) throw new Exception("HEX 结构错误或 EOF 后还有数据");
                var r = new byte[(line.Length - 1) / 2]; int sum = 0;
                for (int i = 0; i < r.Length; i++) { r[i] = Convert.ToByte(line.Substring(i * 2 + 1, 2), 16); sum += r[i]; }
                if (r.Length < 5 || r.Length != r[0] + 5 || sum % 256 != 0) throw new Exception("HEX 长度/校验和错误");
                uint off = (uint)(r[1] * 256 + r[2]);
                if (r[3] == 4) bas = (uint)(r[4] * 256 + r[5]) << 16;
                else if (r[3] == 2) bas = (uint)(r[4] * 256 + r[5]) << 4;
                else if (r[3] == 1) eof = true;
                else if (r[3] == 0) for (int i = 0; i < r[0]; i++) mem[bas + off + (uint)i] = r[4 + i];
            }
            if (mem.Count == 0) throw new Exception("HEX 没有数据");
            uint first = mem.Keys.First(), last = mem.Keys.Last();
            if (first < GrStart) throw new Exception("HEX 里有应用区之前的数据（最低地址 0x" + first.ToString("X8") + "，应用从 0x" + GrStart.ToString("X8") + " 开始）：不能含 Boot/SCA/NVDS，请导出只含应用的 HEX");
            var data = new byte[last - GrStart + 1];
            for (int i = 0; i < data.Length; i++) data[i] = 255;
            foreach (var kv in mem) data[kv.Key - GrStart] = kv.Value;
            return data;
        }

        // CAT1 script size: ask the sibling Cat1UsbImport.exe (check only, writes nothing).
        public static void CheckCat(string sourceDir, Report rep)
        {
            string dir = AppDomain.CurrentDomain.BaseDirectory;
            string exe = new[] { Path.Combine(dir, "Cat1UsbImport.exe"), Path.Combine(dir, "..", "1_CAT1刷机目录生成", "Cat1UsbImport.exe") }.Select(Path.GetFullPath).FirstOrDefault(File.Exists);
            if (exe == null) { rep.Error("没找到 Cat1UsbImport.exe（应在工具包的“1_CAT1刷机目录生成”文件夹里，与本工具同级）：CAT1 脚本大小无法检查"); return; }
            if (!File.Exists(Path.Combine(sourceDir, "main.lua"))) { rep.Error("CAT1 源码目录里没有 main.lua：" + sourceDir); return; }
            // a source whose PRODUCT_VERSION equals OTA_TRIAL_TARGET is the target version for an upgrade package, not a receiver
            string mainText = File.ReadAllText(Path.Combine(sourceDir, "main.lua"), Utf8);
            var pv = Regex.Match(mainText, @"(?m)^PRODUCT_VERSION\s*=\s*""([0-9.]+)"""); var tg = Regex.Match(mainText, @"(?m)^OTA_TRIAL_TARGET\s*=\s*'([0-9.]+)'");
            bool pkg = pv.Success && tg.Success && pv.Groups[1].Value == tg.Groups[1].Value;
            if (pkg) rep.Log("  这份源码是升级包的目标版本 " + pv.Groups[1].Value + "（PRODUCT_VERSION = OTA_TRIAL_TARGET），按升级包源码检查");
            var psi = new ProcessStartInfo(exe, "--source \"" + sourceDir.TrimEnd('\\') + "\" --out \"" + Path.Combine(Path.GetTempPath(), "yp_ver_check") + "\" --check-only" + (pkg ? " --package-source" : ""))
            { UseShellExecute = false, RedirectStandardOutput = true, CreateNoWindow = true, StandardOutputEncoding = Utf8 };
            string output;
            using (var p = Process.Start(psi)) { output = p.StandardOutput.ReadToEnd(); p.WaitForExit(60000); }
            var m = Regex.Match(output, @"LuaDB\s+(\d+)/(\d+)\s*字节，余\s*(-?\d+)");
            if (!m.Success) { rep.Error("CAT1 检查没有给出脚本大小，输出如下：\r\n" + output.Trim()); return; }
            int used = int.Parse(m.Groups[1].Value), left = int.Parse(m.Groups[3].Value);
            if (used > LuaDb) rep.Error("CAT1 脚本共 " + used + " 字节，超过上限 " + LuaDb + " 字节 " + (used - LuaDb) + " 字节：要删减脚本");
            else if (left < 2048) rep.Warn("CAT1 脚本 " + used + " 字节，上限 " + LuaDb + "，余 " + left + " 字节：余量很小，下一版很容易超");
            else rep.Good("CAT1 脚本 " + used + " 字节，上限 " + LuaDb + "，余 " + left + " 字节");
            // SAM | 2026-11-04 +08:00 | OTA red line (budget.json), in case the CAT1 tool next to this one is older.
            string clv = Yp001.Budget.Level(used, Yp001.Budget.LuaDbYellow, Yp001.Budget.LuaDbRed);
            string cline = "CAT1 脚本红线 " + Yp001.Budget.LuaDbRed + "，离红线 " + (Yp001.Budget.LuaDbRed - used);
            if (clv == "red") rep.Error("超过" + cline + "：要删减脚本"); else if (clv == "yellow") rep.Warn("接近" + cline); else rep.Good(cline);
            foreach (string line in output.Split('\n').Select(x => x.TrimEnd()).Where(x => x.StartsWith("  ERROR"))) rep.Error(line.Substring(8).Trim());
        }

        // ---- device free space ---------------------------------------------------------------------------------------------------------
        public class Fs { public long Total, Used, Block, OtaState = -1; public long Free { get { return (Total - Used) * Block; } } public long Capacity { get { return Total * Block; } } }

        public static Fs ParseFs(string text)
        {
            var m = Regex.Match(text ?? "", @"OTA_FS\s+total=(\d+)\s+used=(\d+)\s+block=(\d+)");
            if (!m.Success) return null;
            var fs = new Fs { Total = long.Parse(m.Groups[1].Value), Used = long.Parse(m.Groups[2].Value), Block = long.Parse(m.Groups[3].Value) };
            // SAM | 2026-11-04 +08:00 | OTA state record (two copies) grows ~170 B per release; keep the larger copy from the listing.
            foreach (Match f in Regex.Matches(text, @"F\s+yp001_ota_state_[01]\s+(\d+)")) fs.OtaState = Math.Max(fs.OtaState, long.Parse(f.Groups[1].Value));
            return fs;
        }

        public static string[] Ports() { var p = SerialPort.GetPortNames(); Array.Sort(p, (a, b) => { int x = Num(a), y = Num(b); return x != y ? x.CompareTo(y) : string.CompareOrdinal(a, b); }); return p; }
        static int Num(string s) { var m = Regex.Match(s, @"\d+"); return m.Success ? int.Parse(m.Value) : 0; }

        // SAM | 2026-10-30 18:18 +08:00 | Sends one command to the GR CLI (115200 8N1, CRLF) and collects the answer until `done` is satisfied (then a short grace), or the time is up.
        static string Query(string port, string command, Func<string, bool> done, int seconds, Report rep, Action pump)
        {
            if (string.IsNullOrEmpty(port)) { rep.Error("请选择 COM 口"); return null; }
            var sb = new StringBuilder();
            try
            {
                using (var sp = new SerialPort(port, 115200, Parity.None, 8, StopBits.One) { ReadTimeout = 100, WriteTimeout = 1000, NewLine = "\r\n", Encoding = Encoding.UTF8 })
                {
                    sp.Open(); System.Threading.Thread.Sleep(300); sp.DiscardInBuffer();
                    sp.Write(command + "\r\n");
                    var end = DateTime.UtcNow.AddSeconds(seconds); DateTime? got = null;
                    while (DateTime.UtcNow < end)
                    {
                        try { sb.Append(sp.ReadExisting()); } catch (TimeoutException) { }
                        if (pump != null) pump();
                        System.Threading.Thread.Sleep(50);
                        if (got == null && done(sb.ToString())) got = DateTime.UtcNow;
                        if (got != null && (DateTime.UtcNow - got.Value).TotalSeconds > 1.0) break;   // let the rest of the answer arrive, then stop
                    }
                }
            }
            catch (UnauthorizedAccessException) { rep.Error(port + " 被别的程序占用（串口助手、Keil、监控脚本？），关掉它再读"); return null; }
            catch (Exception ex) { rep.Error("打不开 " + port + "：" + ex.Message); return null; }
            return sb.ToString();
        }

        // Read-only: asks the CAT1 for its file-system usage (cat_at OTA_FS).
        public static Fs ReadDevice(string port, Report rep, Action pump)
        {
            string text = Query(port, "cat_at OTA_FS", t => ParseFs(t) != null, 15, rep, pump);
            if (text == null) return null;
            var fs = ParseFs(text);
            if (fs == null) rep.Error("15 秒内没有收到 OTA_FS 回答。检查：COM 口选对没有（GR 命令行口）、板子上电、CAT1 已启动（开机后要等一会儿）、波特率 115200");
            return fs;
        }

        // Writes device files: cat_at OTA_PRUNE archives the OTA history to the VUART log and deletes the history keys. The OTA state is kept in two copies and
        // each run rewrites one, so it is run twice (as in the board-verified procedure). Returns the free space read afterwards.
        public static Fs Prune(string port, Report rep, Action pump)
        {
            for (int n = 1; n <= 2; n++)
            {
                string text = Query(port, "cat_at OTA_PRUNE", t => Regex.IsMatch(t, @"OTA_PRUNE=(DONE|REFUSED|\w+)"), 20, rep, pump);
                if (text == null) return null;
                var m = Regex.Match(text, @"OTA_PRUNE=(\w+)\s*(\d*)");
                if (!m.Success) { rep.Error("第 " + n + " 次清理没有收到回答（OTA_PRUNE=…）：设备可能正忙，稍后再试"); return null; }
                if (m.Groups[1].Value != "DONE") { rep.Error("第 " + n + " 次清理被设备拒绝：OTA_PRUNE=" + m.Groups[1].Value); return null; }
                rep.Good("第 " + n + " 次清理完成：OTA_PRUNE=DONE " + m.Groups[2].Value + (m.Groups[2].Value.Length > 0 ? "（本次归档/删除的字节数）" : ""));
            }
            return ReadDevice(port, rep, pump);
        }

        // SAM | 2026-11-04 +08:00 | Red line (budget.json, same as the OTA packager and the one-click tool): signed image + 16 KiB reserve +
        // 16 KiB growth margin. The old rule added the 904-byte signature again to an already signed image.
        public static long GrNeed(long signedImageBytes) { return Yp001.Budget.OtaNeed((int)signedImageBytes); }

        public static void ShowFs(Fs fs, long grImageBytes, Report rep)
        {
            rep.Good("OTA_FS total=" + fs.Total + " used=" + fs.Used + " block=" + fs.Block);
            rep.Good("CAT1 可用空间 = (" + fs.Total + " − " + fs.Used + ") × " + fs.Block + " = " + fs.Free + " 字节   ← 填到 3 号工具的“CAT1 可用空间”");
            rep.Log("  文件区总容量 " + fs.Capacity + " 字节，已用 " + fs.Used * fs.Block + " 字节");
            long worst = GrNeed(Yp001.Budget.GrSignedRed);
            long need = grImageBytes > 0 ? GrNeed(grImageBytes) : worst;
            string what = (grImageBytes > 0 ? "GR 签名镜像 " + grImageBytes : "按 GR 红线 " + Yp001.Budget.GrSignedRed) + " + 保留 " + Yp001.Budget.Reserve + " + 余量 " + Yp001.Budget.Margin + " = " + need;
            if (fs.Free >= need) rep.Good("够用：" + what + " 字节，余 " + (fs.Free - need) + " 字节");
            else if (grImageBytes > 0) rep.Error("不够：" + what + " 字节，设备只有 " + fs.Free + " 字节，差 " + (need - fs.Free) + " 字节。先点“清理 OTA 历史”，还不够就要清理设备文件或减小固件，不能改数字");
            else rep.Warn("低于 " + worst + " 字节（" + what + "）：选上 GR 固件再看实际够不够；不够时点“清理 OTA 历史”");
            if (fs.Capacity - fs.Free > Yp001.Budget.ResidentMax)
                rep.Warn("已用 " + (fs.Capacity - fs.Free) + " 字节（含日志），超过常驻数据预算 " + Yp001.Budget.ResidentMax + "：查是什么数据在增长");
            if (fs.OtaState >= 0)
            {
                string s = "OTA 状态记录 " + fs.OtaState + " 字节（存两份，每次升级约 +170 字节）";
                if (fs.OtaState > Yp001.Budget.OtaStateYellow) rep.Warn(s + "，超过 " + Yp001.Budget.OtaStateYellow + "：多次升级在累积，OTA_PRUNE 清不掉这部分，要刷带清理块的接收端或等自动清理版本");
                else rep.Good(s);
            }
            rep.Log("  余量里已含 OTA 过程中状态文件的增长（" + Yp001.Budget.Margin + "）；发令时设备会先删 app 日志，OTA 中不写日志。红线说明：" + Yp001.Budget.Source);
        }
    }

    class MainWindow : Form
    {
        readonly TextBox header = new TextBox(), lua = new TextBox(), ver = new TextBox(), build = new TextBox(), grFile = new TextBox(), catDir = new TextBox();
        readonly ComboBox port = new ComboBox { DropDownStyle = ComboBoxStyle.DropDown };
        readonly RichTextBox log = new RichTextBox();

        public MainWindow()
        {
            Text = "YP001 固件版本与空间工具 v" + Core.ToolVersion; Width = 1060; Height = 760; Font = new Font("Microsoft YaHei UI", 9);
            int y = 8;
            Controls.Add(new Label { Text = "改两个固件的版本（改完你手动编译）；检查两个固件的空间；读设备 CAT1 可用空间", Left = 12, Top = y, Width = 1020, ForeColor = Color.DimGray }); y += 28;
            Section("一、改版本", ref y);
            Row("GR 版本头文件 (yp001_fw_version.h)", header, ref y, "file:头文件|yp001_fw_version.h;*.h");
            Row("CAT1 main.lua", lua, ref y, "file:main.lua|main.lua");
            Row("新版本（如 1.5.3）", ver, ref y, null);
            Row("构建号（留空 = 自动）", build, ref y, null);
            Hint("留空时：版本升高就在当前构建号上加 1，版本不变就保持原构建号。不允许版本倒退，两个固件一起改成同一个版本和构建号。", ref y);
            Buttons(ref y, new[] { "读取当前版本", "修改两个固件的版本" }, new Action[] { ShowCurrent, ApplyVersion });
            Section("二、检查空间", ref y);
            Row("GR 固件（编译出的 .hex / .bin）", grFile, ref y, "file:固件|*.hex;*.bin");
            Row("CAT1 源码目录（含 main.lua）", catDir, ref y, "folder");
            Buttons(ref y, new[] { "检查两个固件的空间" }, new Action[] { CheckSizes });
            Section("三、读设备 CAT1 可用空间（只读，发一次 cat_at OTA_FS）", ref y);
            Controls.Add(new Label { Text = "COM 口（GR 命令行口，会变）", Left = 24, Top = y + 4, Width = 270 });
            port.SetBounds(300, y, 160, 24); Controls.Add(port); FillPorts();
            var refresh = new Button { Text = "刷新", Left = 470, Top = y - 1, Width = 70 }; refresh.Click += (s, e) => FillPorts(); Controls.Add(refresh);
            var read = new Button { Text = "读取设备可用空间", Left = 550, Top = y - 1, Width = 160 }; read.Click += (s, e) => Run(ReadFs); Controls.Add(read);
            var prune = new Button { Text = "清理 OTA 历史", Left = 720, Top = y - 1, Width = 130 }; prune.Click += (s, e) => Run(PruneFs); Controls.Add(prune); y += 34;
            Hint("板子上电、CAT1 已启动、COM 口没被别的程序占用。读到的“可用空间”直接填到 3 号工具；选了上面的 GR 固件，会同时判断够不够（需要 = GR 镜像 + 904 + 16384）。不够时点“清理 OTA 历史”：会向设备写文件，先弹窗确认。", ref y);
            log.Multiline = true; log.ScrollBars = RichTextBoxScrollBars.Both; log.WordWrap = false; log.ReadOnly = true; log.Font = new Font("Consolas", 9);
            log.SetBounds(12, y, 1030, 720 - y); log.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right; Controls.Add(log);
            int wanted = Height; StartPosition = FormStartPosition.CenterScreen;
            Height = Math.Min(wanted, Screen.PrimaryScreen.WorkingArea.Height - 20);
            AutoScroll = true; AutoScrollMinSize = new Size(Width - 40, wanted - 50);
            catDir.Leave += (s, e) => { };
            lua.TextChanged += (s, e) => { if (catDir.Text.Trim().Length == 0 && File.Exists(lua.Text.Trim())) catDir.Text = Path.GetDirectoryName(lua.Text.Trim()); };
        }

        void Section(string t, ref int y) { Controls.Add(new Label { Text = t, Left = 12, Top = y + 2, Width = 1000, Font = new Font("Microsoft YaHei UI", 9, FontStyle.Bold) }); y += 26; }
        void Hint(string t, ref int y)
        {
            var l = new Label { Text = t, Left = 300, Top = y - 2, AutoSize = true, MaximumSize = new Size(700, 0), ForeColor = Color.DimGray };
            Controls.Add(l); y += l.GetPreferredSize(new Size(700, 0)).Height + 8;
        }
        void Buttons(ref int y, string[] names, Action[] acts)
        {
            for (int i = 0; i < names.Length; i++) { var a = acts[i]; var b = new Button { Text = names[i], Left = 300 + i * 180, Top = y, Width = 170 }; b.Click += (s, e) => Run(a); Controls.Add(b); }
            y += 38;
        }
        // SAM | 2026-11-04 +08:00 | The bench GR port moves (COM26 -> COM30): prefer the port of the last successful read (last_port.txt).
        static readonly string LastPortFile = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "last_port.txt");
        static string LastPort() { try { return File.Exists(LastPortFile) ? File.ReadAllText(LastPortFile).Trim() : ""; } catch { return ""; } }
        static void SaveLastPort(string p) { try { File.WriteAllText(LastPortFile, p); } catch { } }
        void FillPorts()
        {
            string keep = port.Text, last = LastPort(); port.Items.Clear(); port.Items.AddRange(Core.Ports());
            port.Text = keep.Length > 0 ? keep : port.Items.Contains(last) ? last : (port.Items.Count > 0 ? (port.Items.Contains("COM26") ? "COM26" : (string)port.Items[0]) : "");
        }

        void Row(string label, TextBox box, ref int y, string pick)
        {
            Controls.Add(new Label { Text = label, Left = 24, Top = y + 4, Width = 270 });
            box.SetBounds(300, y, pick == null ? 280 : 590, 24); Controls.Add(box);
            if (pick != null)
            {
                var b = new Button { Text = "选择…", Left = 900, Top = y - 1, Width = 90 };
                b.Click += (s, e) =>
                {
                    if (pick == "folder") { using (var d = new FolderBrowserDialog { SelectedPath = box.Text }) if (d.ShowDialog() == DialogResult.OK) box.Text = d.SelectedPath; }
                    else { var p = pick.Substring(5).Split('|'); using (var d = new OpenFileDialog { Filter = p[0] + "|" + p[1] + "|所有文件|*.*" }) if (d.ShowDialog() == DialogResult.OK) box.Text = d.FileName; }
                };
                Controls.Add(b);
            }
            y += 32;
        }

        static string N(TextBox t) { string s = t.Text.Trim(); return s.Length == 0 ? null : s; }

        void Put(string color, string text)
        {
            log.SelectionStart = log.TextLength; log.SelectionLength = 0;
            log.SelectionColor = color == "green" ? Color.FromArgb(0, 128, 0) : color == "red" ? Color.Red : color == "orange" ? Color.FromArgb(200, 110, 0) : log.ForeColor;
            log.AppendText(text + "\r\n"); log.SelectionColor = log.ForeColor; Application.DoEvents();
        }

        void Run(Action a)
        {
            log.Clear();
            try { a(); } catch (Exception ex) { Put("red", "异常：" + ex.Message); }
        }

        void ShowCurrent() { var rep = new Report(Put); rep.Log("[当前版本]"); Core.Show(N(header), N(lua), rep); if (N(header) == null && N(lua) == null) rep.Error("请先选择版本头文件或 main.lua"); }

        void ApplyVersion()
        {
            var rep = new Report(Put); int? b = null;
            if (N(build) != null) { int v; if (!int.TryParse(N(build), out v)) { rep.Error("构建号要填数字，或留空自动"); return; } b = v; }
            if (N(ver) == null) { rep.Error("请填新版本（如 1.5.3）"); return; }
            if (MessageBox.Show(this, "要把 GR 和 CAT1 的版本都改成 " + N(ver) + (b.HasValue ? "（构建号 " + b + "）" : "（构建号自动）") + " 吗？" + "\r\n" + "改前的文件会自动备份。", "修改版本", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
            { rep.Log("已取消，没有修改"); return; }
            rep.Log("[修改版本]"); Core.Apply(N(header), N(lua), N(ver), b, rep); Core.Show(N(header), N(lua), rep);
        }

        Core.GrInfo gr;
        void CheckSizes()
        {
            var rep = new Report(Put); bool any = false; gr = null;
            if (N(grFile) != null)
            {
                any = true; rep.Log("[GR 固件大小与版本]");
                string expect = null;
                if (N(header) != null && File.Exists(N(header))) { var q = new Report((c, t) => { }); var id = Core.ReadHeader(N(header), q); if (id != null) expect = id.Canon; }
                gr = Core.CheckGr(N(grFile), expect, rep);
            }
            if (N(catDir) != null) { any = true; rep.Log("[CAT1 脚本大小]"); Core.CheckCat(N(catDir), rep); }
            if (!any) rep.Error("请选择 GR 固件文件，或 CAT1 源码目录");
            else rep.Log(rep.Summary());
        }

        void PruneFs()
        {
            var rep = new Report(Put);
            if (MessageBox.Show(this, "要清理设备上的 OTA 历史日志吗？" + "\r\n" + "\r\n" + "做法：向 " + port.Text + " 发两次 cat_at OTA_PRUNE（先把历史归档到 VUART 日志，再删掉历史键，只动 OTA 自己的历史，不动业务数据和固件），然后重新读可用空间。" + "\r\n" + "这是写设备文件的操作；OTA 正在升级的最后阶段（GR 试运行的 120 秒内）不要做。",
                "清理 OTA 历史", MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes) { rep.Log("已取消，没有清理"); return; }
            long img = GrImageBytes();
            rep.Log("[清理 OTA 历史] " + port.Text + "：cat_at OTA_PRUNE × 2，然后读可用空间…");
            var fs = Core.Prune(port.Text.Trim(), rep, () => Application.DoEvents());
            if (fs != null) Core.ShowFs(fs, img, rep);
            rep.Log(rep.Summary());
        }

        long GrImageBytes()
        {
            if (N(grFile) == null) return 0;
            var q = new Report((c, t) => { }); var gi = Core.CheckGr(N(grFile), null, q);
            return gi == null ? 0 : gi.Payload + Core.SigBytes;     // the signed size, whether the file is the built HEX or the signed BIN
        }

        void ReadFs()
        {
            var rep = new Report(Put);
            long img = GrImageBytes();
            rep.Log("[读取设备 CAT1 可用空间] " + port.Text + " 115200，发送 cat_at OTA_FS（只读），最多等 15 秒…");
            var fs = Core.ReadDevice(port.Text.Trim(), rep, () => Application.DoEvents());
            if (fs != null) { Core.ShowFs(fs, img, rep); SaveLastPort(port.Text.Trim()); }
            rep.Log(rep.Summary());
        }
    }

    static class Program
    {
        [System.Runtime.InteropServices.DllImport("kernel32.dll")] static extern bool FreeConsole();
        static string Opt(List<string> a, string name) { int i = a.IndexOf(name); if (i < 0 || i + 1 >= a.Count) return null; string v = a[i + 1]; a.RemoveRange(i, 2); return v; }
        static string Full(string p) { return p == null ? null : Path.GetFullPath(p); }

        [STAThread]
        static int Main(string[] argv)
        {
            if (argv.Length == 0) { FreeConsole(); Application.EnableVisualStyles(); Application.Run(new MainWindow()); return 0; }
            if (argv.Length == 2 && argv[0] == "--snapshot")
            {
                FreeConsole(); Application.EnableVisualStyles();
                using (var f = new MainWindow()) { f.Show(); Application.DoEvents(); using (var bmp = new Bitmap(f.Width, f.Height)) { f.DrawToBitmap(bmp, new Rectangle(0, 0, f.Width, f.Height)); bmp.Save(argv[1]); } }
                return 0;
            }
            Console.OutputEncoding = Encoding.UTF8;
            var rep = new Report((c, t) => Console.WriteLine(t));
            const string usage = "用法：\r\n" +
                "  YpVersionTool.exe show  --header <yp001_fw_version.h> --lua <main.lua>\r\n" +
                "  YpVersionTool.exe set   --header <yp001_fw_version.h> --lua <main.lua> --version 1.5.3 [--build 7]\r\n" +
                "  YpVersionTool.exe check [--gr <固件.hex|bin>] [--cat1 <CAT1源码目录>] [--header <yp001_fw_version.h>]\r\n" +
                "  YpVersionTool.exe fs    --port COMx  [--gr <固件.hex|bin>]      读设备 CAT1 可用空间（只读）\r\n" +
                "  YpVersionTool.exe prune --port COMx --yes [--gr <固件.hex|bin>]  清理 OTA 历史（向设备发两次 cat_at OTA_PRUNE，会写设备文件，必须带 --yes）\r\n" +
                "  YpVersionTool.exe --ports | --version";
            try
            {
                var a = argv.ToList(); string cmd = a[0]; a.RemoveAt(0);
                if (cmd == "--version") { Console.WriteLine("YpVersionTool v" + Core.ToolVersion); return 0; }
                if (cmd == "--ports") { Console.WriteLine(string.Join(" ", Core.Ports())); return 0; }
                string header = Full(Opt(a, "--header")), lua = Full(Opt(a, "--lua")), ver = Opt(a, "--version"), b = Opt(a, "--build"), gr = Full(Opt(a, "--gr")), cat = Full(Opt(a, "--cat1")), port = Opt(a, "--port"), text = Opt(a, "--parse-text"); bool yes = a.Remove("--yes");
                if (a.Count != 0) { Console.WriteLine("不认识的参数：" + string.Join(" ", a) + "\r\n" + usage); return 2; }
                int bn = 0; if (b != null && !int.TryParse(b, out bn)) { Console.WriteLine("--build 要填数字"); return 2; }
                if (cmd == "show") { if (header == null && lua == null) { Console.WriteLine(usage); return 2; } Core.Show(header, lua, rep); }
                else if (cmd == "set") { if (header == null || lua == null || ver == null) { Console.WriteLine(usage); return 2; } Core.Apply(header, lua, ver, b == null ? (int?)null : bn, rep); }
                else if (cmd == "check")
                {
                    if (gr == null && cat == null) { Console.WriteLine(usage); return 2; }
                    string expect = null; if (header != null) { var id = Core.ReadHeader(header, rep); if (id != null) expect = id.Canon; }
                    if (gr != null) { rep.Log("[GR 固件大小与版本]"); Core.CheckGr(gr, expect, rep); }
                    if (cat != null) { rep.Log("[CAT1 脚本大小]"); Core.CheckCat(cat, rep); }
                }
                else if (cmd == "prune")
                {
                    if (!yes) { Console.WriteLine("清理会向设备写文件，必须明确带 --yes 确认。" + "\r\n" + usage); return 2; }
                    long img = 0; if (gr != null) { var gi = Core.CheckGr(gr, null, new Report((c, t) => { })); if (gi != null) img = gi.Payload + Core.SigBytes; }
                    var fs = Core.Prune(port, rep, null);
                    if (fs != null) Core.ShowFs(fs, img, rep);
                }
                else if (cmd == "fs")
                {
                    long img = 0; if (gr != null) { var gi = Core.CheckGr(gr, null, new Report((c, t) => { })); if (gi != null) img = gi.Payload + Core.SigBytes; }
                    Core.Fs fs = text != null ? Core.ParseFs(text) : Core.ReadDevice(port, rep, null);
                    if (fs == null && text != null) rep.Error("文本里没有 OTA_FS total= used= block=");
                    if (fs != null) Core.ShowFs(fs, img, rep);
                }
                else { Console.WriteLine(usage); return 2; }
            }
            catch (Exception ex) { rep.Error("异常：" + ex.Message); }
            Console.WriteLine(rep.Summary());
            return rep.Errors.Count > 0 ? 1 : 0;
        }
    }
}
