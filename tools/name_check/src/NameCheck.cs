// SAM | 2026-11-04 +08:00 | YP001 resident-name file check (toolkit tool 5): checks a platform residentNameMsg JSON against the
// confirmed framework (Name / Room / Campus all from the platform, nothing kept at the factory; every non-ASCII Name character
// 32+16px, every Campus character 16px; Room only built-in 28px characters; Seq = generation time; GR record <= 4000 B) and writes
// a plain explanation of the file (Markdown) next to it. Same rules as tools/glyph_maker/check_platform_json.py.
// Window: pick a file. Command line: NameCheck.exe <file.json> [--seq-min N] [--md <out.md>]  (exit 0 = can be pushed, 1 = not)
using System;
using System.Collections;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace YpNameCheck
{
    class Result
    {
        public List<string> Ok = new List<string>(), Warn = new List<string>(), Err = new List<string>();
        public string Md = "";
    }

    static class Checker
    {
        public const string Version = "1.0";
        const int ShownName = 5, MaxCampus = 11, MaxGlyphs = 28, MaxGlyphBytes = 200, StoreMax = 4000, StoreHeader = 20, PerGlyph = 16;
        const long SeqMin = 1767225600;     // 2026-01-01 00:00 +08:00
        const string RoomCjk = "号楼栋单元层室";   // the built-in 28px font of the room label (no room glyphs are pushed)

        static bool Cjk(int cp) { return cp >= 0x80; }
        static List<int> Cps(string s)
        {
            var o = new List<int>();
            for (int i = 0; i < s.Length; i++) { int c = char.ConvertToUtf32(s, i); if (char.IsHighSurrogate(s[i])) i++; o.Add(c); }
            return o;
        }
        static string Ch(int cp) { return char.ConvertFromUtf32(cp); }
        static string Shown(string name)
        {
            var sb = new StringBuilder(); int n = 0;
            foreach (int c in Cps(name)) { if (Cjk(c)) { if (n == ShownName) break; n++; } sb.Append(Ch(c)); }
            return sb.ToString().TrimEnd();
        }
        public static ushort Crc16(byte[] d, ushort crc)
        {
            foreach (byte b in d) { crc ^= (ushort)(b << 8); for (int i = 0; i < 8; i++) crc = (ushort)((crc & 0x8000) != 0 ? (crc << 1) ^ 0x1021 : crc << 1); }
            return crc;
        }
        static long? Num(object o) { if (o is int) return (int)o; if (o is long) return (long)o; if (o is decimal) { decimal d = (decimal)o; if (d == Math.Floor(d)) return (long)d; } return null; }
        static string Str(object o) { return o as string; }
        static string Time(long s) { return DateTimeOffset.FromUnixTimeSeconds(s).ToOffset(TimeSpan.FromHours(8)).ToString("yyyy-MM-dd HH:mm:ss"); }

        public static Result Check(string path, long? seqMin)
        {
            var r = new Result();
            Dictionary<string, object> m;
            string text;
            try { text = File.ReadAllText(path, new UTF8Encoding(false, true)); m = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(text); }
            catch (Exception e) { r.Err.Add("不是 UTF-8 JSON：" + e.Message); r.Md = "# " + Path.GetFileName(path) + "\n\n不是 UTF-8 JSON，无法核对。\n"; return r; }
            var md = new StringBuilder();
            md.Append("# " + Path.GetFileName(path) + " 核对与逐段说明\n\n");
            md.Append("NameCheck v" + Version + " | " + DateTime.Now.ToString("yyyy-MM-dd HH:mm") + " | 规则：姓名、房号、园区全部由后台下发，出厂本地不留\n\n");

            string[] head = { "MsgType", "Seq", "Name", "Room", "Campus", "FontId", "FontVer", "Glyphs" };
            foreach (var k in head) if (!m.ContainsKey(k)) r.Err.Add("缺字段 " + k);
            foreach (var k in m.Keys) if (!head.Contains(k)) r.Warn.Add("多余字段 " + k + "（设备忽略）");
            if (Str(m.ContainsKey("MsgType") ? m["MsgType"] : null) != "residentNameMsg") r.Err.Add("MsgType 必须是 residentNameMsg");
            string name = Str(m.ContainsKey("Name") ? m["Name"] : null) ?? "", room = Str(m.ContainsKey("Room") ? m["Room"] : null) ?? "",
                   campus = Str(m.ContainsKey("Campus") ? m["Campus"] : null) ?? "";
            if (name.Length == 0 || Encoding.UTF8.GetByteCount(name) > 63) r.Err.Add("Name 为空或超过 63 字节");
            int nameCjk = Cps(name).Count(Cjk);
            if (nameCjk > ShownName) r.Err.Add("Name 有 " + nameCjk + " 个非英文字，超过 " + ShownName + " 个（生成工具应截断）");
            var campusSet = Cps(campus).Where(Cjk).Distinct().ToList();
            if (campusSet.Count > MaxCampus) r.Err.Add("Campus 非英文字超过 " + MaxCampus + " 个");
            var roomBad = Cps(room).Where(c => Cjk(c) && RoomCjk.IndexOf(Ch(c), StringComparison.Ordinal) < 0).Distinct().Select(Ch).ToList();
            if (roomBad.Count > 0) r.Err.Add("Room 里有设备显示不了的字（屏幕显示 --，推送也补不了）：" + string.Concat(roomBad));

            // 1. timestamp
            long? seq = Num(m.ContainsKey("Seq") ? m["Seq"] : null);
            md.Append("## 一、时间戳\n\n时间戳是 **`Seq`** 字段：生成文件时的当前时间（Unix 秒）。设备只收比上一次更大的 `Seq`。\n\n");
            if (seq == null || seq <= 0 || seq > 0xFFFFFFFFL) { r.Err.Add("Seq 必须是正整数（32 位内）"); md.Append("本文件：`Seq` 无效。\n\n"); }
            else
            {
                md.Append("本文件：`" + seq + "` = " + Time(seq.Value) + "。");
                if (seq < SeqMin) { r.Err.Add("Seq " + seq + " 是 " + Time(seq.Value).Substring(0, 10) + " 的时间，早于 2026-01-01，收过新 Seq 的设备会拒收；后台应取生成时的当前时间"); md.Append(" **错误：太早，应为生成时的当前时间。**"); }
                else if (seq > DateTimeOffset.UtcNow.ToUnixTimeSeconds() + 86400) { r.Err.Add("Seq 是将来的时间"); md.Append(" **错误：是将来的时间。**"); }
                else r.Ok.Add("Seq " + seq + "（" + Time(seq.Value) + "）");
                if (seqMin.HasValue && seq <= seqMin) r.Err.Add("Seq 不大于设备上一次的 " + seqMin + "：设备会当成旧消息拒收");
                md.Append("\n\n");
            }

            // 2. top-level fields
            md.Append("## 二、顶层字段\n\n| 字段 | 本文件的值 | 含义 |\n|---|---|---|\n");
            var meaning = new Dictionary<string, string> {
                { "MsgType", "固定值，表示姓名字库下发" }, { "Seq", "时间戳（秒），见上" }, { "Name", "姓名，最多显示 5 个字" },
                { "Room", "房号，只推文字，用设备自带 28px 字库显示（数字、字母和 号楼栋单元层室）" }, { "Campus", "园区名，最多 11 个字" },
                { "FontId", "字体名，记录用" }, { "FontVer", "格式版本，记录用" }, { "Glyphs", "字形列表，见下" } };
            foreach (var k in head)
            {
                object v = m.ContainsKey(k) ? m[k] : null;
                string shown = v == null ? "（缺）" : k == "Glyphs" ? ((v as ArrayList) == null ? "（不是数组）" : ((ArrayList)v).Count + " 项") : "`" + v + "`";
                md.Append("| `" + k + "` | " + shown + " | " + meaning[k] + " |\n");
            }

            // 3. glyphs
            var list = m.ContainsKey("Glyphs") ? m["Glyphs"] as ArrayList : null;
            if (list == null) { r.Err.Add("Glyphs 必须是数组"); list = new ArrayList(); }
            if (list.Count > MaxGlyphs) r.Err.Add("字形 " + list.Count + " 个，超过 " + MaxGlyphs);
            var seen = new HashSet<string>(); int store = StoreHeader, bad = 0;
            var bySize = new SortedDictionary<int, List<string>>();
            for (int i = 0; i < list.Count; i++)
            {
                var g = list[i] as Dictionary<string, object>;
                string tag = "#" + i;
                if (g == null) { r.Err.Add(tag + " 不是对象"); bad++; continue; }
                try
                {
                    string us = (string)g["U"]; int u = Convert.ToInt32(us, 16);
                    long s = Num(g["S"]).Value, w = Num(g["W"]).Value, h = Num(g["H"]).Value, x = Num(g["X"]).Value, y = Num(g["Y"]).Value, a = Num(g["A"]).Value;
                    byte[] d = Convert.FromBase64String((string)g["D"]); string c = (string)g["C"];
                    tag = "#" + i + " " + Ch(u) + "/" + s + "px";
                    if (c == null || c.Length != 4 || c.Any(ch => !"0123456789ABCDEF".Contains(ch))) r.Err.Add(tag + " C 必须是 4 位大写十六进制");
                    if (s != 16 && s != 32) r.Err.Add(tag + " S 只能是 16 或 32");
                    if (w < 1 || w > 40 || h < 1 || h > 40) r.Err.Add(tag + " W/H 超出 1..40");
                    if (Math.Abs(x) > 40 || Math.Abs(y) > 40) r.Err.Add(tag + " X/Y 超出 ±40");
                    if (a != s * 16) r.Warn.Add(tag + " A=" + a + "，汉字应为 " + s * 16);
                    long want = (w + 7) / 8 * h;
                    if (d.Length != want) r.Err.Add(tag + " 点阵 " + d.Length + " 字节 ≠ ⌈W/8⌉×H = " + want);
                    if (d.Length > MaxGlyphBytes) r.Err.Add(tag + " 点阵超过 " + MaxGlyphBytes + " 字节");
                    byte[] hdr = { (byte)(u >> 16), (byte)(u >> 8), (byte)u, (byte)s, (byte)w, (byte)h, (byte)x, (byte)y, (byte)(a >> 8), (byte)a };
                    ushort crc = Crc16(d, Crc16(hdr, 0xFFFF));
                    if (crc.ToString("X4") != c) { r.Err.Add(tag + " CRC 不对（应为 " + crc.ToString("X4") + "）"); bad++; }
                    if (!seen.Add(u + "/" + s)) r.Err.Add(tag + " 重复");
                    store += PerGlyph + d.Length;
                    if (!bySize.ContainsKey(u)) bySize[u] = new List<string>();
                    bySize[u].Add(s.ToString());
                }
                catch (Exception e) { r.Err.Add(tag + " 字段缺失或格式错：" + e.Message); bad++; }
            }
            if (bad == 0 && list.Count > 0) r.Ok.Add(list.Count + " 个字形格式、点阵长度、CRC 全部正确");

            md.Append("\n## 三、Glyphs 每一项的字段\n\n| 字段 | 含义 |\n|---|---|\n| `U` | 字的 Unicode 码点（十六进制） |\n" +
                "| `S` | 字号：32 主页姓名，16 低电页姓名和园区 |\n| `W` / `H` | 点阵宽、高（像素） |\n| `X` / `Y` | 点阵左边距、底边相对基线的位置 |\n" +
                "| `A` | 前进宽度，= 字号 × 16 |\n| `D` | 点阵数据（base64），每行补齐到整字节 |\n| `C` | CRC-16 校验码，设备收到后重算，不对就拒收 |\n");

            // 4. framework: every Name character 32+16, every Campus character 16
            var need = new HashSet<string>();
            foreach (int c in Cps(Shown(name)).Where(Cjk).Distinct()) { need.Add(c + "/32"); need.Add(c + "/16"); }
            foreach (int c in campusSet) need.Add(c + "/16");
            Func<IEnumerable<string>, string> fmt = ks => string.Join("、", ks.Select(k => { var p = k.Split('/'); return Ch(int.Parse(p[0])) + p[1] + "px"; }));
            var lack = need.Where(k => !seen.Contains(k)).ToList(); var other = seen.Where(k => !need.Contains(k)).ToList();
            if (lack.Count > 0) r.Err.Add("缺少字形（出厂不留字库，会显示方框）：" + fmt(lack));
            if (other.Count > 0) r.Warn.Add("推了 Name/Campus 里没有的字：" + fmt(other));
            if (lack.Count == 0) r.Ok.Add("Name/Campus 需要的 " + need.Count + " 个字形都有（姓名 32+16px，园区 16px）");
            if (store > StoreMax) r.Err.Add("设备存储 " + store + " 字节，超过 " + StoreMax + "：设备放不下，整批拒收");
            else r.Ok.Add("设备存储 " + store + "/" + StoreMax + " 字节（20 + 每字 16 + 点阵）");

            md.Append("\n## 四、本文件的 " + list.Count + " 个字形（" + bySize.Count + " 个字）\n\n| 字 | 码点 | 字号 | 用途 |\n|---|---|---|---|\n");
            var nameOrder = Cps(Shown(name)).Where(Cjk).Distinct().ToList();
            var nameChars = new HashSet<int>(nameOrder);
            // Name characters first, then campus, then anything else, each in text order.
            var order = nameOrder.Concat(Cps(campus).Where(Cjk).Distinct()).Distinct().Where(bySize.ContainsKey)
                .Concat(bySize.Keys.Where(k => !nameChars.Contains(k) && !campusSet.Contains(k))).ToList();
            foreach (int k in order)
                md.Append("| " + Ch(k) + " | " + k.ToString("X4") + " | " + string.Join("、", bySize[k]) + " | " +
                    (nameChars.Contains(k) ? (campusSet.Contains(k) ? "姓名、园区" : "姓名") : campusSet.Contains(k) ? "园区" : "**不在姓名、园区里**") + " |\n");
            md.Append("\n设备存储：" + store + "/" + StoreMax + " 字节。\n");

            md.Append("\n## 五、结论\n\n" + (r.Err.Count == 0 ? "**可以下发**。" : "**不能下发**，要后台改：") + "\n\n");
            foreach (var e in r.Err) md.Append("- 错误：" + e + "\n");
            foreach (var w in r.Warn) md.Append("- 提醒：" + w + "\n");
            foreach (var o in r.Ok) md.Append("- 通过：" + o + "\n");
            r.Md = md.ToString();
            return r;
        }
    }

    class MainWindow : Form
    {
        readonly TextBox file = new TextBox(), seqMin = new TextBox(), log = new TextBox();
        public MainWindow()
        {
            Text = "YP001 姓名字库文件核对 v" + Checker.Version; Width = 900; Height = 620; Font = new Font("Microsoft YaHei UI", 9F);
            var l1 = new Label { Text = "后台文件 (.json)：", Left = 12, Top = 16, Width = 120 };
            file.SetBounds(132, 12, 560, 24);
            var pick = new Button { Text = "选择…", Left = 700, Top = 11, Width = 80 };
            var go = new Button { Text = "核对", Left = 788, Top = 11, Width = 80 };
            var l2 = new Label { Text = "设备上次的 Seq（可选）：", Left = 12, Top = 48, Width = 160 };
            seqMin.SetBounds(172, 44, 160, 24);
            var hint = new Label { Text = "核对结果和逐段说明（Markdown）保存在 JSON 同一个文件夹，文件名后加 _核对.md", Left = 340, Top = 48, Width = 540 };
            log.SetBounds(12, 80, 856, 490); log.Multiline = true; log.ScrollBars = ScrollBars.Vertical; log.ReadOnly = true;
            log.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
            Controls.AddRange(new Control[] { l1, file, pick, go, l2, seqMin, hint, log });
            pick.Click += (s, e) => { using (var d = new OpenFileDialog { Filter = "residentNameMsg (*.json)|*.json" }) if (d.ShowDialog(this) == DialogResult.OK) { file.Text = d.FileName; Run(); } };
            go.Click += (s, e) => Run();
        }
        void Run()
        {
            string f = file.Text.Trim().Trim('"');
            if (!File.Exists(f)) { log.Text = "请先选择后台生成的 residentNameMsg JSON 文件。"; return; }
            long v; long? min = long.TryParse(seqMin.Text.Trim(), out v) ? v : (long?)null;
            var r = Checker.Check(f, min);
            string mdPath = Path.Combine(Path.GetDirectoryName(f), Path.GetFileNameWithoutExtension(f) + "_核对.md");
            File.WriteAllText(mdPath, r.Md, new UTF8Encoding(false));
            log.Text = Program.Summary(r).Replace("\n", "\r\n") + "\r\n逐段说明：" + mdPath;
        }
    }

    static class Program
    {
        public static string Summary(Result r)
        {
            var sb = new StringBuilder();
            foreach (var o in r.Ok) sb.Append("  OK    " + o + "\n");
            foreach (var w in r.Warn) sb.Append("  WARN  " + w + "\n");
            foreach (var e in r.Err) sb.Append("  ERROR " + e + "\n");
            sb.Append("结论：" + (r.Err.Count == 0 ? "可以下发" + (r.Warn.Count > 0 ? "（有提醒）" : "") : "不能下发") + "\n");
            return sb.ToString();
        }
        [STAThread]
        static int Main(string[] args)
        {
            if (args.Length == 0) { Application.EnableVisualStyles(); Application.Run(new MainWindow()); return 0; }
            if (args[0] == "--version") { Console.WriteLine("NameCheck v" + Checker.Version); return 0; }
            string f = args[0], md = null; long? min = null;
            for (int i = 1; i + 1 < args.Length; i++) { if (args[i] == "--seq-min") min = long.Parse(args[++i]); else if (args[i] == "--md") md = args[++i]; }
            if (!File.Exists(f)) { Console.WriteLine("找不到文件：" + f); return 2; }
            var r = Checker.Check(f, min);
            Console.OutputEncoding = new UTF8Encoding(false);
            Console.Write(Summary(r));
            md = md ?? Path.Combine(Path.GetDirectoryName(Path.GetFullPath(f)), Path.GetFileNameWithoutExtension(f) + "_核对.md");
            File.WriteAllText(md, r.Md, new UTF8Encoding(false));
            Console.WriteLine("逐段说明：" + md);
            return r.Err.Count == 0 ? 0 : 1;
        }
    }
}
