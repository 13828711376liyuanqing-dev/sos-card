// SAM | 2026-11-01 +08:00 | YP001 GR5526 J-Link wired flashing (window). Port of yp001_gr_jlink_flash.py, bench-confirmed flow:
// read-only snapshot -> re-pair the board's Boot (40 B baseline descriptor only) -> erase Boot journal/owner and B -> write A (own
// J-Link session, then reset) -> Boot-only session(s) until SCA points at Boot -> full readback -> fw_version on COM port.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Ports;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;
using YpOta;

static class Flasher
{
    const string JLINK = @"C:\Program Files\SEGGER\JLink\JLink.exe";
    const string DEVICE = "YP001_GR5526";
    const uint FLASH_BASE = 0x200000, SNAP_SIZE = 0x100000;
    const uint A_ADDR = 0x202000, B_ADDR = 0x280000, SLOT = 0x6C000;
    const uint BOOT_ADDR = 0x2EC000, BOOT_MAX = 0xA000;
    const uint CLEAR_ADDR = 0x2F6000, CLEAR_END = 0x2FB000, NVDS_ADDR = 0x2FE000;
    const int DESC_OFF = 0x71F0, SIG_TAIL = 904;
    static readonly byte[] LAYOUT_HASH = { 0x4f, 0x46, 0xb2, 0x71, 0xbc, 0x86, 0x5a, 0x8f };
    // SAM | 2026-11-10 +08:00 | First initialization trusts the existing accepted Boot bytes and public contracts only.
    const string BOOT_SHA = "66deeecb32f168b973e750babbd9344a14a049f3ff42c0756d1ee5b5cf567b0c";
    const string PUBLIC_SHA = "6f9ff6c1e1f7d1f12e6955ad9886329563bad196dc79d32da1bb16d4d758cfe1";
    const string LAYOUT_PIN = "4f46b271bc865a8f5b1d3c74083d3645bfb8f281e0700dd29014ba6e5c6fb527";
    const string DATA_PIN = "1c5ef5151909da84307b9f6ba894fbaee1250c21d43377f3c8a094e3e4e6a50c";
    static string probeSerial;
    static bool holdForInitialization;
#if FLASH_TEST
    internal static Func<bool, IEnumerable<string>, string, int, string> TestJLink;
#endif
    const string XML = "<DataBase>\r\n  <Device>\r\n    <ChipInfo Vendor=\"Goodix\" Name=\"YP001_GR5526\" Core=\"JLINK_CORE_CORTEX_M4\" WorkRAMAddr=\"0x20000000\" WorkRAMSize=\"0x8000\" />\r\n" +
        "    <FlashBankInfo Name=\"Flash\" BaseAddr=\"0x00200000\" MaxSize=\"0x01000000\" Loader=\"GR5xxx_16MB_Flash.FLM\" LoaderType=\"FLASH_ALGO_TYPE_OPEN\" AlwaysPresent=\"1\" />\r\n  </Device>\r\n</DataBase>\r\n";

    public static Action<string> Log = s => { };
    public class Stop : Exception { public Stop(string m) : base(m) { } }

    static string Here { get { return AppDomain.CurrentDomain.BaseDirectory; } }

    // SAM | 2026-11-05 12:12 +08:00 | Keep loader files local because Commander cannot preserve Unicode script paths.
    static string InstallDevice(string d)
    {
        Directory.CreateDirectory(d);
        string flm = Path.Combine(Here, "GR5xxx_16MB_Flash.FLM");
        if (!File.Exists(flm)) throw new Stop("缺少 GR5xxx_16MB_Flash.FLM（应与本程序放在同一文件夹）");
        string dst = Path.Combine(d, "GR5xxx_16MB_Flash.FLM");
        if (!File.Exists(dst) || !File.ReadAllBytes(dst).SequenceEqual(File.ReadAllBytes(flm))) File.Copy(flm, dst, true);
        string x = Path.Combine(d, "JLinkDevices.xml");
        if (!File.Exists(x) || File.ReadAllText(x) != XML) File.WriteAllText(x, XML, new UTF8Encoding(false));
        return d;
    }

    // SAM | 2026-11-10 +08:00 | DLL-relative XML paths miss the local loader; pass an absolute ASCII directory.
    [System.Runtime.InteropServices.DllImport("kernel32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    static extern uint GetShortPathName(string path, StringBuilder result, uint size);
    static string AsciiDirectory(string path)
    {
        path = Path.GetFullPath(path);
        if (path.All(c => c < 128)) return path;
        var result = new StringBuilder(32768);
        uint n = GetShortPathName(path, result, (uint)result.Capacity);
        return n > 0 && n < result.Capacity && result.ToString().All(c => c < 128) ? result.ToString() : null;
    }
    static string LoaderDirectory(string dir)
    {
        string path = AsciiDirectory(dir);
        if (path == null)
        {
            // No 8.3 names on this volume: keep backups in logs, stage only the public loader in TEMP.
            string temp = Path.GetTempPath();
            Directory.CreateDirectory(temp);
            temp = AsciiDirectory(temp);
            if (temp == null) throw new Stop("J-Link 无法读取此电脑的算法路径，请将工具放到纯英文路径后再试；尚未执行本次擦写。");
            path = Path.Combine(temp, "YP001_JLink_" + Guid.NewGuid().ToString("N"));
        }
        InstallDevice(path);
        return path.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
    }

    // SAM | 2026-11-05 12:12 +08:00 | Use relative ASCII operands and Unicode WorkingDirectory to support Chinese/space paths.
    static ProcessStartInfo PrepareJLink(bool gr, IEnumerable<string> cmds, string logfile)
    {
        string dir = Path.GetDirectoryName(Path.GetFullPath(logfile));
        var lines = new List<string>();
        // SAM | 2026-11-10 +08:00 | Real Commander uses the installed DLL: set XML before device selection and the first halt.
        if (holdForInitialization || gr) lines.Add("exec SetRestartOnClose = 0");
        string loader = gr ? LoaderDirectory(dir) : null;
        if (gr) { lines.Add("exec JLinkDevicesXMLPath=\"" + loader + "\""); lines.Add("device " + DEVICE); }
        if (holdForInitialization || gr) lines.Add("h");
        string prefix = dir + Path.DirectorySeparatorChar;
        lines.AddRange(cmds.Select(cmd => Regex.Replace(cmd, Regex.Escape(prefix), match => "", RegexOptions.IgnoreCase)));
        if (holdForInitialization) lines.Add("h");
        lines.Add("exit");
        string script = Path.ChangeExtension(logfile, ".jlink");
        File.WriteAllText(script, string.Join("\n", lines) + "\n", Encoding.ASCII);
        string probe = probeSerial == null ? "" : "-SelectEmuBySN " + probeSerial + " ";
        var psi = new ProcessStartInfo(JLINK, probe + "-NoGui 1 -ExitOnError 1 -device CORTEX-M4 -if SWD -speed 4000 -autoconnect 1 -Log \"" + Path.GetFileName(Path.ChangeExtension(logfile, ".sdk.log")) + "\" -CommandFile \"" + Path.GetFileName(script) + "\"")
        { WorkingDirectory = dir, UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true };
        File.WriteAllText(Path.ChangeExtension(logfile, ".runtime.txt"), "Commander=" + psi.FileName + "\r\nArguments=" + psi.Arguments +
            "\r\nRequestedDevice=" + (gr ? DEVICE : "CORTEX-M4") + "\r\nLoaderDirectory=" + loader + "\r\nWorkingDirectory=" + dir, Encoding.UTF8);
        if (gr) File.Copy(Path.Combine(loader, "JLinkDevices.xml"), Path.Combine(dir, "loader_used.xml"), true);
        return psi;
    }

    static string JLink(bool gr, IEnumerable<string> cmds, string logfile, int timeoutMs = 900000)
    {
#if FLASH_TEST
        if (TestJLink != null) return TestJLink(gr, cmds, logfile, timeoutMs);
#endif
        if (!File.Exists(JLINK)) throw new Stop("找不到 J-Link 软件：" + JLINK);
        var psi = PrepareJLink(gr, cmds, logfile);
        using (var p = Process.Start(psi))
        {
            // SAM | 2026-11-10 +08:00 | Drain both pipes asynchronously so the bounded process wait can actually time out.
            var err = p.StandardError.ReadToEndAsync();
            var output = p.StandardOutput.ReadToEndAsync();
            bool exited = p.WaitForExit(timeoutMs);
            if (!exited) { try { p.Kill(); } catch { } }
            if (!System.Threading.Tasks.Task.WaitAll(new System.Threading.Tasks.Task[] { output, err }, 5000))
            {
                File.WriteAllText(logfile, "J-Link 输出读取超时，禁止继续写入。", Encoding.UTF8);
                throw new Stop("J-Link 输出读取超时，见 " + logfile);
            }
            string o = output.Result + err.Result;
            File.WriteAllText(logfile, o, Encoding.UTF8);
            if (!exited) throw new Stop("J-Link 超时，已停止后续步骤，见 " + logfile);
            if (p.ExitCode != 0) o += "\nEXITCODE " + p.ExitCode;
            return o;
        }
    }

    static byte[] Snapshot(string dir, string name)
    {
        string f = Path.Combine(dir, name + ".bin");
        // SAM | 2026-11-10 +08:00 | Running XIP reads produced shifted APP bytes on the bench; halt before every full backup/readback.
        string result = JLink(false, new[] { "h", string.Format("savebin {0},0x{1:X},0x{2:X}", f, FLASH_BASE, SNAP_SIZE) }, Path.Combine(dir, name + "_snapshot.log"));
        Check(result, 0, name + "_snapshot.log");
        byte[] d = File.Exists(f) ? File.ReadAllBytes(f) : new byte[0];
        if (d.Length != SNAP_SIZE) throw new Stop("快照失败（" + name + "），见 " + dir);
        return d;
    }

    static bool Eq(byte[] a, int ao, byte[] b, int bo, int n) { for (int i = 0; i < n; i++) if (a[ao + i] != b[bo + i]) return false; return true; }
    static bool NvdsIntact(byte[] pre, byte[] post, int o, int n)
    {
        int changed = 0;
        for (int i = 0; i < n; i++) { if ((post[o + i] & ~pre[o + i]) != 0) return false; if (post[o + i] != pre[o + i]) ++changed; }
        if (changed > 0) Log("      注意：NVDS 有 " + changed + " 字节被新固件开机后改写（如姓名记录迁移到 Flash 页），不是烧录写的");
        return Eq(post, o, pre, o, 4);
    }
    static bool AllFF(byte[] a, int o, int n) { for (int i = 0; i < n; i++) if (a[o + i] != 0xFF) return false; return true; }
    static int Off(uint addr) { return (int)(addr - FLASH_BASE); }

    static string Sha(byte[] bytes)
    {
        using (var sha = SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
    }

    static byte[] Resource(string name)
    {
        using (var stream = typeof(Flasher).Assembly.GetManifestResourceStream(name))
        {
            if (stream == null) throw new Stop("工具缺少内置初始化资源：" + name);
            using (var output = new MemoryStream()) { stream.CopyTo(output); return output.ToArray(); }
        }
    }

    // SAM | 2026-11-10 +08:00 | Decode only committed v2 owners; CRC and latest generation distinguish an unallocated GR task from installation.
    static uint OwnerCrc(byte[] data, int offset, int length)
    {
        uint crc = 0xffffffff;
        for (int i = offset; i < offset + length; i++)
        {
            crc ^= data[i];
            for (int bit = 0; bit < 8; bit++) crc = (crc >> 1) ^ ((crc & 1) == 0 ? 0u : 0xedb88320u);
        }
        return ~crc;
    }

    static string OwnerText(byte[] record, int offset, int length)
    {
        int end = Array.IndexOf(record, (byte)0, offset, length);
        if (end < offset || end == offset) throw new Stop("OTA 任务身份缺失或字符串损坏，禁止初始化");
        string value = Encoding.ASCII.GetString(record, offset, end - offset);
        if (value.Any(c => c < 32 || c > 126)) throw new Stop("OTA 任务身份包含非法字符，禁止初始化");
        return value;
    }

    static string InitialOwnerSummary(byte[] pre)
    {
        byte[] latest = null;
        uint latestGeneration = 0;
        for (int page = 0; page < 2; page++)
        {
            int offset = Off(0x2F9000) + page * 4096;
            if (AllFF(pre, offset, 4096)) continue;
            uint generation = BitConverter.ToUInt32(pre, offset + 4);
            if (BitConverter.ToUInt32(pre, offset) != 0x594f5432 || generation == 0 || generation == uint.MaxValue ||
                BitConverter.ToUInt32(pre, offset + 364) != 0 ||
                BitConverter.ToUInt32(pre, offset + 360) != OwnerCrc(pre, offset, 360) ||
                !AllFF(pre, offset + 368, 4096 - 368))
                throw new Stop("OTA owner 记录损坏、不完整或格式不支持，禁止初始化；请保留 pre.bin");
            byte[] record = pre.Skip(offset).Take(368).ToArray();
            if (latest != null && generation == latestGeneration && !latest.SequenceEqual(record))
                throw new Stop("OTA owner 同代记录冲突，禁止初始化");
            if (latest == null || generation > latestGeneration) { latest = record; latestGeneration = generation; }
        }
        if (latest == null) return "OTA owner 为空。";
        uint epoch = BitConverter.ToUInt32(latest, 8);
        string job = OwnerText(latest, 13, 65), hash = OwnerText(latest, 78, 65);
        string target = OwnerText(latest, 143, 8);
        string version = OwnerText(latest, 151, 64), source = OwnerText(latest, 215, 64);
        if (epoch == 0 || epoch == uint.MaxValue || !Regex.IsMatch(job, "^[0-9a-fA-F]{64}$") ||
            !Regex.IsMatch(hash, "^[0-9a-fA-F]{64}$") || job.All(c => c == '0') || hash.All(c => c == '0'))
            throw new Stop("OTA owner 任务身份非法，禁止初始化");
        if (latest[12] != 1 || target != "GR5526" || BitConverter.ToUInt32(latest, 352) != 0 ||
            BitConverter.ToUInt32(latest, 356) != 0)
            throw new Stop("OTA 任务已有接收范围、进度、B槽归属或安装状态，禁止初始化；请保留 pre.bin 核对");
        return "将清理尚未取得接收范围的 GR 旧任务（DOWNLOADING，total=0，durable=0，B未归属）。" +
            "\r\nepoch=" + epoch + "，generation=" + latestGeneration + "，范围=" + source + " → " + version +
            "\r\njob=" + job + "\r\nhash=" + hash;
    }

    // SAM | 2026-11-10 +08:00 | User explicitly approved backed-up B clearing after confirmation; allocated or installing transactions remain blocked.
    static void CheckInitialState(byte[] pre)
    {
        if (pre.Length != SNAP_SIZE) throw new Stop("初始化快照不完整，禁止写入");
        if (!AllFF(pre, Off(BOOT_ADDR), (int)BOOT_MAX))
            throw new Stop("首次初始化只适用于 Boot 全空的板子；已有 Boot 禁止强行覆盖");
        if (!AllFF(pre, Off(CLEAR_ADDR), 0x3000))
            throw new Stop("OTA scratch 或 Boot 日志非空，存在安装现场或未知内容，禁止初始化；请保留 pre.bin");
        InitialOwnerSummary(pre);
        if (BitConverter.ToUInt32(pre, 8) != A_ADDR || BitConverter.ToUInt32(pre, 12) != A_ADDR)
            throw new Stop("启动配置不是已知的 APP 直启布局，禁止初始化");
        uint sp = BitConverter.ToUInt32(pre, Off(A_ADDR)), reset = BitConverter.ToUInt32(pre, Off(A_ADDR) + 4);
        string app = Encoding.GetEncoding(28591).GetString(pre, Off(A_ADDR), (int)SLOT);
        if (sp <= 0x20006000 || sp > 0x20040000 || (sp & 7) != 0 || (reset & 1) == 0 ||
            (reset & ~1u) < A_ADDR + 8 || (reset & ~1u) >= A_ADDR + SLOT ||
            !app.Contains("YP001_FW|GR5526|"))
            throw new Stop("板上 APP 无法识别为兼容的 YP001，禁止初始化");
    }

    static byte[] PrepareInitialBoot(byte[] pre, byte[] app)
    {
        CheckInitialState(pre);
        byte[] boot = Resource("BootTemplate");
        if (Sha(boot) != BOOT_SHA) throw new Stop("内置 Boot 指纹错误，禁止初始化");
        VerifySignedApp(app);
        return boot;
    }

    static void VerifySignedApp(byte[] app)
    {
        byte[] publicBytes = Resource("BootPublic");
        if (Sha(publicBytes) != PUBLIC_SHA) throw new Stop("内置公钥指纹错误，禁止烧录");
        try { GrProjectNative.Verify(app, Encoding.UTF8.GetString(publicBytes), PUBLIC_SHA, LAYOUT_PIN, DATA_PIN); }
        catch (Exception e) { throw new Stop("签名/芯片/向量/布局/数据合同校验失败：" + e.Message); }
    }

    public static string Inspect(string image, out string summary)
    {
        return InspectBytes(File.ReadAllBytes(image), image, out summary);
    }

    // SAM | 2026-11-10 +08:00 | Confirmation and writes must describe the same immutable input bytes.
    static string InspectBytes(byte[] app, string image, out string summary)
    {
        if (app.Length <= 8 + SIG_TAIL || app.Length > SLOT) throw new Stop(string.Format("镜像大小 {0} 不对（必须是 Gr5526Tool 签名后的 .bin，且不超过 {1}）", app.Length, SLOT));
        VerifySignedApp(app);
        uint number = BitConverter.ToUInt32(app, app.Length - SIG_TAIL + 20);
        uint build = BitConverter.ToUInt32(app, app.Length - SIG_TAIL + 24);
        string ver = number / 1000000 + "." + number / 1000 % 1000 + "." + number % 1000;
        summary = string.Format("{0}：{1} 字节，版本 {2} build {3}", Path.GetFileName(image), app.Length, ver, build);
        return ver + "_b" + build;
    }

    public static void Run(string image, string port, bool clearName, bool initializeBoot = false, Func<string, bool> confirmInitialization = null)
    {
        if (holdForInitialization) throw new Stop("上次初始化已暂停且未完成，请保留日志交开发恢复，禁止继续烧录");
        probeSerial = null;
        if (initializeBoot && clearName) throw new Stop("首次初始化必须保留姓名和字形，请取消出厂清空");
        byte[] app = File.ReadAllBytes(image);
        string summary; string tag = InspectBytes(app, image, out summary);
        uint ver = BitConverter.ToUInt32(app, app.Length - SIG_TAIL + 20);
        string dir = Path.Combine(Here, "logs", DateTime.Now.ToString("yyyyMMdd_HHmmss_fff") + "_" + tag + "_" + Guid.NewGuid().ToString("N").Substring(0, 8));
        Directory.CreateDirectory(dir);
        Log("[1/6] " + summary + "\r\n      记录目录 " + dir);

        Log("[2/6] 读烧前整片快照（只读）…");
        byte[] pre = Snapshot(dir, "pre");

        // SAM | 2026-11-10 +08:00 | Bind every write to the probe that produced the saved snapshot.
        string probeLog = File.ReadAllText(Path.Combine(dir, "pre_snapshot.log"));
        var probeMatch = Regex.Match(probeLog, @"(?m)^S/N:\s*(\d+)\s*$");
        if (initializeBoot && !probeMatch.Success) throw new Stop("无法确认 J-Link 编号，禁止初始化");
        if (probeMatch.Success) probeSerial = probeMatch.Groups[1].Value;

        int bo = Off(BOOT_ADDR), bl = (int)BOOT_MAX;
        while (bl > 0 && pre[bo + bl - 1] == 0xFF) bl--;
        bl += (4 - bl % 4) % 4;
        byte[] boot = new byte[bl]; Array.Copy(pre, bo, boot, 0, bl);
        if (initializeBoot) { boot = PrepareInitialBoot(pre, app); bl = boot.Length; }
        byte[] approvals = { 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0 };
        if (bl < DESC_OFF + 40 || !Eq(boot, DESC_OFF - 96, LAYOUT_HASH, 0, 8) || !Eq(boot, DESC_OFF - 108, approvals, 0, 12))
            throw new Stop("板上 Boot 不是预期的已配对 Boot（找不到描述符），停止，没有写任何东西。Boot 全空时可勾选首次初始化，再由安全检查确认");
        byte[] desc = new byte[40];
        BitConverter.GetBytes((uint)(app.Length - SIG_TAIL)).CopyTo(desc, 0);
        BitConverter.GetBytes(ver).CopyTo(desc, 4);
        using (var sha = SHA256.Create()) sha.ComputeHash(app, 0, app.Length - SIG_TAIL).CopyTo(desc, 8);
        byte[] nb = (byte[])boot.Clone(); desc.CopyTo(nb, DESC_OFF);
        int changed = 0; for (int i = 0; i < bl; i++) if (nb[i] != boot[i]) { if (i < DESC_OFF || i >= DESC_OFF + 40) throw new Stop("内部错误：Boot 改动超出描述符"); changed++; }
        string appF = Path.Combine(dir, "app.bin"), bootF = Path.Combine(dir, "boot_paired.bin");
        File.WriteAllBytes(appF, app); File.WriteAllBytes(bootF, nb); File.WriteAllBytes(Path.Combine(dir, "boot_before.bin"), boot);
        Log(string.Format("[3/6] 配对 Boot：{0} 字节，只改描述符 {1} 字节", bl, changed));

        if (initializeBoot)
        {
            byte[] originalB = pre.Skip(Off(B_ADDR)).Take((int)SLOT).ToArray();
            string bBackup = Path.Combine(dir, "b_before.bin");
            using (var backup = new FileStream(bBackup, FileMode.CreateNew, FileAccess.Write, FileShare.Read))
            {
                backup.Write(originalB, 0, originalB.Length);
                backup.Flush(true);
            }
            if (!originalB.SequenceEqual(File.ReadAllBytes(bBackup)) || !pre.SequenceEqual(File.ReadAllBytes(Path.Combine(dir, "pre.bin"))))
                throw new Stop("烧前备份读回不一致，禁止初始化");
            string confirmation = "J-Link 编号：" + probeSerial + "\r\n" + summary +
                "\r\n镜像 SHA256：" + Sha(app) + "\r\n烧前备份：" + Path.Combine(dir, "pre.bin") +
                "\r\n\r\nBoot、scratch 和 Boot 日志为空。\r\n" + InitialOwnerSummary(pre) +
                "\r\n\r\n将清空 B 槽 0x280000～0x2EBFFF，其中未知内容会被删除（非FF字节数：" + originalB.Count(b => b != 255) + "）。" +
                "\r\nB槽备份：" + bBackup + "\r\nB槽 SHA256：" + Sha(originalB) +
                "\r\n将写入 A 槽、配套 Boot 并切换启动目标。" +
                "\r\n保留B槽以外的姓名页、字库保留区和 NVDS。写入期间请保持稳定供电。" +
                "\r\n确定首次初始化，并清空 B 槽及上面列出的旧任务？";
            if (confirmInitialization == null || !confirmInitialization(confirmation))
                throw new Stop("已取消首次初始化，没有擦写 Flash；烧前备份已保留");
            holdForInitialization = true;
            byte[] current = Snapshot(dir, "init_check");
            if (!pre.SequenceEqual(current)) throw new Stop("确认期间板上内容发生变化，禁止初始化；目标已暂停，请保留现场交开发核对");
            if (!File.Exists(bBackup) || !File.Exists(Path.Combine(dir, "pre.bin")) ||
                !originalB.SequenceEqual(File.ReadAllBytes(bBackup)) || !pre.SequenceEqual(File.ReadAllBytes(Path.Combine(dir, "pre.bin"))))
                throw new Stop("确认后烧前备份丢失或内容变化，禁止初始化；目标已暂停，请保留现场");
            File.WriteAllText(Path.Combine(dir, "initialization.txt"), confirmation + "\r\n用户在写入前确认。\r\nBoot SHA256：" + Sha(nb), Encoding.UTF8);
        }

        // SAM | 2026-11-10 +08:00 | Check the connected device reported by Commander before any destructive command.
        string connection = JLink(true, new[] { "h", "mem32 0x200000,4" }, Path.Combine(dir, "connection_check.log"), 60000);
        Check(connection, 0, "connection_check.log");
        var selected = Regex.Matches(connection, "Device \"([^\"]+)\" selected", RegexOptions.IgnoreCase);
        if (selected.Count == 0 || selected[selected.Count - 1].Groups[1].Value != DEVICE)
            throw new Stop("J-Link 实际未选中 GR5526，已停止，尚未擦写。请保留 connection_check.sdk.log 和 .runtime.txt");
        Log("[4/6] 擦除 Boot 日志/owner 和 B 槽，写 A 槽（J-Link + GR5526 Flash 算法）…");
        // SAM | 2026-11-05 +08:00 | J-Link erase includes its final address; exclude the adjacent name page and other partitions.
        EraseRange(dir, "erase_owner", CLEAR_ADDR, CLEAR_END - 1);
        EraseRange(dir, "erase_b", B_ADDR, B_ADDR + SLOT - 1);
        string t1 = JLink(true, new[] { "h",
            string.Format("loadbin {0},0x{1:X}", appF, A_ADDR), string.Format("verifybin {0},0x{1:X}", appF, A_ADDR) }
            .Concat(initializeBoot ? new string[0] : new[] { "r", "g" }), Path.Combine(dir, "flash_app.log"));
        Check(t1, 1, "flash_app.log");
        // The flash algorithm records the image of one J-Link session in SCA (ROM boot target). Boot gets its own session, run
        // while GR is running; read SCA back and repeat (max 3) until it points at Boot.
        bool scaOk = false;
        for (int k = 1; k <= 3 && !scaOk; k++)
        {
            Thread.Sleep(3000);
            Log("      写 Boot（第 " + k + " 次）…");
            EraseRange(dir, "erase_boot_" + k, BOOT_ADDR, BOOT_ADDR + BOOT_MAX - 1);
            string t2 = JLink(true, new[] { "h",
                string.Format("loadbin {0},0x{1:X}", bootF, BOOT_ADDR), string.Format("verifybin {0},0x{1:X}", bootF, BOOT_ADDR) }
                .Concat(initializeBoot ? new string[0] : new[] { "r", "g" }),
                Path.Combine(dir, "flash_boot_" + k + ".log"));
            Check(t2, 1, "flash_boot_" + k + ".log");
            string sf = Path.Combine(dir, "sca_" + k + ".bin");
            string scaLog = JLink(false, new[] { string.Format("savebin {0},0x{1:X},0x10", sf, FLASH_BASE) }, Path.Combine(dir, "sca_" + k + ".log"), 60000);
            Check(scaLog, 0, "sca_" + k + ".log");
            byte[] sca = File.Exists(sf) ? File.ReadAllBytes(sf) : new byte[0];
            scaOk = sca.Length == 16 && BitConverter.ToUInt32(sca, 8) == BOOT_ADDR && BitConverter.ToUInt32(sca, 12) == BOOT_ADDR;
            Log("      SCA 启动目标 " + (scaOk ? "= Boot" : "不对，重写 Boot"));
        }

        Log("[5/6] 读回核对…");
        Thread.Sleep(2000);
        byte[] post = Snapshot(dir, "post");
        var checks = new List<KeyValuePair<string, bool>> {
            new KeyValuePair<string, bool>("A 槽 = 签名镜像", Eq(post, Off(A_ADDR), app, 0, app.Length)),
            new KeyValuePair<string, bool>("Boot = 配对 Boot", Eq(post, bo, nb, 0, nb.Length)),
            new KeyValuePair<string, bool>("Boot 日志/owner 已清空", AllFF(post, Off(CLEAR_ADDR), (int)(CLEAR_END - CLEAR_ADDR))),
            new KeyValuePair<string, bool>("B 槽已清空（可供后续 OTA 接收）", AllFF(post, Off(B_ADDR), (int)SLOT)),
            // SAM | 2026-11-04 +08:00 | Flashing never writes NVDS, but the new firmware runs before the readback and may update it
            // (moving a 1.5.8-1.5.10 name record to its Flash pages marks the NVDS tag deleted: bits 1->0 only). Intact = header
            // unchanged and no bit went 0->1 (no erase).
            new KeyValuePair<string, bool>("NVDS 完好（只有固件开机后的正常写入）", NvdsIntact(pre, post, Off(NVDS_ADDR), (int)(SNAP_SIZE - Off(NVDS_ADDR)))),
            new KeyValuePair<string, bool>("SCA 启动目标 = Boot(0x2EC000)", BitConverter.ToUInt32(post, 8) == BOOT_ADDR && BitConverter.ToUInt32(post, 12) == BOOT_ADDR) };
        if (initializeBoot)
        {
            checks.Add(new KeyValuePair<string, bool>("保留区和字库逐字节不变", Eq(pre, Off(A_ADDR + SLOT), post, Off(A_ADDR + SLOT), (int)(B_ADDR - A_ADDR - SLOT))));
            checks.Add(new KeyValuePair<string, bool>("姓名页及 NVDS 逐字节不变", Eq(pre, Off(CLEAR_END), post, Off(CLEAR_END), (int)(SNAP_SIZE - Off(CLEAR_END)))));
        }
        foreach (var c in checks) Log("      " + (c.Value ? "OK    " : "FAIL  ") + c.Key);
        if (checks.Any(c => !c.Value)) throw new Stop("读回不一致，停止。不要断电，把记录目录发给开发：" + dir);
        if (initializeBoot)
        {
            holdForInitialization = false;
            Check(JLink(false, new[] { "r", "g" }, Path.Combine(dir, "start.log")), 0, "start.log");
            Log("首次初始化写入和复位前数据核验完成；启动、OTA及字库功能需另行验证。");
        }

        if (!string.IsNullOrEmpty(port) && port != "none")
        {
            Log("[6/6] 读 GR 版本（" + port + "）…");
            try
            {
                using (var sp = new SerialPort(port, 115200))
                {
                    sp.Open(); Thread.Sleep(8000); sp.ReadExisting(); sp.Write("fw_version\r\n"); Thread.Sleep(3000);
                    string text = sp.ReadExisting();
                    string line = text.Split('\n').FirstOrDefault(l => l.Contains("FW_VERSION"));
                    Log("      " + (line ?? "没读到 fw_version（GR 可能还在启动，稍后手动查）").Trim());
                    // SAM | 2026-11-04 +08:00 | Factory rule: Name / Room / Campus come only from the platform, nothing kept
                    // locally: clear the name store and check it is empty. Bench recovery may untick it to keep the name.
                    if (clearName)
                    {
                        Log("[出厂] 清空姓名/房号/园区和字形（name_store clear），再核对为空…");
                        sp.ReadExisting(); sp.Write("name_store clear\r\n"); Thread.Sleep(2000);
                        string outp = sp.ReadExisting(); sp.Write("name_store status\r\n"); Thread.Sleep(2000); outp += sp.ReadExisting();
                        string st = outp.Split('\n').FirstOrDefault(l => l.Contains("resident=")) ?? "";
                        Log("      " + (st.Length > 0 ? st.Trim() : "没有收到 name_store status 回答"));
                        // SAM | 2026-11-04 +08:00 | Storage empty but a TEST_DATA build refills a test name in RAM (bench 16:2x).
                        if (outp.Contains("[NAME] cleared") && st.Contains("glyphs=0 ") && st.Contains("stored_bytes=0") && st.Contains("resident=set"))
                            throw new Stop("存储已清空，但这版固件开着 TEST_DATA（测试名只在内存里，会显示在屏幕上）：出厂固件必须关掉 TEST_DATA 再烧");
                        if (!outp.Contains("[NAME] cleared") || !st.Contains("resident=--") || !st.Contains("glyphs=0 ") || !st.Contains("stored_bytes=0"))
                            throw new Stop("出厂清空没有确认（name_store status 不是空的）：检查串口后在 GR 串口手动执行 name_store clear 并核对");
                        Log("      OK  姓名/房号/园区和字形已清空，等后台下发");
                    }
                }
            }
            catch (Stop) { throw; }
            catch (Exception e) { Log("      串口打不开：" + e.Message); if (clearName) throw new Stop("串口打不开，出厂清空没做：" + e.Message); }
        }
        else if (clearName) Log("注意：没选串口，出厂清空没做：请在 GR 串口执行 name_store clear 并核对 name_store status 为空");
        Log("完成。全部记录：" + dir);
    }

    // SAM | 2026-11-10 +08:00 | Commander can report Erasing done even without a Flash bank; require the exact range receipt.
    static void EraseRange(string dir, string name, uint first, uint last)
    {
        string file = Path.Combine(dir, name + ".log");
        string result = JLink(true, new[] { "h", string.Format("erase 0x{0:X} 0x{1:X}", first, last), "h" }, file);
        Check(result, 0, file);
        string receipt = string.Format("Flash sectors within Range [0x{0:X8} - 0x{1:X8}] deleted.", first, last);
        if (result.IndexOf(receipt, StringComparison.OrdinalIgnoreCase) < 0)
            throw new Stop("未确认指定范围擦除成功，已停止后续写入。保留现场和 pre.bin，见 " + file);
    }

    static void Check(string text, int verifies, string logname)
    {
        var bad = text.Split('\n').Where(l => Regex.IsMatch(l, "error|failed|mismatch|could not|EXITCODE|No Flash bank|Unknown command|Unknown device|Cannot connect", RegexOptions.IgnoreCase) && !l.Contains("will now exit on Error")).ToList();
        if (Regex.Matches(text, "Verify successful").Count < verifies) bad.Add("J-Link 没有报告 Verify successful");
        if (bad.Count > 0) throw new Stop("写入报错（见 " + logname + "）：" + string.Join(" | ", bad.Take(4)) + "\r\n板子可能半写，不要断电，pre.bin 可用于恢复。");
    }
}

class MainForm : Form
{
    TextBox file = new TextBox(), log = new TextBox();
    ComboBox port = new ComboBox();
    const string NOPORT = "不读版本";
    // SAM | 2026-11-04 +08:00 | The bench GR port moves (COM26 -> COM30): default to the port used last time (last_port.txt).
    static readonly string LastPortFile = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "last_port.txt");
    static string LastPort() { try { return File.Exists(LastPortFile) ? File.ReadAllText(LastPortFile).Trim() : ""; } catch { return ""; } }
    Button pick = new Button(), go = new Button();
    CheckBox clearName = new CheckBox(), initializeBoot = new CheckBox();

    public MainForm()
    {
        // SAM | 2026-11-10 +08:00 | First initialization requires explicit opt-in and a second confirmation after backup.
        Text = "YP001 GR5526 J-Link 有线烧录 v1.4.3"; Width = 860; Height = 650; Font = new Font("Microsoft YaHei UI", 9F);
        // SAM | 2026-11-10 +08:00 | Auto-size labels and separate help text so Chinese text fits at Windows display scales.
        MinimumSize = new Size(860, 650);
        var l1 = new Label { Text = "签名镜像 (.bin)：", Left = 12, Top = 16, AutoSize = true };
        file.SetBounds(156, 12, 566, 24); pick.Text = "选择…"; pick.SetBounds(730, 11, 100, 26);
        var l2 = new Label { Text = "GR 串口（可选）：", Left = 12, Top = 50, AutoSize = true };
        port.SetBounds(156, 46, 140, 24); port.DropDownStyle = ComboBoxStyle.DropDownList;
        RefreshPorts(); port.DropDown += (s, e) => RefreshPorts();
        go.Text = "开始烧录"; go.SetBounds(730, 44, 100, 28);
        var hint = new Label { Text = "串口用来最后读 fw_version 和出厂清空。", Left = 12, Top = 82, AutoSize = true };
        // SAM | 2026-11-04 +08:00 | Factory: Name / Room / Campus are not kept locally; untick only for bench recovery.
        clearName.Text = "出厂：清空姓名/房号/园区"; clearName.Checked = true; clearName.SetBounds(320, 47, 390, 24);
        initializeBoot.Text = "首次初始化 Boot（仅 Boot 全空，检查后再次确认）";
        initializeBoot.SetBounds(12, 150, 700, 24);
        initializeBoot.CheckedChanged += (s, e) =>
        {
            if (initializeBoot.Checked) clearName.Checked = false;
            clearName.Enabled = !initializeBoot.Checked;
        };
        var tip = new Label { Text = "只烧 Gr5526Tool 签名后的 GR5526_x.y.z_bN_signed.bin；会清空 Boot 日志/owner 和 B 槽，NVDS 不动。", Left = 12, Top = 108, Width = 818, Height = 36 };
        log.SetBounds(12, 182, 818, 414); log.Multiline = true; log.ScrollBars = ScrollBars.Vertical; log.ReadOnly = true;
        log.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
        Controls.AddRange(new Control[] { l1, file, pick, l2, port, hint, clearName, initializeBoot, tip, go, log });
        FormClosing += (s, e) => { if (!go.Enabled) e.Cancel = true; };
        pick.Click += (s, e) =>
        {
            using (var d = new OpenFileDialog { Filter = "签名镜像 (*.bin)|*.bin", Title = "选择 Gr5526Tool 签名后的 .bin" })
                if (d.ShowDialog(this) == DialogResult.OK) { file.Text = d.FileName; Describe(); }
        };
        file.Leave += (s, e) => Describe();
        go.Click += (s, e) => Start();
        Flasher.Log = s => BeginInvoke(new Action(() => log.AppendText(s + "\r\n")));
        string[] args = Environment.GetCommandLineArgs();
        if (args.Length > 1) { file.Text = args[1]; Describe(); }
        log.AppendText("连接 J-Link，关掉 Keil 调试和占用 GR 串口的工具，然后选择签名镜像。\r\n");
    }

    void RefreshPorts()
    {
        string cur = port.Text;
        var names = SerialPort.GetPortNames().Distinct().OrderBy(n => n.Length).ThenBy(n => n).ToList();
        port.Items.Clear(); port.Items.Add(NOPORT); foreach (var n in names) port.Items.Add(n);
        if (!string.IsNullOrEmpty(cur) && port.Items.Contains(cur)) port.SelectedItem = cur;
        else { string last = LastPort(); port.SelectedItem = names.Contains(last) ? last : names.Contains("COM26") ? "COM26" : NOPORT; }
    }

    void Describe()
    {
        if (!File.Exists(file.Text)) return;
        try { string s; Flasher.Inspect(file.Text, out s); log.AppendText("已选择 " + s + "\r\n"); }
        catch (Exception e) { log.AppendText("这个文件不能用：" + e.Message + "\r\n"); }
    }

    void Start()
    {
        string img = file.Text.Trim().Trim('"');
        if (!File.Exists(img) || !img.EndsWith(".bin", StringComparison.OrdinalIgnoreCase)) { MessageBox.Show(this, "请先选择 Gr5526Tool 签名后的 .bin 文件。"); return; }
        string s;
        try { Flasher.Inspect(img, out s); } catch (Exception e) { MessageBox.Show(this, e.Message); return; }
        if (MessageBox.Show(this, "将要烧录：\r\n" + s + "\r\n\r\n擦除 Boot 日志/owner 和 B 槽，写 A 槽与 Boot，复位。NVDS 不动。\r\n确定开始？",
            "确认烧录", MessageBoxButtons.OKCancel, MessageBoxIcon.Warning) != DialogResult.OK) return;
        go.Enabled = pick.Enabled = file.Enabled = port.Enabled = clearName.Enabled = initializeBoot.Enabled = false;
        string p = port.Text == NOPORT ? "none" : port.Text.Trim();
        if (p != "none") { try { File.WriteAllText(LastPortFile, p); } catch { } }
        bool clear = clearName.Checked;
        bool initialize = initializeBoot.Checked;
        new Thread(() =>
        {
            try
            {
                Flasher.Run(img, p, clear, initialize, message => (bool)Invoke(new Func<bool>(() =>
                    MessageBox.Show(this, message, "首次初始化确认", MessageBoxButtons.OKCancel, MessageBoxIcon.Warning,
                        MessageBoxDefaultButton.Button2) == DialogResult.OK)));
                BeginInvoke(new Action(() => MessageBox.Show(this, "写入与读回校验完成，请核对设备启动版本。", "完成")));
            }
            catch (Flasher.Stop e) { Flasher.Log("停止：" + e.Message); BeginInvoke(new Action(() => MessageBox.Show(this, e.Message, "停止", MessageBoxButtons.OK, MessageBoxIcon.Error))); }
            catch (Exception e) { Flasher.Log("异常：" + e); }
            finally { BeginInvoke(new Action(() => {
                initializeBoot.Checked = false;
                go.Enabled = pick.Enabled = file.Enabled = port.Enabled = clearName.Enabled = initializeBoot.Enabled = true;
            })); }
        }) { IsBackground = true }.Start();
    }

    [STAThread]
    static void Main() { Application.EnableVisualStyles(); Application.Run(new MainForm()); }
}
