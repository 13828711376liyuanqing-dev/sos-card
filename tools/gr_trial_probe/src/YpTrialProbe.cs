// SAM | 2026-11-10 +08:00 | YP001 GR 试运行（Boot TRIAL）卡点只读探针 YpTrialProbe.exe。
// 用同一次编译的 .map 找到 GR 内存里的"120 秒健康计时"和"静默租约"变量，用 J-Link 在 GR 运行中只读采样，判断卡在哪一步。
// 吸取 GR_JLink_Flash_Tool（doc/2026-11-10_GR烧录工具失败复盘_成功证据与后续注意事项.md）的教训：
//  1. 不用自定义设备库/算法：只读 RAM，命令行 -device CORTEX-M4 在连接前就选好；从 J-Link 实际输出核对"选中的设备""识别到的内核""探针编号"，不信请求参数。
//  2. 错误即停：J-Link 报错、文件没生成、长度不对、符号缺失/重名/大小不符，都停止并说清原因，不猜。
//  3. 不停核、不写、不复位：每次读取前后各读一次 DHCSR，确认 S_HALT=0；GR 的 now_ms 在样本之间必须前进，作为"没被停住"的实际证据。
//     运行中读 Flash 曾出现错位（复盘第 8 条），所以 .map 与板上固件是否同一次编译，用 .hex 对比时连读两次，两次不一致就判"无法核对"，不停核重读。
//  4. 中文/空格路径：J-Link 只用记录目录里的相对文件名。
//  5. 每次 J-Link 完整输出都落盘，失败现场可追溯。
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

class Sym { public string Name, Obj; public uint Addr; public int Size; }

class SymSpec
{
    public string Name, Obj; public int[] Sizes; public int MinSize;
    public SymSpec(string n, string o, int min, params int[] sizes) { Name = n; Obj = o; MinSize = min; Sizes = sizes; }
}

static class MapFile
{
    public static readonly SymSpec[] Need = {
        new SymSpec("quiet", "yp001_ota.o", 0, 1080),
        new SymSpec("known", "yp001_ota.o", 0, 1),
        new SymSpec("state", "yp001_ota.o", 0, 344, 348),
        new SymSpec("g_ota_quiet_trace", "yp001_ota.o", 0, 64),
        new SymSpec("g_ota_quiet_first_timeout", "yp001_ota.o", 0, 64),
        new SymSpec("yp001_ota_quiet_denial", "yp001_ota.o", 0, 40),
        new SymSpec("health_check", "yp001_ota_port.o", 12),
        new SymSpec("health_since", "yp001_ota_port.o", 0, 4),
        new SymSpec("health_started", "yp001_ota_port.o", 0, 1),
        new SymSpec("result_check_at", "yp001_ota_port.o", 0, 4),
        new SymSpec("result_check_started", "yp001_ota_port.o", 0, 1),
        new SymSpec("s", "yp001_business.o", 0, 376, 380),
        new SymSpec("ota_battery_seen", "yp001_business.o", 0, 1),
        new SymSpec("ota_battery_ms", "yp001_business.o", 0, 4),
        new SymSpec("ota_keys_seen", "yp001_business.o", 0, 1),
        new SymSpec("ota_keys_ms", "yp001_business.o", 0, 4),
    };

    static readonly Regex Line = new Regex(@"^\s+(\S+)\s+0x([0-9a-fA-F]{8})\s+(Data|Thumb Code)\s+(\d+)\s+([^\s(]+)\(", RegexOptions.Compiled);

    // 返回 null 并给出 err 表示 .map 不合格（错误即停）。
    public static Dictionary<string, Sym> Load(string path, out Sym code, out string err)
    {
        code = null; err = null;
        var found = new Dictionary<string, List<Sym>>();
        var codes = new List<Sym>();
        // SAM | 2026-11-10 +08:00 | v1.0.1: 同事 Keil 的 .map 抬头是 "Arm Compiler for Embedded"（v1.0 只认 6.14 的 "ARM Compiler"，误判）。
        // 改为认 armlink 生成的符号表；真正的门禁仍是下面 16 个变量的对象文件、地址和大小核对，以及 .hex 对比。
        bool keil = false, table = false; string head = null;
        foreach (var l in File.ReadLines(path, Encoding.Default))
        {
            if (head == null && l.Trim().Length > 0) head = l.Trim();
            if (l.IndexOf("armlink", StringComparison.OrdinalIgnoreCase) >= 0 || l.IndexOf("Arm Compiler", StringComparison.OrdinalIgnoreCase) >= 0) keil = true;
            if (l.Contains("Image Symbol Table")) table = true;
            var m = Line.Match(l);
            if (!m.Success) continue;
            var s = new Sym { Name = m.Groups[1].Value, Addr = Convert.ToUInt32(m.Groups[2].Value, 16), Size = int.Parse(m.Groups[4].Value), Obj = m.Groups[5].Value };
            if (m.Groups[3].Value == "Thumb Code") { if (s.Name == "yp001_ota_poll" && s.Obj == "yp001_ota.o") codes.Add(s); continue; }
            var spec = Need.FirstOrDefault(x => x.Name == s.Name && x.Obj == s.Obj);
            if (spec == null) continue;
            List<Sym> list; if (!found.TryGetValue(s.Name, out list)) found[s.Name] = list = new List<Sym>();
            if (!list.Any(x => x.Addr == s.Addr)) list.Add(s);
        }
        if (!keil || !table) { err = "这不是 Keil armlink 生成的带符号表的 .map 文件（文件第一行：" + (head ?? "空") + "）。确认选的是 Listings 目录下的 .map，Keil 的 Linker 选项要勾选输出符号表"; return null; }
        var res = new Dictionary<string, Sym>();
        var miss = new List<string>();
        foreach (var spec in Need)
        {
            List<Sym> list;
            if (!found.TryGetValue(spec.Name, out list)) { miss.Add(spec.Obj + ":" + spec.Name); continue; }
            if (list.Count != 1) { err = ".map 里 " + spec.Obj + " 的 " + spec.Name + " 出现 " + list.Count + " 个不同地址，无法确定，停止"; return null; }
            var s = list[0];
            if (s.Addr < 0x20000000 || s.Addr >= 0x20100000) { err = spec.Name + " 地址 0x" + s.Addr.ToString("X8") + " 不在 GR 内存范围，停止"; return null; }
            if ((spec.Sizes.Length > 0 && !spec.Sizes.Contains(s.Size)) || s.Size < spec.MinSize)
            { err = spec.Name + " 大小是 " + s.Size + " 字节，和本工具认识的固件结构不一致（期望 " + (spec.Sizes.Length > 0 ? string.Join("/", spec.Sizes) : ">=" + spec.MinSize) + "）。固件结构变了，工具需要更新，停止"; return null; }
            res[spec.Name] = s;
        }
        if (miss.Count > 0) { err = ".map 里找不到这些变量：" + string.Join("、", miss) + "。确认选的是本次编译 Listings 目录下的 .map（Keil 的 Linker 选项需要输出符号表）"; return null; }
        if (codes.Count == 1) code = codes[0];
        return res;
    }
}

static class HexFile
{
    // Intel HEX → 地址:字节；只用于对比，不写入任何设备。
    public static Dictionary<uint, byte> Load(string path)
    {
        var d = new Dictionary<uint, byte>();
        uint upper = 0;
        foreach (var raw in File.ReadLines(path))
        {
            var l = raw.Trim();
            if (l.Length < 11 || l[0] != ':') continue;
            int n = Convert.ToInt32(l.Substring(1, 2), 16);
            uint a = Convert.ToUInt32(l.Substring(3, 4), 16);
            int t = Convert.ToInt32(l.Substring(7, 2), 16);
            if (t == 0) for (int i = 0; i < n; i++) d[upper + a + (uint)i] = Convert.ToByte(l.Substring(9 + i * 2, 2), 16);
            else if (t == 4) upper = Convert.ToUInt32(l.Substring(9, 4), 16) << 16;
            else if (t == 2) upper = Convert.ToUInt32(l.Substring(9, 4), 16) << 4;
            else if (t == 1) break;
        }
        return d;
    }
}

class JResult
{
    public bool Ok; public string Error, Output, SerialNo; public bool HaltBefore, HaltAfter;
    public Dictionary<string, byte[]> Bins = new Dictionary<string, byte[]>();
}

static class JLink
{
    public static string Exe()
    {
        foreach (var root in new[] { Environment.GetEnvironmentVariable("ProgramFiles"), Environment.GetEnvironmentVariable("ProgramFiles(x86)"), @"C:\Program Files" })
        {
            if (string.IsNullOrEmpty(root)) continue;
            var seg = Path.Combine(root, "SEGGER");
            if (!Directory.Exists(seg)) continue;
            var direct = Path.Combine(seg, "JLink", "JLink.exe");
            if (File.Exists(direct)) return direct;
            foreach (var d in Directory.GetDirectories(seg, "JLink*").OrderByDescending(x => x))
                if (File.Exists(Path.Combine(d, "JLink.exe"))) return Path.Combine(d, "JLink.exe");
        }
        return null;
    }

    static readonly Regex Dhcsr = new Regex(@"E000EDF0\s*=\s*([0-9A-Fa-f]{8})");

    // reads: 文件名(ASCII) → (地址, 长度)。只发 mem32 / savebin，不发 h / g / r / 写命令。
    public static JResult Read(string exe, string dir, string tag, List<KeyValuePair<string, KeyValuePair<uint, int>>> reads)
    {
        var r = new JResult();
        var sb = new StringBuilder("exec SetRestartOnClose = 0\nmem32 0xE000EDF0,1\n");
        foreach (var x in reads)
        {
            var f = Path.Combine(dir, x.Key); if (File.Exists(f)) File.Delete(f);
            sb.Append("savebin " + x.Key + ",0x" + x.Value.Key.ToString("X8") + ",0x" + x.Value.Value.ToString("X") + "\n");
        }
        sb.Append("mem32 0xE000EDF0,1\nexit\n");
        File.WriteAllText(Path.Combine(dir, tag + ".jlink"), sb.ToString(), Encoding.ASCII);
        var psi = new ProcessStartInfo(exe, "-NoGui 1 -ExitOnError 1 -device CORTEX-M4 -if SWD -speed 4000 -autoconnect 1 -Log " + tag + ".sdk.log -CommandFile " + tag + ".jlink")
        { WorkingDirectory = dir, UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
        using (var p = Process.Start(psi))
        {
            var o = p.StandardOutput.ReadToEndAsync(); var e = p.StandardError.ReadToEndAsync();
            bool exited = p.WaitForExit(60000);
            if (!exited) { try { p.Kill(); } catch { } }
            bool drained = System.Threading.Tasks.Task.WaitAll(new System.Threading.Tasks.Task[] { o, e }, 5000);
            r.Output = drained ? o.Result + e.Result : "(J-Link 输出读取超时)";
            File.WriteAllText(Path.Combine(dir, tag + ".txt"), r.Output, Encoding.UTF8);
            if (!exited || !drained) { r.Error = "J-Link 60 秒没结束，已停止本次读取（见 " + tag + ".txt）"; return r; }
            var outp = r.Output;
            if (outp.Contains("No J-Link") || outp.Contains("Connecting to J-Link via USB...FAILED")) { r.Error = "找不到 J-Link，或被别的程序占着（6 号工具的 J-Link 读取、Keil 调试、J-Flash 都要先关）"; return r; }
            if (outp.Contains("Cannot connect") || outp.Contains("Could not connect") || outp.Contains("Failed to attach")) { r.Error = "J-Link 连不上 GR（查 SWD 线和板子供电）"; return r; }
            // 教训 4：核对实际选中的设备和识别到的内核，不信请求参数。
            if (!outp.Contains("Device \"CORTEX-M4\" selected")) { r.Error = "J-Link 实际没有选中 CORTEX-M4（见 " + tag + ".txt），停止"; return r; }
            if (!outp.Contains("Cortex-M4 identified")) { r.Error = "J-Link 没识别到 Cortex-M4 内核（见 " + tag + ".txt），停止"; return r; }
            if (p.ExitCode != 0) { r.Error = "J-Link 报错退出（退出码 " + p.ExitCode + "，见 " + tag + ".txt）"; return r; }
            var sn = Regex.Match(outp, @"S/N:\s*(\d+)"); r.SerialNo = sn.Success ? sn.Groups[1].Value : "?";
            var dh = Dhcsr.Matches(outp);
            if (dh.Count < 2) { r.Error = "没读到内核运行状态 DHCSR（见 " + tag + ".txt），停止"; return r; }
            r.HaltBefore = (Convert.ToUInt32(dh[0].Groups[1].Value, 16) & 0x20000) != 0;
            r.HaltAfter = (Convert.ToUInt32(dh[dh.Count - 1].Groups[1].Value, 16) & 0x20000) != 0;
            foreach (var x in reads)
            {
                var f = Path.Combine(dir, x.Key);
                if (!File.Exists(f)) { r.Error = "J-Link 没生成 " + x.Key + "（见 " + tag + ".txt），停止"; return r; }
                var b = File.ReadAllBytes(f);
                if (b.Length != x.Value.Value) { r.Error = x.Key + " 长度 " + b.Length + "，应为 " + x.Value.Value + "，停止"; return r; }
                r.Bins[x.Key] = b;
            }
            r.Ok = true;
        }
        return r;
    }
}

class Sample
{
    public DateTime At;
    public uint Now, HealthSince, ResultCheckAt, BattMs, KeysMs, Token, HealthAt, DenialCount, DenialMask;
    public bool HealthStarted, ResultCheckStarted, HcValid, BattSeen, BattKnown, KeysSeen, Alarm, Transport, Known, Granted, Allowed;
    public uint HcState, HcGen; public int Call, Net, Phase, Kind, Battery;
    public uint[] Trace = new uint[16], FirstTimeout = new uint[16];
    public bool TraceStable;
    public int OwnerPhase; public string Target = "", Version = "", Source = "";
    public bool InTrialFlow { get { return Known && OwnerPhase == 3 && Target == "GR5526"; } }
    static readonly string[] PH = { "IDLE", "DOWNLOADING", "PREPARED", "INSTALL_PENDING", "COMPLETE" };
    public string OwnerText { get { return Known ? (OwnerPhase >= 0 && OwnerPhase < PH.Length ? PH[OwnerPhase] : "?" + OwnerPhase) + " 目标 " + (Target.Length > 0 ? Target : "-") + " " + Source + "→" + Version : "未载入"; } }

    public uint ClockNow { get { return KeysSeen && (int)(KeysMs - Now) > 0 ? KeysMs : Now; } }
    public bool BattFresh { get { return BattSeen && (uint)(ClockNow - BattMs) <= 3000u; } }
    public bool CallOk { get { return Call == 0 || Call == 4; } }
    public bool NetOk { get { return Transport && Net == 4; } }
    public double HealthSec { get { return HealthStarted ? (uint)(Now - HealthSince) / 1000.0 : 0; } }

    static readonly string[] CALL = { "空闲", "拨号", "来电", "通话中", "已结束", "失败", "未知" };
    static readonly string[] NET = { "未知", "无卡", "注册中", "有IP", "MQTT", "离线" };
    static readonly string[] BOOT = { "EMPTY", "PREPARED", "INSTALL", "TRIAL", "ROLLBACK", "CONFIRMED", "REVERTED" };
    public static string CallName(int c) { return c >= 0 && c < CALL.Length ? CALL[c] : "?" + c; }
    public static string NetName(int n) { return n >= 0 && n < NET.Length ? NET[n] : "?" + n; }
    public static string BootName(uint b) { return b < BOOT.Length ? BOOT[b] : "?" + b; }

    public static string Flags(uint f)
    {
        var l = new List<string>();
        if ((f & 1) != 0) l.Add("已申请");
        if ((f & 2) != 0) l.Add("收到CAT1回复241");
        if ((f & 4) != 0) l.Add("获准并开始写");
        if ((f & 8) != 0) l.Add("写完");
        if ((f & 16) != 0) l.Add("发结束242");
        if ((f & 32) != 0) l.Add("收到243");
        if ((f & 64) != 0) l.Add("超时");
        return l.Count == 0 ? "无" : string.Join("→", l);
    }
}

class MainForm : Form
{
    TextBox mapBox = new TextBox(), hexBox = new TextBox(), log = new TextBox();
    ComboBox durBox = new ComboBox();
    Button mapBtn = new Button(), hexBtn = new Button(), startBtn = new Button(), stopBtn = new Button(), openBtn = new Button();
    Label status = new Label();
    volatile bool stop;
    Thread worker;
    string runDir;
    // SAM | 2026-11-10 +08:00 | --auto <map> [hex] [--min N]: 台架实测走同一个窗口和 Start()，自动点开始、结束后关闭（不另写测试路径）。
    bool auto; int autoMin;

    public MainForm(string[] args)
    {
        string arg = null;
        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == "--auto") auto = true;
            else if (args[i] == "--min" && i + 1 < args.Length) autoMin = int.Parse(args[++i]);
            else if (arg == null && !args[i].EndsWith(".hex", StringComparison.OrdinalIgnoreCase)) arg = args[i];
            else SetFile(args[i]);
        }
        Text = "YP001 GR 试运行卡点读取（只读） v1.0.2";
        Font = new Font("Microsoft YaHei UI", 9f);
        MinimumSize = new Size(820, 560); Size = new Size(980, 700);
        var top = new TableLayoutPanel { Dock = DockStyle.Top, AutoSize = true, ColumnCount = 3, Padding = new Padding(8) };
        top.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        top.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        top.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        Action<string, Control, Control> row = (t, c, b) =>
        {
            top.Controls.Add(new Label { Text = t, AutoSize = true, Anchor = AnchorStyles.Left, Margin = new Padding(3, 8, 3, 3) });
            c.Dock = DockStyle.Fill; top.Controls.Add(c);
            if (b != null) top.Controls.Add(b); else top.Controls.Add(new Label());
        };
        mapBtn.Text = "选择…"; mapBtn.AutoSize = true; hexBtn.Text = "选择…"; hexBtn.AutoSize = true;
        row("① .map 文件（必填）", mapBox, mapBtn);
        row("② .hex 文件（建议）", hexBox, hexBtn);
        durBox.DropDownStyle = ComboBoxStyle.DropDownList;
        durBox.Items.AddRange(new object[] { "3 分钟", "5 分钟", "10 分钟", "20 分钟" }); durBox.SelectedIndex = 1;
        row("③ 采样时长（每 5 秒一次）", durBox, null);
        var btns = new FlowLayoutPanel { Dock = DockStyle.Top, AutoSize = true, Padding = new Padding(8, 0, 8, 4) };
        startBtn.Text = "开始读取"; startBtn.AutoSize = true; stopBtn.Text = "停止"; stopBtn.AutoSize = true; stopBtn.Enabled = false;
        openBtn.Text = "打开记录文件夹"; openBtn.AutoSize = true; openBtn.Enabled = false;
        status.AutoSize = true; status.Margin = new Padding(12, 8, 3, 3);
        btns.Controls.AddRange(new Control[] { startBtn, stopBtn, openBtn, status });
        log.Multiline = true; log.ReadOnly = true; log.ScrollBars = ScrollBars.Both; log.WordWrap = false; log.Dock = DockStyle.Fill;
        log.Font = new Font("Consolas", 9.5f); log.BackColor = Color.White;
        Controls.Add(log); Controls.Add(btns); Controls.Add(top);

        mapBtn.Click += (a, b) => Pick(mapBox, "Keil map|*.map");
        hexBtn.Click += (a, b) => Pick(hexBox, "Intel HEX|*.hex");
        startBtn.Click += (a, b) => Start();
        stopBtn.Click += (a, b) => { stop = true; stopBtn.Enabled = false; };
        openBtn.Click += (a, b) => { if (runDir != null) Process.Start("explorer.exe", runDir); };
        mapBox.TextChanged += (a, b) => GuessHex();
        AllowDrop = true;
        DragEnter += (a, e) => { if (e.Data.GetDataPresent(DataFormats.FileDrop)) e.Effect = DragDropEffects.Copy; };
        DragDrop += (a, e) => { foreach (string f in (string[])e.Data.GetData(DataFormats.FileDrop)) SetFile(f); };
        Shown += (a, e) => { if (auto) Start(); };
        FormClosing += (a, e) => { stop = true; if (worker != null) worker.Join(3000); };

        Say("用途：GR 卡在 Boot TRIAL（owner INSTALL_PENDING、目标 GR5526）时，读出 GR 内存里的 120 秒健康计时和静默租约状态。");
        Say("只读：不停 GR、不写、不复位。J-Link 一直接着，设备保持上电，不要重新烧录。");
        Say("开始前：关掉 Keil 调试；6 号工具如果在用 J-Link 读进度，先点停止或取消勾选（同一个 J-Link 不能两个程序同时用）。");
        Say(".map 和 .hex 必须是板上这版固件的同一次 Keil 编译（Listings\\*.map、Objects\\*.hex）。可以把文件拖到窗口上。");
        Say("");
        if (!string.IsNullOrEmpty(arg)) SetFile(arg);
        else
        {
            var here = AppDomain.CurrentDomain.BaseDirectory;
            var maps = Directory.GetFiles(here, "*.map");
            if (maps.Length == 1) SetFile(maps[0]);
        }
    }

    void SetFile(string f)
    {
        if (f.EndsWith(".map", StringComparison.OrdinalIgnoreCase)) mapBox.Text = f;
        else if (f.EndsWith(".hex", StringComparison.OrdinalIgnoreCase)) hexBox.Text = f;
    }

    void GuessHex()
    {
        if (hexBox.Text.Length > 0 || !File.Exists(mapBox.Text)) return;
        var dir = Path.GetDirectoryName(mapBox.Text); var name = Path.GetFileNameWithoutExtension(mapBox.Text) + ".hex";
        foreach (var c in new[] { Path.Combine(dir, name), Path.Combine(Path.GetDirectoryName(dir) ?? dir, "Objects", name) })
            if (File.Exists(c)) { hexBox.Text = c; return; }
    }

    void Pick(TextBox box, string filter)
    {
        using (var d = new OpenFileDialog { Filter = filter }) if (d.ShowDialog(this) == DialogResult.OK) box.Text = d.FileName;
    }

    void Say(string s)
    {
        if (InvokeRequired) { BeginInvoke(new Action<string>(Say), s); return; }
        log.AppendText(s + "\r\n");
        if (runDir != null) try { File.AppendAllText(Path.Combine(runDir, "报告.txt"), s + "\r\n", Encoding.UTF8); } catch { }
    }

    void Status(string s) { if (InvokeRequired) { BeginInvoke(new Action<string>(Status), s); return; } status.Text = s; }

    void Done()
    {
        if (InvokeRequired) { BeginInvoke(new Action(Done)); return; }
        startBtn.Enabled = mapBtn.Enabled = hexBtn.Enabled = durBox.Enabled = true; stopBtn.Enabled = false; openBtn.Enabled = runDir != null;
        if (auto) Close();
    }

    void Start()
    {
        if (!File.Exists(mapBox.Text)) { MessageBox.Show(this, "先选 .map 文件"); return; }
        if (hexBox.Text.Length > 0 && !File.Exists(hexBox.Text)) { MessageBox.Show(this, ".hex 文件不存在"); return; }
        var exe = JLink.Exe();
        if (exe == null) { MessageBox.Show(this, "电脑上没装 SEGGER J-Link 软件（默认 C:\\Program Files\\SEGGER\\JLink）"); return; }
        int min = autoMin > 0 ? autoMin : new[] { 3, 5, 10, 20 }[durBox.SelectedIndex];
        runDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "logs", DateTime.Now.ToString("yyyyMMdd_HHmmss"));
        Directory.CreateDirectory(Path.Combine(runDir, "jlink"));
        log.Clear();
        startBtn.Enabled = mapBtn.Enabled = hexBtn.Enabled = durBox.Enabled = false; stopBtn.Enabled = true; openBtn.Enabled = true; stop = false;
        string map = mapBox.Text, hex = hexBox.Text;
        worker = new Thread(() => { try { Run(exe, map, hex, min); } catch (Exception ex) { Say("程序异常，已停止：" + ex); } finally { Done(); } }) { IsBackground = true };
        worker.Start();
    }

    static uint U32(byte[] b, int o) { return BitConverter.ToUInt32(b, o); }

    void Run(string exe, string map, string hex, int minutes)
    {
        string jdir = Path.Combine(runDir, "jlink");
        Say("YP001 GR 试运行卡点读取 v1.0.2   " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"));
        Say("J-Link 程序：" + exe);
        Say(".map：" + map + "（" + File.GetLastWriteTime(map).ToString("yyyy-MM-dd HH:mm:ss") + "）");
        Sym code; string err;
        var syms = MapFile.Load(map, out code, out err);
        if (syms == null) { Say("停止：" + err); Status("停止"); return; }
        bool wideEnum = syms["s"].Size == 380;
        Say(".map 核对通过：16 个变量地址和大小都符合（业务状态结构 " + syms["s"].Size + " 字节）。");
        try { File.Copy(map, Path.Combine(runDir, "used.map"), true); } catch { }

        // 1. 版本核对：.hex 与板上 Flash 对比（连读两次，不停核）。
        string identity = "未核对（没给 .hex）";
        var reads = new List<KeyValuePair<string, KeyValuePair<uint, int>>>();
        Dictionary<uint, byte> hx = null;
        if (hex.Length > 0)
        {
            Say(".hex：" + hex + "（" + File.GetLastWriteTime(hex).ToString("yyyy-MM-dd HH:mm:ss") + "）");
            hx = HexFile.Load(hex);
            reads.Add(Kv("head1.bin", 0x00202000u, 0x300)); reads.Add(Kv("head2.bin", 0x00202000u, 0x300));
            if (code != null) { uint c = code.Addr & ~0xFFu; reads.Add(Kv("code1.bin", c, 0x200)); reads.Add(Kv("code2.bin", c, 0x200)); }
        }
        reads.Add(Kv("s.bin", syms["s"].Addr, 32));
        Status("第一次连接 J-Link…");
        var first = JLink.Read(exe, jdir, "check", reads);
        if (!first.Ok) { Say("停止：" + first.Error); Status("停止"); return; }
        Say("J-Link 编号 " + first.SerialNo + "，实际选中 CORTEX-M4，识别到 Cortex-M4 内核。");
        if (first.HaltBefore) { Say("停止：读取前 GR 内核已经处于停住状态（可能 Keil 调试还连着）。本工具不去恢复运行，请先关 Keil 调试、让板子正常运行后再读。"); Status("停止"); return; }
        if (first.HaltAfter) { Say("停止：读取后发现 GR 内核停住了。保持现场，不要断电，把整个记录文件夹发给开发。"); Status("停止"); return; }
        if (hx != null)
        {
            var parts = new List<string>(); bool mismatch = false, unstable = false; int compared = 0;
            foreach (var pair in new[] { new[] { "head1.bin", "head2.bin" }, new[] { "code1.bin", "code2.bin" } })
            {
                if (!first.Bins.ContainsKey(pair[0])) continue;
                byte[] a = first.Bins[pair[0]], b = first.Bins[pair[1]];
                if (!a.SequenceEqual(b)) { unstable = true; continue; }
                uint baseAddr = reads.First(x => x.Key == pair[0]).Value.Key;
                for (int i = 0; i < a.Length; i++) { byte v; if (hx.TryGetValue(baseAddr + (uint)i, out v)) { compared++; if (v != a[i]) mismatch = true; } }
            }
            if (mismatch) { Say("停止：板上固件和这份 .hex 不一致 —— .map/.hex 不是板上这版的编译产物，变量地址不可信。请找 1.5.30 那次编译的 Listings\\*.map 和 Objects\\*.hex。"); Status("停止"); return; }
            identity = unstable ? "无法核对（运行中两次读 Flash 不一致，按规则不停核重读；结果仍可参考，但 .map 必须确认是同一次编译）"
                     : compared < 256 ? "无法核对（.hex 里对应地址数据太少）" : "一致（对比 " + compared + " 字节：向量表、版本信息区、OTA 代码）";
            Say("板上固件 ↔ .hex：" + identity);
        }

        // 2. 采样。
        var rv = new List<KeyValuePair<string, KeyValuePair<uint, int>>>();
        foreach (var kv in syms)
        {
            int n = kv.Key == "health_check" ? 12 : kv.Value.Size;
            rv.Add(Kv(kv.Key + ".bin", kv.Value.Addr, n));
        }
        var samples = new List<Sample>();
        var csv = new StringBuilder("时间,now_ms,健康计时开始,健康计时秒,健康身份有效,Boot状态,电量记录,电量记录距今ms,电量已知,告警,通话,链路,网络,静默阶段,租约序号,获准,最近租约过程,GR侧拒绝次数\r\n");
        Say("");
        Say("开始采样 " + minutes + " 分钟，每 5 秒一次。列：健康计时 | 条件（电量记录 告警 通话 链路/网络 健康身份）| 静默租约");
        DateTime end = DateTime.Now.AddMinutes(minutes);
        int idx = 0, fails = 0;
        while (!stop && DateTime.Now < end)
        {
            DateTime t0 = DateTime.Now;
            Status("采样 " + (idx + 1) + "，剩余 " + (int)(end - DateTime.Now).TotalSeconds + " 秒");
            var r = JLink.Read(exe, jdir, "s" + idx.ToString("D3"), rv);
            idx++;
            if (!r.Ok)
            {
                Say(t0.ToString("HH:mm:ss") + "  读取失败：" + r.Error);
                if (++fails >= 3) { Say("连续 3 次读取失败，停止。"); break; }
                continue;
            }
            fails = 0;
            if (r.HaltBefore || r.HaltAfter) { Say("停止：发现 GR 内核处于停住状态（读前 " + r.HaltBefore + "，读后 " + r.HaltAfter + "）。保持现场，不要断电，把记录文件夹发给开发。"); break; }
            if (r.SerialNo != first.SerialNo) { Say("停止：J-Link 编号变了（" + first.SerialNo + " → " + r.SerialNo + "）。"); break; }
            var sm = Decode(r.Bins, wideEnum); sm.At = t0;
            if (samples.Count > 0 && sm.Now == samples[samples.Count - 1].Now) { Say("停止：两次采样之间 GR 的 now_ms 没有前进，GR 可能没在运行。保持现场，把记录文件夹发给开发。"); break; }
            samples.Add(sm);
            Say(Line(sm));
            csv.Append(string.Join(",", new object[] { t0.ToString("HH:mm:ss"), sm.Now, sm.HealthStarted ? 1 : 0, sm.HealthSec.ToString("0.0", CultureInfo.InvariantCulture), sm.HcValid ? 1 : 0, Sample.BootName(sm.HcState),
                sm.BattSeen ? 1 : 0, (uint)(sm.ClockNow - sm.BattMs), sm.BattKnown ? 1 : 0, sm.Alarm ? 1 : 0, Sample.CallName(sm.Call), sm.Transport ? 1 : 0, Sample.NetName(sm.Net),
                sm.Phase, sm.Token, sm.Granted ? 1 : 0, Sample.Flags(sm.Trace[3]).Replace(',', ' '), sm.DenialCount }) + "\r\n");
            try { File.WriteAllText(Path.Combine(runDir, "samples.csv"), csv.ToString(), Encoding.UTF8); } catch { }
            int wait = 5000 - (int)(DateTime.Now - t0).TotalMilliseconds;
            while (wait > 0 && !stop) { Thread.Sleep(Math.Min(wait, 200)); wait -= 200; }
        }
        Say("");
        Verdict(samples, identity, first.SerialNo);
        Status("完成，记录在 logs 文件夹");
    }

    static KeyValuePair<string, KeyValuePair<uint, int>> Kv(string f, uint a, int n) { return new KeyValuePair<string, KeyValuePair<uint, int>>(f, new KeyValuePair<uint, int>(a, n)); }

    static Sample Decode(Dictionary<string, byte[]> b, bool wideEnum)
    {
        var sm = new Sample();
        var s = b["s.bin"];
        sm.Alarm = s[0] != 0; sm.BattKnown = s[1] != 0; sm.Transport = s[12] != 0; sm.Battery = s[13];
        if (wideEnum) { sm.Call = (int)U32(s, 16); sm.Net = (int)U32(s, 20); sm.Now = U32(s, 24); }
        else { sm.Call = s[15]; sm.Net = s[16]; sm.Now = U32(s, 20); }
        sm.BattSeen = b["ota_battery_seen.bin"][0] != 0; sm.BattMs = U32(b["ota_battery_ms.bin"], 0);
        sm.KeysSeen = b["ota_keys_seen.bin"][0] != 0; sm.KeysMs = U32(b["ota_keys_ms.bin"], 0);
        sm.HealthStarted = b["health_started.bin"][0] != 0; sm.HealthSince = U32(b["health_since.bin"], 0);
        sm.ResultCheckStarted = b["result_check_started.bin"][0] != 0; sm.ResultCheckAt = U32(b["result_check_at.bin"], 0);
        var hc = b["health_check.bin"]; sm.HcValid = hc[0] != 0; sm.HcGen = U32(hc, 4); sm.HcState = U32(hc, 8);
        sm.Known = b["known.bin"][0] != 0;
        // SAM | 2026-11-10 +08:00 | owner 记录 RAM 副本：短枚举 344 字节（phase 1 字节），整型枚举 348 字节。
        var st = b["state.bin"]; int po = st.Length == 344 ? 5 : 8;
        sm.OwnerPhase = st.Length == 344 ? st[4] : (int)U32(st, 4);
        sm.Target = Cstr(st, po + 130, 8); sm.Version = Cstr(st, po + 138, 64); sm.Source = Cstr(st, po + 202, 64);
        var q = b["quiet.bin"];
        sm.Phase = q[0]; sm.Kind = q[1]; sm.Token = U32(q, 1044); sm.HealthAt = U32(q, 1052); sm.Granted = q[1076] != 0; sm.Allowed = q[1077] != 0;
        var tr = b["g_ota_quiet_trace.bin"]; var ft = b["g_ota_quiet_first_timeout.bin"];
        for (int i = 0; i < 16; i++) { sm.Trace[i] = U32(tr, i * 4); sm.FirstTimeout[i] = U32(ft, i * 4); }
        sm.TraceStable = (sm.Trace[0] & 1) == 0;
        var dn = b["yp001_ota_quiet_denial.bin"]; sm.DenialCount = U32(dn, 4); sm.DenialMask = U32(dn, 24);
        return sm;
    }

    static string Cstr(byte[] b, int o, int n)
    {
        var sb = new StringBuilder();
        for (int i = o; i < o + n && i < b.Length && b[i] != 0; i++) sb.Append(b[i] >= 32 && b[i] < 127 ? (char)b[i] : '?');
        return sb.ToString();
    }

    static string Line(Sample m)
    {
        string health = m.HealthStarted ? "计时 " + m.HealthSec.ToString("0") + "s/120s" : "计时未开始";
        // SAM | 2026-11-10 +08:00 | v1.0.2: GR 的"电量已知"= 电量记录新鲜 且（电池电量已知 或 USB 供电证据）。v1.0.1 只显示新鲜度，电池未知时误显示"√"。
        string cond = "电量" + (m.BattFresh ? (m.BattKnown ? "√" + m.Battery + "%" : "未知(只能靠USB)") : (m.BattSeen ? "旧" + ((uint)(m.ClockNow - m.BattMs) / 1000) + "s" : "×")) +
            " 告警" + (m.Alarm ? "有" : "无") + " 通话" + Sample.CallName(m.Call) + " 链路" + (m.Transport ? "√" : "×") + "/" + Sample.NetName(m.Net) +
            " 身份" + (m.HcValid ? Sample.BootName(m.HcState) : "未核");
        string q = "租约#" + m.Token + " 阶段" + m.Phase + (m.Phase != 0 ? "(类" + m.Kind + (m.Granted ? " 获准" : "") + ")" : "") +
            " 最近:" + (m.TraceStable ? Sample.Flags(m.Trace[3]) : "正在更新") + (m.DenialCount > 0 ? " GR拒" + m.DenialCount : "");
        return m.At.ToString("HH:mm:ss") + "  " + (m.InTrialFlow ? "" : "[" + m.OwnerText + "] ") + health + " | " + cond + " | " + q;
    }

    void Verdict(List<Sample> ss, string identity, string sn)
    {
        Say("==================== 结论 ====================");
        Say("J-Link 编号：" + sn + "；固件核对：" + identity + "；有效样本 " + ss.Count + " 个。");
        if (ss.Count < 3) { Say("样本太少（不到 3 个），不下结论。看上面的读取失败原因，处理后再读一次。"); return; }
        var a = ss[0]; var z = ss[ss.Count - 1];
        double span = (uint)(z.Now - a.Now) / 1000.0;
        Say("GR 时钟前进 " + span.ToString("0") + " 秒（证明 GR 一直在运行，没有被停住）。");
        Say("OTA 记录（GR 内存）：开始 " + a.OwnerText + "；结束 " + z.OwnerText);
        Say("健康身份：" + (z.HcValid ? "已核对，Boot=" + Sample.BootName(z.HcState) : "未核对"));
        if (a.InTrialFlow && !z.InTrialFlow) { Say("【已往下走】采样期间 OTA 记录离开了“GR 试运行待确认”（现在：" + z.OwnerText + "）。用 6 号工具继续看 CAT1 阶段。"); return; }
        if (!z.InTrialFlow) { Say("【不适用】设备当前不在“GR 试运行待确认”阶段（需要 INSTALL_PENDING、目标 GR5526；现在：" + z.OwnerText + "），本工具的卡点判断不适用。用 6 号工具看当前阶段。"); return; }
        if (z.HcValid && z.HcState == 5) { Say("【已往下走】Boot 已经 CONFIRMED，下一步 GR 会写 OTA 记录并切到 CAT1，稍等后用 6 号工具确认。"); return; }

        int n = ss.Count;
        int battUnknown = ss.Count(x => x.BattFresh && !x.BattKnown);
        int battBad = ss.Count(x => !x.BattFresh), alarm = ss.Count(x => x.Alarm), call = ss.Count(x => !x.CallOk), link = ss.Count(x => !x.NetOk), idBad = ss.Count(x => !x.HcValid);
        double maxHealth = ss.Max(x => x.HealthSec);
        uint leases = z.Token - a.Token;
        uint denials = z.DenialCount - a.DenialCount;
        Say("");
        Say("A. 120 秒健康计时：最长连续 " + maxHealth.ToString("0") + " 秒。各条件不满足的样本数（共 " + n + "）：");
        Say("   电池电量未知（只能靠 USB 供电证据）" + battUnknown + "，电量记录不新鲜（>3 秒没更新）" + battBad + "，有告警 " + alarm + "，通话非空闲 " + call + "，链路/网络不是 MQTT " + link + "，健康身份未核对 " + idBad);
        Say("B. 静默租约：采样期间 GR 申请了 " + leases + " 次（序号 " + a.Token + " → " + z.Token + "）；GR 侧安全检查拒绝新增 " + denials + " 次；最近一次过程：" + Sample.Flags(z.Trace[3]) +
            ((z.Trace[3] & 64) != 0 ? "（超时发生在阶段 " + z.Trace[11] + "）" : ""));
        if (z.FirstTimeout[0] != 0) Say("   开机以来第一次超时：租约#" + z.FirstTimeout[1] + "，过程 " + Sample.Flags(z.FirstTimeout[3]) + "，阶段 " + z.FirstTimeout[11]);
        uint seen = 0; foreach (var x in ss) if (x.TraceStable && x.Token != a.Token) seen |= x.Trace[3];
        if (leases > 0) Say("   采样期间各次租约出现过的步骤合计：" + Sample.Flags(seen));
        Say("");
        if (leases == 0 && maxHealth < 120)
        {
            var why = new List<string>();
            if (battUnknown > 0) why.Add("GR 读不到电池电量（" + battUnknown + "/" + n + " 个样本），这时 GR 只能靠充电芯片报告的 USB 供电证据算“电量已知”，这个证据要每次检查都成立，时有时无就会把计时清零 —— 请确认 GR 板上接了电池、屏上能显示电量；这一项本工具在采样点上看不到 USB 证据本身");
            if (battBad > 0) why.Add("电量记录不新鲜（GR 没按时拿到电量，或电量未知且没识别到 USB 供电）");
            if (alarm > 0) why.Add("有告警");
            if (call > 0) why.Add("通话状态不是空闲/已结束（包括“未知”）");
            if (link > 0) why.Add("GR 认为 CAT1 链路未就绪或网络不是 MQTT");
            if (idBad > 0) why.Add("GR 还没核对运行镜像身份");
            if (why.Count == 0) why.Add("条件在采样点上都满足，但计时仍被打断：可能是两次检查间隔超过 3 秒（GR 忙），或在采样间隙条件短暂不满足");
            Say("【判断】卡在 120 秒健康计时，GR 一直没攒够 120 秒，所以根本没去申请静默租约。原因：" + string.Join("；", why) + "。");
        }
        else if (leases == 0)
            Say("【判断】健康计时已满 120 秒，但采样期间 GR 没有新申请租约：可能静默流程卡在非 0 阶段（当前阶段 " + z.Phase + "），或 GR 安全检查不过（见 B）。把记录文件夹发给开发。");
        else if ((seen & 2) == 0)
            Say("【判断】GR 一直在申请静默租约，但收不到 CAT1 的回复（241）。CAT1 没有处理 GR 的静默请求 —— 查 CAT1 侧串口收发和 ota_uart_window。");
        else if ((seen & 4) == 0)
            Say(denials > 0 ? "【判断】CAT1 有回复，但 GR 自己的安全检查不过（电量/告警/通话/链路），没开始写。看 A 的条件统计。"
                            : "【判断】CAT1 回复了 241 但是“拒绝”（CAT1 认为自己不空闲：正在发 OTA_CTL、等回复或有挂起事务）。这就是 CAT1 一直有电、不停发 INSTALLING 时的卡点 —— 查 CAT1 ota_uart_window 的 idle()/denied。");
        else if ((seen & 8) != 0 && z.HcValid && z.HcState == 3)
            Say("【判断】租约已获准、写也做完了，但 Boot 仍是 TRIAL：Boot 确认（yp_boot_confirm）没成功。把记录文件夹发给开发。");
        else
            Say("【判断】租约流程在推进（最近：" + Sample.Flags(z.Trace[3]) + "），延长采样再看一次。");
        Say("");
        Say("把整个记录文件夹（报告.txt、samples.csv、jlink\\）发给开发。");
    }

    [STAThread]
    static void Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new MainForm(args));
    }
}
