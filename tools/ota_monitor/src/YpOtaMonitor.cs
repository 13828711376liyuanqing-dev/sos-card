// SAM | 2026-11-10 +08:00 | YP001 OTA 过程监控（6 号工具）。只读监控：检查硬件（J-Link / GR 调试串口 / CAT1 USB）并提示要接什么、关什么；
// 监控时：GR 串口保持 CAT1 供电并读 [OTA_RX]，CAT1 USB 读 OTA 信标，J-Link 只读 GR 的 owner / Boot 记录（不停核、不写）。
// 不需要 Python；.NET Framework 4 自带。口号不写死：GR 口自动找（排除 CAT1 19D1/17D1、nRF 1915、J-Link 1366），CAT1 信标口按 USB 接口号（MI_06、MI_02）找，MI_04 是二进制口不打开。
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Ports;
using System.Linq;
using System.Management;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

class PortInfo
{
    public string Com, Name, Id;
    public int Vid { get { return Hex("VID_"); } }
    public string Mi { get { var m = Regex.Match(Id, "MI_([0-9A-F]{2})"); return m.Success ? m.Groups[1].Value : ""; } }
    int Hex(string k) { var m = Regex.Match(Id, k + "([0-9A-F]{4})"); return m.Success ? Convert.ToInt32(m.Groups[1].Value, 16) : 0; }
    public override string ToString() { return Com + "  " + Name; }
}

static class Hw
{
    public const int CAT1 = 0x19D1, CAT1_DL = 0x17D1, NRF = 0x1915, JLINK = 0x1366;

    public static List<PortInfo> Ports()
    {
        var list = new List<PortInfo>();
        try
        {
            using (var s = new ManagementObjectSearcher("SELECT Name, DeviceID FROM Win32_PnPEntity WHERE Name LIKE '%(COM%'"))
                foreach (ManagementObject o in s.Get())
                {
                    string name = (o["Name"] ?? "").ToString(), id = (o["DeviceID"] ?? "").ToString().ToUpper();
                    var m = Regex.Match(name, @"\((COM\d+)\)");
                    if (m.Success) list.Add(new PortInfo { Com = m.Groups[1].Value, Name = name, Id = id });
                }
        }
        catch { }
        return list.OrderBy(p => int.Parse(p.Com.Substring(3))).ToList();
    }

    public static bool UsbPresent(int vid)
    {
        try
        {
            using (var s = new ManagementObjectSearcher("SELECT DeviceID FROM Win32_PnPEntity WHERE DeviceID LIKE 'USB\\\\VID_" + vid.ToString("X4") + "%'"))
                return s.Get().Count > 0;
        }
        catch { return false; }
    }

    public static List<PortInfo> GrCandidates(List<PortInfo> ps)
    {
        return ps.Where(p => p.Vid != CAT1 && p.Vid != CAT1_DL && p.Vid != NRF && p.Vid != JLINK).ToList();
    }

    // 信标口：MI_06（台架上是 COM21）为主，MI_02（COM23）备用；MI_04（COM22）是二进制跟踪口，不打开
    public static List<string> Cat1BeaconPorts(List<PortInfo> ps)
    {
        return ps.Where(p => p.Vid == CAT1 && (p.Mi == "06" || p.Mi == "02")).OrderBy(p => p.Mi == "06" ? 0 : 1).Select(p => p.Com).ToList();
    }

    public static string JLinkExe()
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

    // 0 = 能打开，1 = 被占用，2 = 其他错误
    public static int TryOpen(string com, out string err)
    {
        err = "";
        try { using (var s = new SerialPort(com, 115200)) { s.Open(); s.Close(); } return 0; }
        catch (UnauthorizedAccessException) { return 1; }
        catch (Exception e) { err = e.Message; return 2; }
    }

    public static string[] RunningTools()
    {
        var names = new[] { "Luatools", "sscom", "XCOM", "MobaXterm", "putty", "SecureCRT", "LLCOM", "UartAssist", "JLinkRTTViewer", "JFlash" };
        var hit = new List<string>();
        foreach (var p in Process.GetProcesses())
        {
            try { foreach (var n in names) if (p.ProcessName.StartsWith(n, StringComparison.OrdinalIgnoreCase) && !hit.Contains(p.ProcessName)) hit.Add(p.ProcessName); }
            catch { }
        }
        return hit.ToArray();
    }
}

// J-Link 只读 GR 的 OTA owner（0x2F9000，两页）和 Boot 记录（0x2F7000，两页）
class OwnerState
{
    public bool Ok; public string Error = "";
    public uint Generation, Epoch; public string Job = "", Hash = ""; public string Phase = "", Target = "", Version = "", Source = "", Actual = "", Outcome = "", Boot = "";
    public string Key { get { return Ok ? Generation + "|" + Epoch + "|" + Job + "|" + Hash + "|" + Phase + "|" + Target + "|" + Version + "|" + Outcome + "|" + Actual + "|" + Boot : "ERR|" + Error; } }
    public string Text
    {
        get
        {
            if (!Ok) return "读不到：" + Error;
            return "记录代次 " + Generation + "  阶段 " + Phase + "  对象 " + Target + "  目标版本 " + Version + "  结果 " + (Outcome == "" ? "-" : Outcome) +
                   (Actual == "" ? "" : "  实际 " + Actual) + "  Boot " + Boot + "  epoch=" + Epoch + (Job == "" ? "" : "  job=" + Job) + (Hash == "" ? "" : "  hash=" + Hash);
        }
    }
}

static class GrProbe
{
    static readonly string[] PHASE = { "IDLE", "DOWNLOADING", "PREPARED", "INSTALL_PENDING", "COMPLETE" };
    static readonly Dictionary<uint, string> BOOT = new Dictionary<uint, string> { { 0, "EMPTY" }, { 1, "PREPARED" }, { 2, "INSTALL" }, { 3, "TRIAL" }, { 4, "ROLLBACK" }, { 5, "CONFIRMED" }, { 6, "REVERTED" } };
    static uint[] table;

    static uint Crc32(byte[] b, int off, int len)
    {
        if (table == null)
        {
            table = new uint[256];
            for (uint i = 0; i < 256; i++) { uint c = i; for (int k = 0; k < 8; k++) c = (c & 1) != 0 ? 0xEDB88320 ^ (c >> 1) : c >> 1; table[i] = c; }
        }
        uint crc = 0xFFFFFFFF;
        for (int i = off; i < off + len; i++) crc = table[(crc ^ b[i]) & 0xFF] ^ (crc >> 8);
        return crc ^ 0xFFFFFFFF;
    }

    static bool AllFF(byte[] data, int offset, int length)
    {
        for (int i = offset; i < offset + length; i++) if (data[i] != 255) return false;
        return true;
    }

    static string Str(byte[] b, int off, int n)
    {
        int end = off;
        while (end < off + n && b[end] != 0)
        {
            if (b[end] < 32 || b[end] > 126) throw new InvalidDataException("OTA 记录字符串不合法，等待下一次读取");
            end++;
        }
        if (end == off + n) throw new InvalidDataException("OTA 记录字符串未结束，等待下一次读取");
        return Encoding.ASCII.GetString(b, off, end - off);
    }

    public static OwnerState Read(string jlink, string workDir)
    {
        var st = new OwnerState();
        try
        {
            Directory.CreateDirectory(workDir);
            string ob = Path.Combine(workDir, "owner.bin"), jb = Path.Combine(workDir, "journal.bin"), cmd = Path.Combine(workDir, "probe.jlink");
            if (File.Exists(ob)) File.Delete(ob);
            if (File.Exists(jb)) File.Delete(jb);
            // SAM | 2026-11-10 +08:00 | Commander script operands must stay ASCII in Unicode folders; OTA sampling must preserve run state.
            File.WriteAllText(cmd, "exec SetRestartOnClose = 0\nsavebin owner.bin,0x2F9000,0x2000\nsavebin journal.bin,0x2F7000,0x2000\nexit\n", Encoding.ASCII);
            var psi = new ProcessStartInfo(jlink, "-NoGui 1 -ExitOnError 1 -device CORTEX-M4 -if SWD -speed 4000 -autoconnect 1 -Log jlink.sdk.log -CommandFile probe.jlink")
            { WorkingDirectory = Path.GetFullPath(workDir), UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
            using (var p = Process.Start(psi))
            {
                // SAM | 2026-11-10 +08:00 | Drain both pipes before a bounded wait so a hung child cannot block Stop forever.
                var stdout = p.StandardOutput.ReadToEndAsync();
                var stderr = p.StandardError.ReadToEndAsync();
                bool exited = p.WaitForExit(60000);
                if (!exited) { try { p.Kill(); } catch { } }
                bool drained = System.Threading.Tasks.Task.WaitAll(new System.Threading.Tasks.Task[] { stdout, stderr }, 5000);
                string outp = drained ? stdout.Result + stderr.Result : "J-Link 输出读取超时";
                File.WriteAllText(Path.Combine(workDir, "jlink.txt"), outp, Encoding.UTF8);
                if (!exited || !drained) { st.Error = "J-Link 读取超时，已停止本次读取，见 jlink.txt"; return st; }
                if (p.ExitCode != 0 || !File.Exists(ob) || !File.Exists(jb))
                {
                    st.Error = outp.Contains("No J-Link") || outp.Contains("Connecting to J-Link via USB...FAILED") ? "电脑上找不到或无法独占 J-Link（核对 USB 和占用程序）"
                             : outp.Contains("Could not open file for writing") ? "J-Link 无法保存快照（核对日志目录写权限，见 jlink.txt）"
                             : outp.Contains("Cannot connect") || outp.Contains("Could not connect") ? "J-Link 连不上 GR（检查 SWD 线和板子供电）"
                             : "J-Link 读取失败（退出码 " + p.ExitCode + "），详情见 jlink.txt";
                    return st;
                }
            }
            byte[] o = File.ReadAllBytes(ob), j = File.ReadAllBytes(jb);
            if (o.Length != 8192 || j.Length != 8192) { st.Error = "读回长度不对"; return st; }
            // SAM | 2026-11-10 +08:00 | A nonempty invalid/torn sample is unknown, not an empty record or proof of completion.
            bool found = false;
            int selectedOffset = 0, selectedSize = 0;
            for (int pg = 0; pg < 2; pg++)
            {
                int b = pg * 4096;
                if (AllFF(o, b, 4096)) continue;
                uint magic = BitConverter.ToUInt32(o, b), gen = BitConverter.ToUInt32(o, b + 4);
                bool v1 = magic == 0x594F5431;
                int crcAt = v1 ? 352 : 360, size = v1 ? 360 : 368;
                if ((!v1 && magic != 0x594F5432) || gen == 0 || gen == uint.MaxValue || o[b + 12] >= PHASE.Length ||
                    BitConverter.ToUInt32(o, b + crcAt) != Crc32(o, b, crcAt) || BitConverter.ToUInt32(o, b + crcAt + 4) != 0 ||
                    !AllFF(o, b + size, 4096 - size))
                    throw new InvalidDataException("OTA owner 正在更新、校验失败或格式未知，请保留日志并等待重读");
                if (found && gen == st.Generation && (size != selectedSize ||
                    !o.Skip(b).Take(size).SequenceEqual(o.Skip(selectedOffset).Take(selectedSize))))
                    throw new InvalidDataException("OTA owner 同代记录冲突，不能判定进度");
                if (found && gen <= st.Generation) continue;
                found = true; selectedOffset = b; selectedSize = size;
                st.Generation = gen; st.Epoch = BitConverter.ToUInt32(o, b + 8);
                st.Job = Str(o, b + 13, 65); st.Hash = Str(o, b + 78, 65);
                st.Phase = PHASE[o[b + 12]];
                st.Target = Str(o, b + 143, 8); st.Version = Str(o, b + 151, 64); st.Source = Str(o, b + 215, 64);
                st.Actual = Str(o, b + 279, 64); st.Outcome = Str(o, b + 343, 8);
            }
            uint bestGen = 0; bool jf = false;
            for (int pg = 0; pg < 2; pg++)
            {
                int b = pg * 4096;
                if (AllFF(j, b, 4096)) continue;
                uint gen = BitConverter.ToUInt32(j, b + 4), state = BitConverter.ToUInt32(j, b + 12);
                uint oldSize = BitConverter.ToUInt32(j, b + 28), newSize = BitConverter.ToUInt32(j, b + 68);
                if (BitConverter.ToUInt32(j, b) != 0x59504231 || gen == 0 || gen == uint.MaxValue ||
                    BitConverter.ToUInt32(j, b + 116) != Crc32(j, b, 116) || BitConverter.ToUInt32(j, b + 120) != 0 ||
                    BitConverter.ToUInt32(j, b + 8) != 0xbcc4a6a4 || state < 1 || state > 6 ||
                    BitConverter.ToUInt32(j, b + 16) > 108 || BitConverter.ToUInt32(j, b + 20) > 2 ||
                    oldSize == 0 || oldSize > 442368 || newSize == 0 || newSize > 442368 ||
                    BitConverter.ToUInt32(j, b + 108) != 1 || BitConverter.ToUInt32(j, b + 112) != 0)
                    throw new InvalidDataException("Boot 记录正在更新、校验失败或布局不匹配，请保留日志并等待重读");
                if (jf && gen == bestGen) throw new InvalidDataException("Boot 同代记录无法唯一确定，不能判定完成");
                if (jf && gen < bestGen) continue;
                jf = true; bestGen = gen; st.Boot = BOOT[state];
            }
            if (!found) { st.Phase = "无记录"; }
            if (!jf) st.Boot = "无记录";
            st.Ok = true;
        }
        catch (Exception e) { st.Error = e.Message; }
        return st;
    }
}

class Cat1Beacon
{
    public string Phase, Ticket, Reason, Native, Step, Progress;
    public string Key { get { return Phase + "|" + Ticket + "|" + Reason + "|" + Native + "|" + Step + "|" + Progress; } }
    public string Text { get { return Phase + "  票据 " + Ticket + "  进度 " + Progress + "  本地安装 " + Native +
        "  步骤 " + Step + (Reason == "nil" ? "" : "  原因 " + Reason); } }
}

// SAM | 2026-11-10 +08:00 | Keep observed versions separate from targets, and raw status separate from completion verdicts.
// SAM | 2026-11-10 +08:00 | Only release holds requested here; missing ACK remains unconfirmed and requires cleanup.
// SAM | 2026-11-10 +08:00 | Match download assistant rail/probe/key ordering; one key attempt per session even when ACK is lost.
class Cat1Startup
{
    bool keyAttempted;
    public string Status = "尚未启动";
    static bool Traffic(string text) { return (text??"").Split('\n').Any(l=>l.Trim().StartsWith("[CAT1 RX] ")); }
    public bool Start(Func<string,int,string> ask, Action<int> wait, HoldSession hold, bool usbPresent)
    {
        string rail=ask("cat1_power on",2500)??"";
        if(!rail.Contains("[CAT1 POWER] rail_request=on code=0x0000;")) { Status="供电请求未确认，未发送PWRKEY";return false; }
        wait(200);
        bool live=Traffic(rail)||Traffic(ask("cat_at AT_INFO",2500));
        if(!live && !usbPresent)
        {
            if(keyAttempted) { Status="本轮已请求过PWRKEY，不重复发送；请核对启动日志";return false; }
            if(hold.Owned && !hold.Release(c=>ask(c,2000))) { Status="无法释放本工具旧保电，未发送PWRKEY";return false; }
            string state=ask("cat1_power status",2000)??"";
            if(!state.Contains("[CAT1 POWER] rail_request=1 factory_hold=0;")) { Status="电源状态未知或已有其他保电锁，未发送PWRKEY";return false; }
            keyAttempted=true;
            string key=ask("cat1_power key",4000)??"";
            if(!key.Contains("[CAT1 POWER] manual_key code=0x0000;")) { Status="PWRKEY仅请求一次，执行未确认；不自动重试";return false; }
        }
        bool held=hold.Acquire(c=>ask(c,2000));
        for(int i=0;!live && i<4;i++) { wait(1000);live=Traffic(ask("cat_at AT_INFO",2500)); }
        Status=live ? (held?"CAT1已有实际回应，GR保电已确认":"CAT1已有实际回应，但保电未确认") : (held?"GR保电已确认，但CAT1启动尚未确认；未重复PWRKEY":"CAT1启动与保电均未确认");
        return live && held;
    }
}

class HoldSession
{
    public bool Owned { get; private set; }
    public bool Confirmed { get; private set; }
    public void Invalidate() { Confirmed=false; }
    public bool Acquire(Func<string,string> ask)
    {
        string status = ask("cat1_power status") ?? "";
        var m=Regex.Match(status, @"\[CAT1 POWER\] rail_request=[01] factory_hold=([01]);");
        if(!m.Success) { Confirmed=false; return false; }
        if(m.Groups[1].Value=="1") { Confirmed=true; return true; }
        Owned=true; // A lost ACK must not leave an untracked hold on the device.
        string reply=ask("cat1_power hold_on") ?? "";
        Confirmed=reply.Contains("[CAT1 POWER] factory_hold=1 result=0;");
        return Confirmed;
    }
    public bool Release(Func<string,string> ask)
    {
        if(!Owned) { Confirmed=false; return true; }
        string reply=ask("cat1_power hold_off") ?? "";
        bool ok=reply.Contains("[CAT1 POWER] factory_hold=0; normal policy restored, rail unchanged");
        if(ok) { Owned=false; Confirmed=false; }
        return ok;
    }
}

// SAM | 2026-11-10 +08:00 | Local Chinese queries map to known read-only device commands.
static class MonitorCommands
{
    public static string Normalize(string text)
    {
        text=(text??"").Trim().ToLowerInvariant();
        if(new[]{"进度","查询进度","当前进度","progress"}.Contains(text)) return "进度";
        if(new[]{"版本","查询版本","version"}.Contains(text)) return "版本";
        if(new[]{"保电状态","电源状态","power"}.Contains(text)) return "保电状态";
        if(new[]{"帮助","help"}.Contains(text)) return "帮助";
        return "";
    }
    public static string[] Queries(string command)
    {
        if(command=="进度") return new[]{"at FOTA_STATUS","business status"};
        if(command=="版本") return new[]{"fw_version","cat_at AT_INFO"};
        if(command=="保电状态") return new[]{"cat1_power status"};
        return new string[0];
    }
}

class MonitorEvidence
{
    readonly object sync = new object();
    string gr = "未读到", cat = "未读到", phase = "未读到", reason = "未读到", detail = "未读到";
    readonly Dictionary<string, DateTime> seen = new Dictionary<string, DateTime>();
    string owner = "GR/Boot尚未读到", progress = "进度未读到", step = "步骤未读到", power = "保电状态未读到";
    public void Owner(OwnerState state) { lock(sync) owner=DateTime.Now.ToString("HH:mm:ss")+" "+state.Text; }
    public string Summary { get { lock(sync) return Versions+Environment.NewLine+owner+Environment.NewLine+Status+Environment.NewLine+progress+"，"+step+Environment.NewLine+power+Environment.NewLine+Times; } }
    public void Seen(string source) { lock(sync) seen[source] = DateTime.Now; }
    static string Version(string s) { return string.Join(".", s.Split('.').Select(x => int.Parse(x).ToString()).ToArray()); }
    public void Observe(string line)
    {
        lock(sync)
        {
            var g = Regex.Match(line, @"\[FW_VERSION\] YP001_FW\|GR5526\|(\d{1,3}\.\d{1,3}\.\d{1,3})\|(\d+)");
            var c = Regex.Match(line, @"LuatOS Ver:\s*(\d{1,3}\.\d{1,3}\.\d{1,3})(?![\d.])");
            if(g.Success) gr = Version(g.Groups[1].Value) + " build " + g.Groups[2].Value + "（" + DateTime.Now.ToString("HH:mm:ss") + "读取）";
            if(c.Success) cat = Version(c.Groups[1].Value) + "（" + DateTime.Now.ToString("HH:mm:ss") + "读取）";
            var p=Regex.Match(line,@"OTA_PROGRESS=(\S+)"); if(p.Success) progress=p.Groups[1].Value;
            var st=Regex.Match(line,@"OTA_STEP=(\S+)"); if(st.Success) step=st.Groups[1].Value;
            var pw=Regex.Match(line,@"\[CAT1 POWER\] [^\r\n]+"); if(pw.Success) power=pw.Value+"（"+DateTime.Now.ToString("HH:mm:ss")+"）";
            var ph = Regex.Match(line, @"\[FOTA_STATUS\]\s+(IDLE|RECOVERY_HOLD|PAUSED|PREPARING|PREPARED|WAIT_ACTIVATE|INSTALLING|ACTIVATION_ISSUED|COMPLETE_PENDING)\b");
            if(ph.Success) phase = ph.Groups[1].Value;
            var r = Regex.Match(line, @"OTA_REASON=([^\s\]]+)");
            if(r.Success) reason = r.Groups[1].Value + "（" + DateTime.Now.ToString("HH:mm:ss") + "）";
            var d = Regex.Match(line, @"\[OTA\]\s+ACTIVATION_RECHECK_FAILED\s+(SAFE_AFTER_VERIFY|SAFE|VALIDATE|VERIFY_CANDIDATE)\b");
            if(d.Success) detail = d.Groups[1].Value + "（" + DateTime.Now.ToString("HH:mm:ss") + "）";
            if(line.Contains("=== YP001 GR5526 BOOT")) gr = "重启后未读到";
        }
    }
    public string Versions { get { lock(sync) return "GR：" + gr + "；CAT1：" + cat; } }
    public string Status { get { lock(sync) return "设备阶段：" + phase + "；最近原因：" + reason + "；最近复核失败项：" + detail; } }
    public string Times { get { lock(sync) return string.Join("；", new[]{"GR串口", "CAT1信标", "J-Link有效记录", "阶段变化"}.Select(k => k + "：" + (seen.ContainsKey(k) ? seen[k].ToString("HH:mm:ss") + "（" + (int)(DateTime.Now-seen[k]).TotalSeconds + "秒前）" : "未收到")).ToArray()); } }
}

class MainForm : Form
{
    readonly Font ui = new Font("Microsoft YaHei UI", 10f), mono = new Font("Consolas", 10f);
    ComboBox cbGr = new ComboBox();
    CheckBox chkKeep = new CheckBox(), chkJlink = new CheckBox();
    NumericUpDown numMin = new NumericUpDown();
    Button btnCheck = new Button(), btnStart = new Button(), btnStop = new Button(), btnVer = new Button(), btnFolder = new Button();
    Label lblGr = new Label(), lblCat = new Label(), lblPush = new Label(), lblState = new Label();
    Label lblVersions = new Label(), lblDetail = new Label(), lblUpdated = new Label();
    MonitorEvidence evidence = new MonitorEvidence();
    HoldSession hold = new HoldSession(); string holdCom;
    readonly Dictionary<string,Cat1Startup> startups = new Dictionary<string,Cat1Startup>();
    Label lblHold = new Label();
    System.Windows.Forms.Timer evidenceTimer = new System.Windows.Forms.Timer();
    RichTextBox box = new RichTextBox(), commandOutput = new RichTextBox();
    TextBox commandInput = new TextBox(); Button commandSend = new Button();
    Thread commandThread; bool commandBusy;
    readonly AutoResetEvent progressRefresh = new AutoResetEvent(false);
    int requestedOwnerReport;

    volatile bool running;
    volatile bool existingTask;
    bool stopping, checking, hardwareReady, closeAfterStop;
    string logDir, evLog;
    readonly object grLock = new object();
    SerialPort grPort;               // 监控期间由保电线程持有
    DateTime t0; bool gotRx; uint startGen; bool startGenKnown; bool done; DateTime nextWarn;
    List<Thread> workers = new List<Thread>();

    public MainForm()
    {
        Text = "YP001 OTA 过程监控 v1.5";
        Font = ui; ClientSize = new Size(1100, 760); MinimumSize = new Size(900, 600); StartPosition = FormStartPosition.CenterScreen;

        var top = new TableLayoutPanel { Dock = DockStyle.Top, AutoSize = true, ColumnCount = 6, Padding = new Padding(10, 8, 10, 4) };
        for (int i = 0; i < 6; i++) top.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        top.ColumnStyles[5] = new ColumnStyle(SizeType.Percent, 100);

        Btn(btnCheck, "① 检查硬件", Check); Btn(btnStart, "② 开始监控", Start); Btn(btnStop, "停止监控", Stop);
        Btn(btnVer, "读设备版本", ReadVersion); Btn(btnFolder, "打开日志文件夹", OpenFolder);
        btnStop.Enabled = false; btnStart.Enabled = false;
        var flow1 = Flow(); flow1.Controls.AddRange(new Control[] { btnCheck, btnStart, btnStop, btnVer, btnFolder });
        top.Controls.Add(flow1, 0, 0); top.SetColumnSpan(flow1, 6);

        cbGr.DropDownStyle = ComboBoxStyle.DropDownList; cbGr.Width = 360;
        chkKeep.Text = "启动并保电（检查时执行）"; chkKeep.Checked = true; chkKeep.AutoSize = true; chkKeep.Margin = new Padding(16, 6, 3, 3);
        chkJlink.Text = "用 J-Link 读 GR 进度"; chkJlink.Checked = true; chkJlink.AutoSize = true; chkJlink.Margin = new Padding(16, 6, 3, 3);
        numMin.Minimum = 10; numMin.Maximum = 180; numMin.Value = 45; numMin.Width = 60;
        var flow2 = Flow();
        flow2.Controls.AddRange(new Control[] { L("GR 调试串口："), cbGr, chkKeep, chkJlink, L("   最长（分钟）："), numMin });
        top.Controls.Add(flow2, 0, 1); top.SetColumnSpan(flow2, 6);

        var stat = new TableLayoutPanel { Dock = DockStyle.Top, AutoSize = true, ColumnCount = 2, Padding = new Padding(10, 2, 10, 6) };
        stat.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize)); stat.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        AddStat(stat, "状态", lblState); AddStat(stat, "推送", lblPush); AddStat(stat, "GR（J-Link）", lblGr); AddStat(stat, "CAT1 信标", lblCat);
        AddStat(stat, "实际版本", lblVersions); AddStat(stat, "设备诊断", lblDetail); AddStat(stat, "有效更新", lblUpdated);
        stat.SizeChanged += (s, e) => {
            foreach(var label in new[]{lblState,lblPush,lblGr,lblCat,lblVersions,lblDetail,lblUpdated,lblHold})
                label.MaximumSize = new Size(Math.Max(240, stat.ClientSize.Width - 150), 0);
        };
        AddStat(stat, "保电", lblHold); lblHold.Text = "尚未申请；点击检查硬件";
        evidenceTimer.Interval = 1000;
        evidenceTimer.Tick += (s, e) => { lblVersions.Text = evidence.Versions; lblDetail.Text = evidence.Status; lblUpdated.Text = evidence.Times; };
        evidenceTimer.Start(); FormClosed += (s, e) => evidenceTimer.Dispose();
        lblState.Text = "先点「① 检查硬件」"; lblPush.Text = "-"; lblGr.Text = "-"; lblCat.Text = "-";

        box.Dock = DockStyle.Fill; box.Font = mono; box.ReadOnly = true; box.BackColor = Color.White; box.WordWrap = true;
        var pad = new Panel { Dock = DockStyle.Fill, Padding = new Padding(10, 0, 10, 10) }; pad.Controls.Add(box);
        // SAM | 2026-11-10 +08:00 | Repeated queries use the shared serial lock and keep timestamped replies in the session log.
        var commandPanel=new Panel { Dock=DockStyle.Bottom, Height=175, Padding=new Padding(10,0,10,8) };
        var entry=new TableLayoutPanel { Dock=DockStyle.Bottom, Height=36, ColumnCount=3 };
        entry.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize)); entry.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100)); entry.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        entry.Controls.Add(L("查询命令")); commandInput.Dock=DockStyle.Fill; entry.Controls.Add(commandInput);
        Btn(commandSend,"发送",SubmitCommand); entry.Controls.Add(commandSend);
        commandOutput.Dock=DockStyle.Fill; commandOutput.ReadOnly=true; commandOutput.Font=mono; commandOutput.BackColor=Color.FromArgb(245,248,250);
        commandOutput.Text="可输入 进度、版本、保电状态、帮助，按回车发送。回复保留在这里及监控日志。\n";
        commandInput.KeyDown+=(s,e)=>{if(e.KeyCode==Keys.Enter){e.SuppressKeyPress=true;SubmitCommand();}};
        commandPanel.Controls.Add(commandOutput);commandPanel.Controls.Add(entry);
        Controls.Add(pad); Controls.Add(commandPanel); Controls.Add(stat); Controls.Add(top);

        // SAM | 2026-11-10 +08:00 | Finish releasing workers/serial ports before closing or allowing another session.
        FormClosing += (s, e) => {
            if (commandBusy && !running) { e.Cancel=true; Warn("查询正在结束，请稍候关闭"); return; }
            if (checking) { e.Cancel = true; Warn("硬件或版本检查尚未结束，请稍后关闭"); return; }
            if (!running && !stopping && hold.Owned) { e.Cancel = true; ReleaseHoldAsync(true); return; }
            if (running || stopping) { e.Cancel = true; closeAfterStop = true; Stop(); }
        };
        cbGr.SelectedIndexChanged += (s, e) => InvalidateCheck();
        chkKeep.CheckedChanged += (s, e) => { InvalidateCheck(); if(!chkKeep.Checked && hold.Owned && !checking && !running) ReleaseHoldAsync(false); };
        chkJlink.CheckedChanged += (s, e) => InvalidateCheck();
        Shown += (s, e) => { FillPorts(); Say("用法：① 检查硬件，按提示接好、关掉占口的程序 → ② 开始监控 → 核对现有任务，确认无在途/暂停事务后再推送。勾选保电后，在检查硬件时申请真实保电并核对确认。", Color.DimGray); };
    }

    void CommandReply(string message)
    {
        Info("[查询] "+message);
        Ui(()=>{commandOutput.AppendText(DateTime.Now.ToString("HH:mm:ss")+" "+message+"\n");commandOutput.SelectionStart=commandOutput.TextLength;commandOutput.ScrollToCaret();});
    }
    void SubmitCommand()
    {
        string command=MonitorCommands.Normalize(commandInput.Text);
        if(command==""){CommandReply("支持 进度、版本、保电状态、帮助");return;}
        commandInput.Clear();
        if(command=="帮助"){CommandReply("进度 汇总GR/Boot/CAT1并查询状态；版本 查询两端实际版本；保电状态 查询GR保持锁。时间表示最后一次观察。");return;}
        CommandReply("收到 "+command+"，当前已知记录\n"+evidence.Summary);
        if(commandBusy||checking||stopping){CommandReply("设备接口正忙，本次仅返回已有记录，请稍后重试");return;}
        string gr=GrCom(); bool monitor=running; string jl=chkJlink.Checked?Hw.JLinkExe():null;
        if(gr==null){CommandReply("未选择GR串口，无法查询新数据");return;}
        if(logDir==null){logDir=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"logs","query_"+DateTime.Now.ToString("yyyyMMdd_HHmmss_fff"));Directory.CreateDirectory(logDir);evLog=Path.Combine(logDir,"监控记录.txt");grRaw=Path.Combine(logDir,"gr_serial.txt");}
        commandBusy=true;commandSend.Enabled=false;
        if(!monitor){checking=true;btnCheck.Enabled=btnStart.Enabled=btnVer.Enabled=false;cbGr.Enabled=chkKeep.Enabled=chkJlink.Enabled=false;}
        commandThread=new Thread(()=>{
            try {
                foreach(string request in MonitorCommands.Queries(command)) {
                    if(monitor&&!running) break;
                    string reply;int rc=GrAsk(gr,request,request=="cat_at AT_INFO"?4000:2000,out reply);
                    if(rc!=0){CommandReply("串口查询失败，"+reply);break;}
                    evidence.Observe(reply);if(reply.Length>0)evidence.Seen("GR串口");
                    CommandReply(request+"\n"+(string.IsNullOrWhiteSpace(reply)?"本次等待未收到回应":reply.Trim()));
                }
                if(command=="进度"&&jl!=null) {
                    if(monitor&&running){Interlocked.Exchange(ref requestedOwnerReport,1);progressRefresh.Set();}
                    else if(!monitor){var state=GrProbe.Read(jl,Path.Combine(logDir,"query_jlink_"+Guid.NewGuid().ToString("N")));evidence.Owner(state);}
                }
                CommandReply("本次查询后汇总\n"+evidence.Summary);
            } catch(Exception ex){CommandReply("查询未完成，"+ex.Message);}
            finally {Ui(()=>{commandBusy=false;commandSend.Enabled=true;if(!monitor){checking=false;btnCheck.Enabled=btnVer.Enabled=true;btnStart.Enabled=hardwareReady;cbGr.Enabled=chkKeep.Enabled=chkJlink.Enabled=true;}});}
        }){IsBackground=true};commandThread.Start();
    }

    FlowLayoutPanel Flow() { return new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill, WrapContents = true, Margin = new Padding(0) }; }
    Label L(string t) { return new Label { Text = t, AutoSize = true, Margin = new Padding(3, 7, 3, 3) }; }
    void Btn(Button b, string t, Action a) { b.Text = t; b.AutoSize = true; b.Padding = new Padding(8, 3, 8, 3); b.Margin = new Padding(3, 3, 8, 3); b.Click += (s, e) => a(); }
    void AddStat(TableLayoutPanel t, string name, Label v)
    {
        var n = new Label { Text = name + "：", AutoSize = true, Margin = new Padding(3, 4, 6, 4), ForeColor = Color.DimGray };
        v.AutoSize = true; v.Margin = new Padding(3, 4, 3, 4); v.MaximumSize = new Size(950, 0);
        t.Controls.Add(n); t.Controls.Add(v);
    }

    void Ui(Action a) { if (IsDisposed) return; if (InvokeRequired) { try { BeginInvoke(a); } catch { } } else a(); }

    void Say(string msg, Color c)
    {
        string line = DateTime.Now.ToString("HH:mm:ss") + "  " + msg;
        if (evLog != null) try { File.AppendAllText(evLog, line + Environment.NewLine, Encoding.UTF8); } catch { }
        Ui(() => { box.SelectionStart = box.TextLength; box.SelectionColor = c; box.AppendText(line + "\n"); box.ScrollToCaret(); });
    }
    void Ok(string m) { Say("✔ " + m, Color.ForestGreen); }
    void Bad(string m) { Say("✘ " + m, Color.Firebrick); }
    void Warn(string m) { Say("! " + m, Color.DarkOrange); }
    void Info(string m) { Say(m, Color.Black); }

    void FillPorts()
    {
        var ps = Hw.Ports(); var cand = Hw.GrCandidates(ps);
        string keep = cbGr.SelectedItem as string;
        cbGr.Items.Clear();
        foreach (var p in cand) cbGr.Items.Add(p.Com + "  " + p.Name);
        if (keep != null && cbGr.Items.Contains(keep)) cbGr.SelectedItem = keep;
        else if (cbGr.Items.Count > 0) cbGr.SelectedIndex = 0;
    }

    string GrCom() { var s = cbGr.SelectedItem as string; return s == null ? null : s.Split(' ')[0]; }

    // ---------- ① 检查硬件 ----------
    void InvalidateCheck()
    {
        if (running || stopping || checking) return;
        hardwareReady = false; btnStart.Enabled = false;
    }

    void Check()
    {
        if (running || stopping || checking) { Warn("正在监控或释放资源，请结束后再检查"); return; }
        hardwareReady = false; checking = true;
        bool useJ = chkJlink.Checked, keep = chkKeep.Checked;
        btnCheck.Enabled = btnStart.Enabled = btnVer.Enabled = false;
        cbGr.Enabled = chkKeep.Enabled = chkJlink.Enabled = false;
        new Thread(() => {
            try { hardwareReady = DoCheck(useJ, keep); }
            catch (Exception e) { Bad("硬件检查失败：" + e.Message); }
            finally { Ui(() => {
                checking = false; btnCheck.Enabled = btnVer.Enabled = true;
                cbGr.Enabled = chkKeep.Enabled = chkJlink.Enabled = true;
                btnStart.Enabled = hardwareReady;
            }); }
        }) { IsBackground = true }.Start();
    }

    bool DoCheck(bool useJ, bool keep)
    {
        logDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "logs", "hardware_check_" + DateTime.Now.ToString("yyyyMMdd_HHmmss_fff") + "_" + Guid.NewGuid().ToString("N").Substring(0, 6));
        Directory.CreateDirectory(logDir);
        evLog = Path.Combine(logDir, "监控记录.txt"); grRaw = Path.Combine(logDir, "gr_serial.txt");
        Info("—— 检查硬件 —— 日志：" + logDir);
        var ps = Hw.Ports();
        Info("电脑上的串口：" + (ps.Count == 0 ? "一个都没有" : string.Join("；", ps.Select(p => p.Com + " " + p.Name).ToArray())));
        int fail = 0; bool grResponded = false;
        var tools = Hw.RunningTools();
        if (tools.Length > 0) Warn("这些程序开着：" + string.Join("、", tools) + "。它们可能占着串口或 J-Link；下面哪个口被占用，就关掉对应的程序（Luatools 刷机时要关掉本工具）");

        // 1) J-Link
        string jl = Hw.JLinkExe();
        if (!useJ) Info("J-Link：本次未启用 GR Flash 记录读取");
        else if (jl == null) { Bad("J-Link：电脑上没装 J-Link 软件（SEGGER），看不到 GR 进度。装好 J-Link 驱动，或取消勾选「用 J-Link 读 GR 进度」"); fail++; }
        else if (!Hw.UsbPresent(Hw.JLINK)) { Bad("J-Link：USB 上没有 J-Link。接上 J-Link 的 USB，SWD 线接到 GR 板子"); fail++; }
        else
        {
            var st = GrProbe.Read(jl, Path.Combine(logDir, "jlink"));
            if (st.Ok) Ok("J-Link：连上了 GR，只读。当前 GR 的 OTA 记录：" + st.Text);
            else { Bad("J-Link：" + st.Error + "。关掉 J-Flash / Keil 调试 / J-Link 烧录工具后再试"); fail++; }
        }

        // 2) GR 调试串口
        var cand = Hw.GrCandidates(ps);
        Ui(FillPorts);
        Thread.Sleep(300);
        string gr = (string)Invoke(new Func<string>(GrCom));
        if (cand.Count == 0) { Bad("GR 调试串口：没找到。接上 GR 的 USB 转串口线（台架上是 CH340，口号会变）"); fail++; }
        else
        {
            if (cand.Count > 1) Warn("找到多个可能的 GR 口：" + string.Join("、", cand.Select(p => p.Com).ToArray()) + "，请在「GR 调试串口」里选对");
            if (gr != null)
            {
                string reply;
                int r = GrAsk(gr, "fw_version", 2500, out reply);
                if (r == 1) { Bad("GR 调试串口 " + gr + "：被别的程序占用。关掉 Luatools、串口助手，或停掉别的监控/保电脚本"); fail++; }
                else if (r == 2) { Bad("GR 调试串口 " + gr + "：打不开（" + reply + "）"); fail++; }
                else
                {
                    var m = Regex.Match(reply, @"\[FW_VERSION\] YP001_FW\|GR5526\|(\d{3}\.\d{3}\.\d{3})\|(\d+)");
                    grResponded = m.Success;
                    evidence.Observe(reply);
                    if (m.Success) Ok("GR 调试串口 " + gr + "：GR 有回应，版本 " + Norm(m.Groups[1].Value) + " build " + m.Groups[2].Value);
                    // SAM | 2026-11-10 +08:00 | Opening a port does not prove a running GR or a usable command path.
                    else { Bad("GR 调试串口 " + gr + "：能打开，但没有 GR 版本回应。核对串口、115200 波特率和 GR 运行状态后重新检查"); fail++; }
                }
            }
        }

        // SAM | 2026-11-10 +08:00 | Acquire before requiring CAT1 USB, so an unpowered CAT1 cannot deadlock the check.
        if(hold.Owned && holdCom != gr && !ReleaseHold()) { Bad("旧串口保电未释放，不能切换设备"); return false; }
        if(keep && (!grResponded || ps.Any(p=>p.Vid==Hw.CAT1_DL))) {
            Bad("GR运行未确认或CAT1在下载模式，未执行启动/保电操作");
            Ui(() => lblHold.Text="启动保电未执行：请先确认GR运行及CAT1非下载模式"); fail++;
        }
        if(keep && gr != null && grResponded && !ps.Any(p=>p.Vid==Hw.CAT1_DL))
        {
            holdCom=gr;
            Cat1Startup startup;
            if(!startups.TryGetValue(gr,out startup)) { startup=new Cat1Startup();startups.Add(gr,startup); }
            Ui(() => lblHold.Text="正在核对CAT1启动与保电，请稍候…");
            bool active=startup.Start((command,ms)=>{
                string reply;int rc=GrAsk(gr,command,ms,out reply);evidence.Observe(reply);
                return rc==0?reply:"";
            },Thread.Sleep,hold,ps.Any(p=>p.Vid==Hw.CAT1||p.Vid==Hw.CAT1_DL));
            Ui(() => lblHold.Text=startup.Status);
            if(active) Ok(startup.Status);else { Bad(startup.Status);fail++; }
            ps=Hw.Ports();
        }
        // 3) CAT1 USB
        if (ps.Any(p => p.Vid == Hw.CAT1_DL) || Hw.UsbPresent(Hw.CAT1_DL))
        { Bad("CAT1 USB：CAT1 现在在下载模式（Luatools 正在刷或刚刷完）。等刷完、CAT1 重启后再开始监控"); fail++; }
        var beacon = Hw.Cat1BeaconPorts(ps);
        if (beacon.Count == 0)
        {
            Bad("CAT1 USB：没有发现信标口。请先确认 CAT1 已实际启动、接好 USB，再重新检查"); fail++;
        }
        else
        {
            foreach (var c in beacon)
            {
                string e; int r = Hw.TryOpen(c, out e);
                if (r == 0) Ok("CAT1 USB " + c + "：能打开（OTA 信标口" + (c == beacon[0] ? "" : "，备用") + "）");
                else if (r == 1) { Bad("CAT1 USB " + c + "：被占用。关掉 Luatools 的日志/串口窗口，或其他打开 " + c + " 的程序"); fail++; }
                else { Bad("CAT1 USB " + c + "：打不开（" + e + "）"); fail++; }
            }
            var trace = ps.Where(p => p.Vid == Hw.CAT1 && p.Mi == "04").Select(p => p.Com).FirstOrDefault();
            if (trace != null) Info("    " + trace + " 是 CAT1 的二进制跟踪口，本工具不打开，也不要用别的程序抓它");
        }

        if (fail == 0) { Ok("连接检查通过，可以开始监控；先核对现有 OTA 状态，再决定是否推送"); Ui(() => lblState.Text = "硬件检查通过"); }
        else { Bad("有 " + fail + " 项要处理，按上面的提示接好或关掉占用的程序，再点「① 检查硬件」"); Ui(() => lblState.Text = "硬件检查没通过：" + fail + " 项"); }
        return fail == 0;
    }

    static bool TryVersion(string value, out string normalized)
    {
        normalized = "";
        var match = Regex.Match(value ?? "", @"^(\d+)\.(\d+)\.(\d+)$");
        uint major, minor, patch;
        if (!match.Success || !uint.TryParse(match.Groups[1].Value, out major) ||
            !uint.TryParse(match.Groups[2].Value, out minor) || !uint.TryParse(match.Groups[3].Value, out patch) ||
            major > 999 || minor > 999 || patch > 999) return false;
        normalized = major + "." + minor + "." + patch; return true;
    }

    static string Norm(string value)
    {
        string normalized; return TryVersion(value, out normalized) ? normalized : value;
    }

    // SAM | 2026-11-10 +08:00 | Record success and actual running versions are separate evidence; require both before a green completion.
    internal static bool VersionsMatch(string gr, string cat1, string expected)
    {
        string g, c, e;
        return TryVersion(gr, out g) && TryVersion(cat1, out c) && TryVersion(expected, out e) && g == e && c == e;
    }

    internal static bool SuccessRecord(OwnerState state)
    {
        return state.Ok && state.Phase == "COMPLETE" && state.Target == "CAT1" && state.Outcome == "success" &&
            state.Boot == "CONFIRMED" && state.Epoch > 0 && state.Epoch < uint.MaxValue &&
            Regex.IsMatch(state.Job, "^[0-9a-fA-F]{64}$") && Regex.IsMatch(state.Hash, "^[0-9a-fA-F]{64}$") &&
            state.Job.Any(c => c != '0') && state.Hash.Any(c => c != '0') &&
            VersionsMatch(state.Version, state.Actual, state.Version);
    }

    internal static bool SameCompletedTask(OwnerState expected, OwnerState current)
    {
        return SuccessRecord(expected) && SuccessRecord(current) && current.Generation >= expected.Generation &&
            expected.Job == current.Job && expected.Hash == current.Hash && expected.Epoch == current.Epoch &&
            VersionsMatch(expected.Version, current.Version, expected.Version);
    }

    // 在 GR 口上发一条命令并收回复；监控中用保电线程的那个口
    int GrAsk(string com, string cmd, int ms, out string reply)
    {
        reply = "";
        lock (grLock)
        {
            SerialPort s = grPort; bool own = false;
            try
            {
                if (s == null) { s = new SerialPort(com, 115200) { Encoding = Encoding.UTF8, ReadTimeout = 200 }; s.Open(); own = true; Thread.Sleep(200); s.ReadExisting(); }
                s.Write(cmd + "\r\n");
                var sb = new StringBuilder(); var end = DateTime.Now.AddMilliseconds(ms);
                while (DateTime.Now < end) { Thread.Sleep(100); sb.Append(s.ReadExisting()); }
                reply = sb.ToString();
                if (grRaw != null) try { File.AppendAllText(grRaw, ">>> " + cmd + "\n" + reply, Encoding.UTF8); } catch { }
                return 0;
            }
            catch (UnauthorizedAccessException) { return 1; }
            catch (Exception e) { reply = e.Message; return 2; }
            finally { if (own && s != null) try { s.Close(); } catch { } }
        }
    }
    string HoldAsk(string command)
    {
        string reply; int result=GrAsk(holdCom,command,2000,out reply);
        return result==0 ? reply : "";
    }
    bool ReleaseHold()
    {
        bool owned=hold.Owned; bool ok=hold.Release(HoldAsk);
        if(owned) {
            if(ok) Info("已确认释放本工具保电，恢复设备正常策略；没有发送断电命令");
            else Warn("本工具保电释放未确认，请保持连接重新检查/关闭以重试");
        }
        Ui(() => lblHold.Text=ok ? "本工具未持有保电；已有其他来源保电不清除" : "释放未确认，请保持GR串口连接");
        return ok;
    }
    void ReleaseHoldAsync(bool close)
    {
        if(checking) return;
        checking=true; btnCheck.Enabled=btnStart.Enabled=btnVer.Enabled=false;
        cbGr.Enabled=chkKeep.Enabled=chkJlink.Enabled=false;
        new Thread(() => {
            bool ok=ReleaseHold();
            Ui(() => { checking=false; hardwareReady=false; btnCheck.Enabled=btnVer.Enabled=true;
                cbGr.Enabled=chkKeep.Enabled=chkJlink.Enabled=true;
                if(close && ok) Close();
            });
        }) { IsBackground=true }.Start();
    }
    string grRaw;

    // ---------- 读设备版本 ----------
    void ReadVersion()
    {
        if (running || stopping || checking) return;
        string gr = GrCom();
        if (gr == null) { Bad("没有选 GR 调试串口，先点「① 检查硬件」"); return; }
        checking = true; hardwareReady = false;
        btnVer.Enabled = btnStart.Enabled = btnCheck.Enabled = false;
        cbGr.Enabled = chkKeep.Enabled = chkJlink.Enabled = false;
        new Thread(() => {
            try { DoReadVersion(gr); }
            finally { Ui(() => {
                checking = false; btnVer.Enabled = btnCheck.Enabled = true;
                cbGr.Enabled = chkKeep.Enabled = chkJlink.Enabled = true;
            }); }
        }) { IsBackground = true }.Start();
    }

    bool DoReadVersion(string gr, string expected = null)
    {
        string a, b;
        int r = GrAsk(gr, "fw_version", 2500, out a);
        if (r != 0) { Bad("GR 口 " + gr + (r == 1 ? " 被占用，关掉占用它的程序" : " 打不开：" + a)); return false; }
        GrAsk(gr, "cat_at AT_INFO", 6000, out b);
        var m1 = Regex.Match(a, @"\[FW_VERSION\] YP001_FW\|GR5526\|(\d{3}\.\d{3}\.\d{3})\|(\d+)");
        var m2 = Regex.Match(b, @"LuatOS Ver:\s+(\d{3}\.\d{3}\.\d{3})");
        var m3 = Regex.Match(b, @"IMEI:\s+(\d+)");
        string g = m1.Success ? Norm(m1.Groups[1].Value) + " build " + m1.Groups[2].Value : "没读到";
        string c = m2.Success ? Norm(m2.Groups[1].Value) : "没读到（CAT1 可能没开机，开着保电再读一次）";
        evidence.Observe(a); evidence.Observe(b);
        Info("设备版本：GR " + g + "；CAT1 " + c + (m3.Success ? "；IMEI " + m3.Groups[1].Value : ""));
        return m1.Success && m2.Success && (expected == null || VersionsMatch(m1.Groups[1].Value, m2.Groups[1].Value, expected));
    }

    void OpenFolder()
    {
        string d = logDir ?? Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "logs");
        Directory.CreateDirectory(d);
        Process.Start("explorer.exe", "\"" + d + "\"");
    }

    // ---------- ② 开始监控 ----------
    void Start()
    {
        if (running || stopping || checking) return;
        if (chkKeep.Checked && !hold.Confirmed) { Bad("保电尚未确认，请重新检查硬件"); return; }
        if (!hardwareReady) { Bad("请先完成「① 检查硬件」，处理未通过项目后再开始"); return; }
        string gr = GrCom();
        bool keep = chkKeep.Checked, useJ = chkJlink.Checked;
        if (gr == null && keep) { Bad("没有选 GR 调试串口，不能保电。先点「① 检查硬件」，或取消「保持 CAT1 供电」"); return; }
        string jl = useJ ? Hw.JLinkExe() : null;
        if (useJ && jl == null) { Bad("没找到 J-Link 软件；装好，或取消勾选「用 J-Link 读 GR 进度」"); return; }

        logDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "logs", "ota_monitor_" + DateTime.Now.ToString("yyyyMMdd_HHmmss_fff") + "_" + Guid.NewGuid().ToString("N").Substring(0, 6));
        Directory.CreateDirectory(logDir);
        evLog = Path.Combine(logDir, "监控记录.txt"); grRaw = Path.Combine(logDir, "gr_serial.txt");
        evidence = new MonitorEvidence();
        running = true; done = false; gotRx = false; existingTask = false; startGenKnown = false; t0 = DateTime.Now; nextWarn = t0.AddSeconds(120);
        int maxMin = (int)numMin.Value;
        btnStart.Enabled = false; btnStop.Enabled = true; btnCheck.Enabled = false; btnVer.Enabled = false; cbGr.Enabled = false; chkKeep.Enabled = false; chkJlink.Enabled = false;
        lblState.Text = "监控中（最长 " + maxMin + " 分钟）：先核对现场 OTA 状态"; lblPush.Text = "等推送到达设备…"; lblGr.Text = useJ ? "读取中…" : "未启用"; lblCat.Text = "等 CAT1 的口…";
        Info("—— 开始监控 —— 日志：" + logDir);
        Info("先核对现有任务和两端版本；设备无在途/暂停事务时再发起新任务。收到新推送后会显示 [OTA_RX]。");

        progressRefresh.Reset(); Interlocked.Exchange(ref requestedOwnerReport,0);
        workers.Clear();
        if (gr != null) workers.Add(new Thread(() => GrWorker(gr, keep)) { IsBackground = true });
        workers.Add(new Thread(Cat1Worker) { IsBackground = true });
        if (useJ) workers.Add(new Thread(() => JWorker(jl)) { IsBackground = true });
        workers.Add(new Thread(() => Watchdog(maxMin)) { IsBackground = true });
        foreach (var t in workers) t.Start();
    }

    void Stop()
    {
        if (!running || stopping) return;
        stopping = true; running = false; progressRefresh.Set(); hardwareReady = false;
        btnStart.Enabled = btnStop.Enabled = btnCheck.Enabled = btnVer.Enabled = false;
        Info("正在停止监控并释放串口/J-Link，请稍候…");
        var currentWorkers = workers.ToArray();
        new Thread(() => {
            foreach (var worker in currentWorkers) if (worker.IsAlive) worker.Join();
            var query=commandThread; if(query!=null && query.IsAlive) query.Join();
            ReleaseHold();
            Ui(() => {
                workers.Clear(); stopping = false;
                btnCheck.Enabled = btnVer.Enabled = true;
                cbGr.Enabled = chkKeep.Enabled = chkJlink.Enabled = true;
                Info("—— 监控已停止 —— 串口和 J-Link 线程已释放。日志：" + logDir);
                if (!done) lblState.Text = "已停止，请重新检查硬件";
                if (closeAfterStop) { closeAfterStop=false; if(!hold.Owned) Close(); else Warn("保电释放未确认，窗口保留以便重试；不要直接拔电"); }
            });
        }) { IsBackground = true }.Start();
    }

    void Watchdog(int maxMin)
    {
        while (running)
        {
            Thread.Sleep(1000);
            if (!gotRx && !existingTask && DateTime.Now > nextWarn)
            {
                Warn((int)(DateTime.Now - t0).TotalSeconds + " 秒了，设备还没收到推送（没有 [OTA_RX]）：查后台推送状态、IMEI、目标版本是否比设备高；已经 ACCEPTED 过的不要重复推");
                nextWarn = DateTime.Now.AddMinutes(5);
            }
            if ((DateTime.Now - t0).TotalMinutes > maxMin)
            {
                Bad("到了最长时间 " + maxMin + " 分钟，还没看到 OTA 走完。看日志文件夹里的 cat1_beacon.txt 最后几行，或把截图发给开发");
                Ui(() => lblState.Text = "超时，没看到走完");
                Ui(Stop); return;
            }
        }
    }

    void RxSeen(string line)
    {
        var m = Regex.Match(line, @"\[OTA_RX\]\s*(\S+)(.*)");
        string what = m.Success ? m.Groups[1].Value + m.Groups[2].Value : line;
        gotRx = true;
        if (what.StartsWith("ACCEPTED")) { Ok("设备收到推送并接受：[OTA_RX] " + what.Trim()); Ui(() => lblPush.Text = "已收到并接受（ACCEPTED）"); }
        else if (what.StartsWith("REJECT")) { Bad("设备拒绝了这次推送：[OTA_RX] " + what.Trim() + "  —— 常见原因：源版本不等于设备当前版本、目标不比设备高、包是旧工具打的"); Ui(() => lblPush.Text = "被拒绝：" + what.Trim()); }
        else { Warn("[OTA_RX] " + what.Trim()); Ui(() => lblPush.Text = what.Trim()); }
    }

    // SAM | 2026-11-10 +08:00 | Surface the actual SPENT/NACK evidence instead of advising another push while a task is paused.
    internal static string OtaRisk(string line)
    {
        if (line.Contains("TRIAL_SPENT") || line.Contains("TRIAL=SPENT"))
            return "票据已消耗（SPENT），请结合当前事务阶段、job/hash/epoch 和 Boot 判断；此字段单独不代表失败";
        var reason = Regex.Match(line, @"OTA_REASON=(GR_NACK_\d+|ACTIVATION_RECHECK_FAILED|boot_commit_failed)");
        return reason.Success ? "检测到 OTA 暂停原因 " + reason.Groups[1].Value + "，请保留日志核对设备事务" : "";
    }

    // SAM | 2026-11-10 +08:00 | Status query every 10 s, observed-version queries once per minute when enabled; never power-cycle the device.
    void GrWorker(string com, bool keep)
    {
        string lastRx = "", lastRisk = "", partial = ""; int queryCycle = 0;
        while (running)
        {
            try
            {
                var s = new SerialPort(com, 115200) { Encoding = Encoding.UTF8, ReadTimeout = 200 };
                s.Open();
                lock (grLock) grPort = s;
                Info("GR 口 " + com + " 已打开" + (keep ? "，定期发送状态查询，保电效果需核对设备回应" : "（只读，不保电）"));
                try
                {
                    while (running)
                    {
                        string buf;
                        lock (grLock)
                        {
                            if (keep) {
                                s.Write("at FOTA_STATUS\r\n");
                                if(queryCycle % 6 == 0) s.Write("fw_version\r\n");
                                if(queryCycle % 6 == 2) s.Write("cat1_power status\r\n");
                                if(queryCycle % 6 == 1) s.Write("cat_at AT_INFO\r\n");
                                queryCycle++;
                            }
                            buf = "";
                        }
                        var end = DateTime.Now.AddSeconds(10);
                        var sb = new StringBuilder();
                        while (running && DateTime.Now < end) { Thread.Sleep(200); lock (grLock) sb.Append(s.ReadExisting()); }
                        buf = sb.ToString();
                        try { File.AppendAllText(grRaw, "--- " + DateTime.Now.ToString("HH:mm:ss") + "\n" + buf, Encoding.UTF8); } catch { }
                        if(buf.Length > 0) evidence.Seen("GR串口");
                        partial += buf;
                        int lastNewline = partial.LastIndexOf('\n');
                        string complete = lastNewline < 0 ? "" : partial.Substring(0, lastNewline + 1);
                        partial = lastNewline < 0 ? partial : partial.Substring(lastNewline + 1);
                        if(partial.Length > 8192) partial = "";
                        foreach (var ln in complete.Split('\n'))
                        {
                            evidence.Observe(ln);
                            if(ln.Contains("[CAT1 POWER] rail_request=") && ln.Contains("factory_hold=")) {
                                bool held=ln.Contains("factory_hold=1;"); if(!held) hold.Invalidate();
                                Ui(() => lblHold.Text=held ? "GR 状态确认保电（" + DateTime.Now.ToString("HH:mm:ss") + "）；CAT1 启动另行核对" : "当前保电未生效（可能已重启/释放），请重新检查；不会自动强制上电");
                            }
                            if(ln.Contains("=== YP001 GR5526 BOOT")) { hold.Invalidate(); Ui(() => lblHold.Text="GR 已重启，原保电状态失效，请重新检查"); }
                            string risk = OtaRisk(ln);
                            if (risk != "" && risk != lastRisk)
                            {
                                lastRisk = risk; existingTask = true; Warn(risk);
                                Ui(() => { lblState.Text = "检测到事务提示，请查看设备诊断与 Boot 状态"; lblPush.Text = "已有任务，请核对任务身份"; });
                            }
                            if (ln.Contains("OTA_PROGRESS=") && Regex.IsMatch(ln, @"OTA_PROGRESS=\S+:[1-9]\d*/")) existingTask = true;
                            if (ln.Contains("[CAT1 RX] [OTA_RX]") && !ln.Contains("parse"))
                            { var t = ln.Trim(); if (t != lastRx) { lastRx = t; RxSeen(t); } }
                        }
                        if (keep && buf.LastIndexOf("rail_request=off") > buf.LastIndexOf("rail_request=on"))
                        {
                            // SAM | 2026-11-10 +08:00 | OTA monitoring must not blindly pulse PWRKEY during install/reset recovery.
                            Warn("检测到 CAT1 供电状态变化，请核对实际启动及 OTA 阶段；安装中请保留现场");
                        }
                    }
                }
                finally { lock (grLock) { grPort = null; try { s.Close(); } catch { } } }
            }
            catch (UnauthorizedAccessException) { Bad("GR 口 " + com + " 被别的程序占用，5 秒后重试。关掉占用它的程序"); Sleep(5000); }
            catch (Exception e) { if (running) { hold.Invalidate(); Ui(() => lblHold.Text="GR串口失联，当前保电状态未知"); Warn("GR 口 " + com + " 断开（" + e.Message + "），5 秒后重连"); Sleep(5000); } }
        }
    }

    void Sleep(int ms) { var end = DateTime.Now.AddMilliseconds(ms); while (running && DateTime.Now < end) Thread.Sleep(100); }

    // SAM | 2026-11-10 +08:00 | update.lua native_diag has variable-width fields; parse N/S/P markers instead of fixed indexes.
    internal static Cat1Beacon ParseBeacon(string line)
    {
        var match = Regex.Match(line ?? "", @"\[OTA\]\s+B\s+(\S+)\s+\S+\s+(\S+)\s+(\S+)\s+N\s+(.+?)\s+S\s+(.+?)\s+P\s+(\S+)");
        if (!match.Success) return null;
        return new Cat1Beacon { Phase = match.Groups[1].Value, Ticket = match.Groups[2].Value,
            Reason = match.Groups[3].Value, Native = match.Groups[4].Value, Step = match.Groups[5].Value, Progress = match.Groups[6].Value };
    }

    // CAT1 USB：读 OTA 信标，只在阶段变化时显示；CAT1 重启后口会消失再出现，自动重连
    void Cat1Worker()
    {
        string beaconLog = Path.Combine(logDir, "cat1_beacon.txt");
        string lastKey = null; bool warnedMissing = false;
        var open = new Dictionary<string, SerialPort>(); var part = new Dictionary<string, string>();
        DateTime nextScan = DateTime.MinValue;
        try
        {
            while (running)
            {
                if (DateTime.Now > nextScan)
                {
                    nextScan = DateTime.Now.AddSeconds(3);
                    var want = Hw.Cat1BeaconPorts(Hw.Ports());
                    if (want.Count == 0 && open.Count == 0 && !warnedMissing && (DateTime.Now - t0).TotalSeconds > 60)
                    { Warn("1 分钟了还看不到 CAT1 的 USB 口：检查 CAT1 的 USB 线；同时核对 GR 安装状态与 CAT1 实际供电，不能仅凭失联认定正常"); warnedMissing = true; }
                    foreach (var c in want)
                    {
                        if (open.ContainsKey(c)) continue;
                        try
                        {
                            var s = new SerialPort(c, 115200) { Encoding = Encoding.UTF8, ReadTimeout = 100 }; s.Open();
                            open[c] = s; part[c] = ""; warnedMissing = false;
                            Info("CAT1 口 " + c + " 已连上"); Ui(() => { if (lblCat.Text.StartsWith("等")) lblCat.Text = "已连上，等信标…"; });
                        }
                        catch (UnauthorizedAccessException) { Warn("CAT1 口 " + c + " 被占用（关掉 Luatools 日志窗口），稍后重试"); }
                        catch { }
                    }
                }
                foreach (var c in open.Keys.ToList())
                {
                    string data;
                    try { data = open[c].ReadExisting(); }
                    catch
                    {
                        try { open[c].Close(); } catch { }
                        open.Remove(c); Info("CAT1 口 " + c + " 断开（CAT1 重启或断电，正常情况下会自己回来）");
                        Ui(() => lblCat.Text = "CAT1 断开，等它回来…"); continue;
                    }
                    if (data.Length == 0) continue;
                    part[c] += data;
                    int nl;
                    while ((nl = part[c].IndexOf('\n')) >= 0)
                    {
                        string ln = part[c].Substring(0, nl).TrimEnd('\r'); part[c] = part[c].Substring(nl + 1);
                        if (ln.Length == 0) continue;
                        try { File.AppendAllText(beaconLog, DateTime.Now.ToString("HH:mm:ss") + " " + c + " " + ln + "\n", Encoding.UTF8); } catch { }
                        evidence.Observe(ln);
                        if (ln.Contains("[OTA_RX]")) { RxSeen(ln); continue; }
                        int k = ln.IndexOf("[OTA] B ");
                        if (k >= 0)
                        {
                            var beacon = ParseBeacon(ln.Substring(k));
                            if (beacon != null) evidence.Seen("CAT1信标");
                            if (beacon != null && beacon.Key != lastKey)
                            {
                                lastKey = beacon.Key; evidence.Seen("阶段变化");
                                evidence.Observe("OTA_PROGRESS="+beacon.Progress); evidence.Observe("OTA_STEP="+beacon.Step);
                                evidence.Observe("[FOTA_STATUS] " + beacon.Phase); evidence.Observe("OTA_REASON=" + beacon.Reason);
                                if (beacon.Phase != "IDLE") existingTask = true;
                                if (beacon.Phase == "PAUSED" && beacon.Ticket == "SPENT")
                                {
                                    Bad("CAT1 任务 PAUSED / SPENT，保留现场核对任务身份、Boot 和原因 " + beacon.Reason);
                                    Ui(() => lblState.Text = "OTA 暂停且票据已消耗，请核对现场");
                                }
                                string show = beacon.Text;
                                Say("CAT1  " + show + "  —— " + Explain(beacon.Phase, beacon.Reason), Color.Navy);
                                Ui(() => lblCat.Text = show);
                            }
                            continue;
                        }
                        if (Regex.IsMatch(ln, "SNAPSHOT|ERROR|traceback|REFUSED|REJECT|DATA_EVIDENCE"))
                            Warn("CAT1  " + (ln.Length > 160 ? ln.Substring(0, 160) : ln));
                    }
                }
                Thread.Sleep(150);
            }
        }
        finally { foreach (var s in open.Values) try { s.Close(); } catch { } }
    }

    static string Explain(string ph, string reason)
    {
        if (ph == "PREPARING") return "准备或等待 GR，结合原因与进度观察";
        if (ph == "PAUSED") return "已暂停，核对原因 " + reason + " 及任务进度";
        if (ph == "WAIT_ACTIVATE") return "GR 包已下载，等待激活；是否安装成功须继续看 Boot 与设备记录";
        if (ph == "RECOVERY_HOLD") return "恢复等待，需核对 Boot、任务身份和原因 " + reason;
        if (ph == "INSTALLING") return "CAT1 正在安装，装完会重启";
        if (ph == "COMPLETE_PENDING") return "CAT1 已装完，正在向 GR 报结果";
        if (ph == "IDLE") return "空闲";
        return "";
    }

    // J-Link：每 30 秒只读一次 GR 的 OTA 记录；记下开始时的次数，只有新开的这一次到 COMPLETE / CAT1 才算走完
    void JWorker(string jl)
    {
        string work = Path.Combine(logDir, "jlink"), ownerLog = Path.Combine(logDir, "gr_owner.txt");
        string last = null; int errs = 0;
        while (running)
        {
            // SAM | 2026-11-10 +08:00 | Every read gets a unique evidence folder, including failed or torn samples; never overwrite the previous Boot/owner.
            string sample = Path.Combine(work, DateTime.Now.ToString("yyyyMMdd_HHmmss_fff") + "_" + Guid.NewGuid().ToString("N").Substring(0, 6));
            var st = GrProbe.Read(jl, sample);
            evidence.Owner(st);
            if(Interlocked.Exchange(ref requestedOwnerReport,0)==1) CommandReply("GR/Boot新读取\n"+evidence.Summary);
            if (!running) break;
            if (st.Ok)
            {
                errs = 0; evidence.Seen("J-Link有效记录");
                if (!startGenKnown)
                {
                    startGen = st.Generation; startGenKnown = true;
                    Info("GR 启动监控时的 OTA 记录：" + st.Text + "（现场基线，用于比较后续变化）");
                    if (st.Phase == "DOWNLOADING" || st.Phase == "PREPARED" || st.Phase == "INSTALL_PENDING" || st.Boot == "TRIAL")
                    {
                        existingTask = true;
                        Warn("设备已有在途或待恢复记录，请核对任务身份后继续观察");
                        Ui(() => lblPush.Text = "设备已有任务，先核对任务身份");
                    }
                }
                if (st.Key != last)
                {
                    last = st.Key; evidence.Seen("阶段变化");
                    Info("阶段快照：" + sample);
                    try { File.AppendAllText(ownerLog, DateTime.Now.ToString("HH:mm:ss") + " " + st.Text + "\n", Encoding.UTF8); } catch { }
                    bool fresh = st.Generation > startGen;
                    if (fresh) Say("GR    " + st.Text + "  —— " + GrExplain(st), Color.DarkMagenta);
                    Ui(() => lblGr.Text = st.Text + " —— " + GrExplain(st) + (fresh ? "" : "（启动时已有记录）"));
                    if (fresh && st.Phase == "COMPLETE" && st.Target == "CAT1")
                    {
                        if (st.Outcome != "success")
                        {
                            done = true; Bad("OTA 设备记录的结果为 " + st.Outcome + "，请保留现场核对");
                            Ui(() => lblState.Text = "OTA 结束：" + st.Outcome); Ui(Stop); return;
                        }
                        if (!SuccessRecord(st))
                        {
                            Warn("设备记录为 success，但 Boot、任务身份或实际版本字段尚未确认一致，继续观察");
                            Ui(() => lblState.Text = "设备记录 success，完成条件待核对");
                            Sleep(30000); continue;
                        }
                        Info("设备记录 COMPLETE / CAT1 / success，30 秒后核对两端实际版本");
                        Ui(() => lblState.Text = "设备记录 success，等待两端版本核对");
                        Sleep(30000);
                        if (!running) return;
                        string gr = null; try { gr = (string)Invoke(new Func<string>(GrCom)); } catch { }
                        bool verified = gr != null && DoReadVersion(gr, st.Version);
                        if (!running) return;
                        // SAM | 2026-11-10 +08:00 | A second task may start while versions are read; bind the final evidence to the same completed transaction.
                        if (verified)
                        {
                            var current = GrProbe.Read(jl, Path.Combine(logDir, "jlink_confirm"));
                            if (!running) return;
                            verified = SameCompletedTask(st, current);
                            Info("完成核对时的事务记录：" + current.Text);
                        }
                        done = true;
                        if (verified) Ok("设备端 OTA 完成，GR/CAT1 实际版本均为 " + st.Version);
                        else Warn("设备曾记录 success，但两端版本或当前任务身份未确认一致，请保留日志核对");
                        Ui(() => lblState.Text = verified ? "设备端 OTA 完成，版本核对通过" : "设备记录 success，版本或任务身份待核对");
                        Ui(Stop); return;
                    }
                }
            }
            else
            {
                errs++;
                if (errs == 1 || errs % 10 == 0) Warn("J-Link 读 GR 失败：" + st.Error + "（继续重试）");
                Ui(() => lblGr.Text = "读不到：" + st.Error);
            }
            progressRefresh.WaitOne(30000);
        }
    }

    internal static string GrExplain(OwnerState s)
    {
        if (s.Boot == "TRIAL") return "Boot 试运行，健康状态尚未确认，不代表双端升级完成";
        if (s.Target == "GR5526" && s.Phase == "DOWNLOADING") return "GR 正在下载自己的固件";
        if (s.Target == "GR5526" && s.Phase == "PREPARED") return "GR 固件已下载好，等安装";
        if (s.Target == "GR5526" && s.Phase == "INSTALL_PENDING") return "GR 正在安装，会重启";
        if (s.Target == "CAT1" && s.Phase == "DOWNLOADING") return "GR 已确认新固件，轮到 CAT1";
        if (s.Phase == "COMPLETE") return "记录已结束，仍须核对结果、Boot和两端实际版本";
        return "";
    }

    [STAThread]
    static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new MainForm());
    }
}
