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

    // SAM | 2026-11-05 12:12 +08:00 | Use relative ASCII operands and Unicode WorkingDirectory to support Chinese/space paths.
    static ProcessStartInfo PrepareJLink(bool gr, IEnumerable<string> cmds, string logfile)
    {
        string dir = Path.GetDirectoryName(Path.GetFullPath(logfile));
        var lines = new List<string>();
        // J-Link V7.54 does not load the per-user device folder at start-up (it then waits on a dialog): connect as Cortex-M4 first.
        if (gr) { InstallDevice(dir); lines.Add("exec JLinkDevicesXMLPath=.\\"); lines.Add("device " + DEVICE); }
        string prefix = dir + Path.DirectorySeparatorChar;
        lines.AddRange(cmds.Select(cmd => Regex.Replace(cmd, Regex.Escape(prefix), match => "", RegexOptions.IgnoreCase)));
        lines.Add("exit");
        string script = Path.ChangeExtension(logfile, ".jlink");
        File.WriteAllText(script, string.Join("\n", lines) + "\n", Encoding.ASCII);
        return new ProcessStartInfo(JLINK, "-NoGui 1 -ExitOnError 1 -device CORTEX-M4 -if SWD -speed 4000 -autoconnect 1 -CommandFile \"" + Path.GetFileName(script) + "\"")
        { WorkingDirectory = dir, UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true };
    }

    static string JLink(bool gr, IEnumerable<string> cmds, string logfile, int timeoutMs = 900000)
    {
        if (!File.Exists(JLINK)) throw new Stop("找不到 J-Link 软件：" + JLINK);
        var psi = PrepareJLink(gr, cmds, logfile);
        using (var p = Process.Start(psi))
        {
            var err = p.StandardError.ReadToEndAsync();
            string o = p.StandardOutput.ReadToEnd();
            if (!p.WaitForExit(timeoutMs)) { try { p.Kill(); } catch { } throw new Stop("J-Link 超时，见 " + logfile); }
            o += err.Result;
            File.WriteAllText(logfile, o, Encoding.UTF8);
            if (p.ExitCode != 0) o += "\nEXITCODE " + p.ExitCode;
            return o;
        }
    }

    static byte[] Snapshot(string dir, string name)
    {
        string f = Path.Combine(dir, name + ".bin");
        JLink(false, new[] { string.Format("savebin {0},0x{1:X},0x{2:X}", f, FLASH_BASE, SNAP_SIZE) }, Path.Combine(dir, name + "_snapshot.log"));
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

    public static string Inspect(string image, out string summary)
    {
        byte[] app = File.ReadAllBytes(image);
        if (app.Length <= 8 + SIG_TAIL || app.Length > SLOT) throw new Stop(string.Format("镜像大小 {0} 不对（必须是 Gr5526Tool 签名后的 .bin，且不超过 {1}）", app.Length, SLOT));
        var m = Regex.Match(Encoding.GetEncoding(28591).GetString(app), @"YP001_FW\|GR5526\|(\d{3})\.(\d{3})\.(\d{3})\|(\d+)\|END");
        if (!m.Success) throw new Stop("镜像里找不到版本标记 YP001_FW|GR5526|x.y.z|build|END");
        string ver = int.Parse(m.Groups[1].Value) + "." + int.Parse(m.Groups[2].Value) + "." + int.Parse(m.Groups[3].Value);
        summary = string.Format("{0}：{1} 字节，版本 {2} build {3}", Path.GetFileName(image), app.Length, ver, m.Groups[4].Value);
        return ver + "_b" + m.Groups[4].Value;
    }

    public static void Run(string image, string port, bool clearName)
    {
        byte[] app = File.ReadAllBytes(image);
        string summary; string tag = Inspect(image, out summary);
        var m = Regex.Match(Encoding.GetEncoding(28591).GetString(app), @"YP001_FW\|GR5526\|(\d{3})\.(\d{3})\.(\d{3})\|");
        uint ver = uint.Parse(m.Groups[1].Value) * 1000000 + uint.Parse(m.Groups[2].Value) * 1000 + uint.Parse(m.Groups[3].Value);
        string dir = Path.Combine(Here, "logs", DateTime.Now.ToString("yyyyMMdd_HHmmss") + "_" + tag);
        Directory.CreateDirectory(dir);
        Log("[1/6] " + summary + "\r\n      记录目录 " + dir);

        Log("[2/6] 读烧前整片快照（只读）…");
        byte[] pre = Snapshot(dir, "pre");

        int bo = Off(BOOT_ADDR), bl = (int)BOOT_MAX;
        while (bl > 0 && pre[bo + bl - 1] == 0xFF) bl--;
        bl += (4 - bl % 4) % 4;
        byte[] boot = new byte[bl]; Array.Copy(pre, bo, boot, 0, bl);
        byte[] approvals = { 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0 };
        if (bl < DESC_OFF + 40 || !Eq(boot, DESC_OFF - 96, LAYOUT_HASH, 0, 8) || !Eq(boot, DESC_OFF - 108, approvals, 0, 12))
            throw new Stop("板上 Boot 不是预期的已配对 Boot（找不到描述符），停止，没有写任何东西");
        byte[] desc = new byte[40];
        BitConverter.GetBytes((uint)(app.Length - SIG_TAIL)).CopyTo(desc, 0);
        BitConverter.GetBytes(ver).CopyTo(desc, 4);
        using (var sha = SHA256.Create()) sha.ComputeHash(app, 0, app.Length - SIG_TAIL).CopyTo(desc, 8);
        byte[] nb = (byte[])boot.Clone(); desc.CopyTo(nb, DESC_OFF);
        int changed = 0; for (int i = 0; i < bl; i++) if (nb[i] != boot[i]) { if (i < DESC_OFF || i >= DESC_OFF + 40) throw new Stop("内部错误：Boot 改动超出描述符"); changed++; }
        string appF = Path.Combine(dir, "app.bin"), bootF = Path.Combine(dir, "boot_paired.bin");
        File.WriteAllBytes(appF, app); File.WriteAllBytes(bootF, nb); File.WriteAllBytes(Path.Combine(dir, "boot_before.bin"), boot);
        Log(string.Format("[3/6] 配对 Boot：{0} 字节，只改描述符 {1} 字节", bl, changed));

        Log("[4/6] 擦除 Boot 日志/owner 和 B 槽，写 A 槽（J-Link + GR5526 Flash 算法）…");
        // SAM | 2026-11-05 +08:00 | J-Link erase includes its final address; exclude the adjacent name page and other partitions.
        string t1 = JLink(true, new[] { "h",
            string.Format("erase 0x{0:X} 0x{1:X}", CLEAR_ADDR, CLEAR_END - 1), string.Format("erase 0x{0:X} 0x{1:X}", B_ADDR, B_ADDR + SLOT - 1),
            string.Format("loadbin {0},0x{1:X}", appF, A_ADDR), string.Format("verifybin {0},0x{1:X}", appF, A_ADDR), "r", "g" }, Path.Combine(dir, "flash_app.log"));
        Check(t1, 1, "flash_app.log");
        // The flash algorithm records the image of one J-Link session in SCA (ROM boot target). Boot gets its own session, run
        // while GR is running; read SCA back and repeat (max 3) until it points at Boot.
        bool scaOk = false;
        for (int k = 1; k <= 3 && !scaOk; k++)
        {
            Thread.Sleep(3000);
            Log("      写 Boot（第 " + k + " 次）…");
            string t2 = JLink(true, new[] { "h", string.Format("erase 0x{0:X} 0x{1:X}", BOOT_ADDR, BOOT_ADDR + BOOT_MAX - 1),
                string.Format("loadbin {0},0x{1:X}", bootF, BOOT_ADDR), string.Format("verifybin {0},0x{1:X}", bootF, BOOT_ADDR), "r", "g" },
                Path.Combine(dir, "flash_boot_" + k + ".log"));
            Check(t2, 1, "flash_boot_" + k + ".log");
            string sf = Path.Combine(dir, "sca_" + k + ".bin");
            JLink(false, new[] { string.Format("savebin {0},0x{1:X},0x10", sf, FLASH_BASE) }, Path.Combine(dir, "sca_" + k + ".log"), 60000);
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
            new KeyValuePair<string, bool>("B 槽已清空", AllFF(post, Off(B_ADDR), (int)SLOT)),
            // SAM | 2026-11-04 +08:00 | Flashing never writes NVDS, but the new firmware runs before the readback and may update it
            // (moving a 1.5.8-1.5.10 name record to its Flash pages marks the NVDS tag deleted: bits 1->0 only). Intact = header
            // unchanged and no bit went 0->1 (no erase).
            new KeyValuePair<string, bool>("NVDS 完好（只有固件开机后的正常写入）", NvdsIntact(pre, post, Off(NVDS_ADDR), (int)(SNAP_SIZE - Off(NVDS_ADDR)))),
            new KeyValuePair<string, bool>("SCA 启动目标 = Boot(0x2EC000)", BitConverter.ToUInt32(post, 8) == BOOT_ADDR && BitConverter.ToUInt32(post, 12) == BOOT_ADDR) };
        foreach (var c in checks) Log("      " + (c.Value ? "OK    " : "FAIL  ") + c.Key);
        if (checks.Any(c => !c.Value)) throw new Stop("读回不一致，停止。不要断电，把记录目录发给开发：" + dir);

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

    static void Check(string text, int verifies, string logname)
    {
        var bad = text.Split('\n').Where(l => Regex.IsMatch(l, "error|failed|mismatch|could not|EXITCODE", RegexOptions.IgnoreCase) && !l.Contains("will now exit on Error")).ToList();
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
    CheckBox clearName = new CheckBox();

    public MainForm()
    {
        // SAM | 2026-11-05 12:12 +08:00 | Identify the Unicode-path fix in the delivered window.
        Text = "YP001 GR5526 J-Link 有线烧录 v1.2"; Width = 860; Height = 620; Font = new Font("Microsoft YaHei UI", 9F);
        var l1 = new Label { Text = "签名镜像 (.bin)：", Left = 12, Top = 16, Width = 110 };
        file.SetBounds(122, 12, 600, 24); pick.Text = "选择…"; pick.SetBounds(730, 11, 100, 26);
        var l2 = new Label { Text = "GR 串口（可选）：", Left = 12, Top = 50, Width = 110 };
        port.SetBounds(122, 46, 140, 24); port.DropDownStyle = ComboBoxStyle.DropDownList;
        RefreshPorts(); port.DropDown += (s, e) => RefreshPorts();
        go.Text = "开始烧录"; go.SetBounds(730, 44, 100, 28);
        var hint = new Label { Text = "串口用来最后读 fw_version 和出厂清空。", Left = 272, Top = 50, Width = 250 };
        // SAM | 2026-11-04 +08:00 | Factory: Name / Room / Campus are not kept locally; untick only for bench recovery.
        clearName.Text = "出厂：清空姓名/房号/园区"; clearName.Checked = true; clearName.SetBounds(525, 47, 200, 24);
        var tip = new Label { Text = "只烧 Gr5526Tool 签名后的 GR5526_x.y.z_bN_signed.bin；会清空 Boot 日志/owner 和 B 槽，NVDS 不动。", Left = 12, Top = 80, Width = 818, Height = 20 };
        log.SetBounds(12, 106, 818, 460); log.Multiline = true; log.ScrollBars = ScrollBars.Vertical; log.ReadOnly = true;
        log.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
        Controls.AddRange(new Control[] { l1, file, pick, l2, port, hint, clearName, tip, go, log });
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
        go.Enabled = pick.Enabled = false;
        string p = port.Text == NOPORT ? "none" : port.Text.Trim();
        if (p != "none") { try { File.WriteAllText(LastPortFile, p); } catch { } }
        bool clear = clearName.Checked;
        new Thread(() =>
        {
            try { Flasher.Run(img, p, clear); BeginInvoke(new Action(() => MessageBox.Show(this, "烧录完成，核对全部通过。", "完成"))); }
            catch (Flasher.Stop e) { Flasher.Log("停止：" + e.Message); BeginInvoke(new Action(() => MessageBox.Show(this, e.Message, "停止", MessageBoxButtons.OK, MessageBoxIcon.Error))); }
            catch (Exception e) { Flasher.Log("异常：" + e); }
            finally { BeginInvoke(new Action(() => { go.Enabled = pick.Enabled = true; })); }
        }) { IsBackground = true }.Start();
    }

    [STAThread]
    static void Main() { Application.EnableVisualStyles(); Application.Run(new MainForm()); }
}
