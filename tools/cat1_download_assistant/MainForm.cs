// SAM | 2026-10-15 12:42 +08:00 | Increase the step panel and status row so the fourth step no longer overlaps the status text.
using System;
using System.Drawing;
using System.IO.Ports;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace Cat1DownloadAssistant {
    public sealed class MainForm : Form {
        readonly DownloadSession session = new DownloadSession();
        readonly ComboBox ports = new ComboBox();
        readonly Label status = new Label();
        readonly TextBox log = new TextBox();
        SerialPort port;
        // SAM | 2026-10-20 16:51 +08:00 | Collect physical CAT1 replies separately from GR TX acknowledgements before reusing a running module.
        readonly object captureLock = new object();
        readonly StringBuilder capture = new StringBuilder();
        bool captureEnabled;

        public MainForm() {
            // SAM | 2026-10-20 16:25 +08:00 | Make reconnect and repeat explicit because the old connect action always toggled PWRKEY.
            // SAM | 2026-10-25 +08:00 | Show the executable build name because the stale 20261020 title concealed which revision was actually running.
            Text = "CAT1 固件下载时序助手 · " + System.IO.Path.GetFileNameWithoutExtension(Application.ExecutablePath).Replace("CAT1DownloadAssistant_", ""); Size = new Size(900, 790); MinimumSize = new Size(860, 760);
            StartPosition = FormStartPosition.CenterScreen; Font = new Font("Microsoft YaHei UI", 10);
            var box = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(22), ColumnCount = 1, RowCount = 5 };
            box.RowStyles.Add(new RowStyle(SizeType.Absolute, 75)); box.RowStyles.Add(new RowStyle(SizeType.Absolute, 95));
            box.RowStyles.Add(new RowStyle(SizeType.Absolute, 320)); box.RowStyles.Add(new RowStyle(SizeType.Absolute, 90)); box.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); Controls.Add(box);
            box.Controls.Add(new Label { Text = "CAT1 固件下载时序助手\nLuatools 重启优先；串口重启只作备用", Dock = DockStyle.Fill, Font = new Font(Font.FontFamily, 18, FontStyle.Bold) });
            var serial = Row(); serial.WrapContents = true; ports.Width = 120; ports.DropDownStyle = ComboBoxStyle.DropDownList; serial.Controls.Add(new Label { Text = "GR UART0", AutoSize = true, Padding = new Padding(0, 8, 4, 0) }); serial.Controls.Add(ports); serial.Controls.Add(Button("刷新端口", RefreshPorts)); serial.Controls.Add(Button("仅连接 GR（不动电源）", ConnectSerial)); serial.Controls.Add(Button("首次上电（CAT1 未开机）", FirstPowerOn)); serial.Controls.Add(Button("关闭串口", CloseSerialByUser)); serial.Controls.Add(new Label { Text = "115200 / 8N1", AutoSize = true, Padding = new Padding(8, 8, 0, 0) }); box.Controls.Add(serial);
            var steps = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false };
            steps.Controls.Add(Button("再次下载 / CAT1 已运行（不发 PWRKEY）", BeginRepeat));
            steps.Controls.Add(Button("1. USB 已出现、Luatools 等待下载，并接通 BOOT↔EXT", delegate { Do(delegate { session.ConfirmBootToExt(); }); }));
            steps.Controls.Add(Button("2. 已在 Luatools 点击“模块重启”", delegate { Do(delegate { session.MarkRestartIssued("luatools"); }); }));
            steps.Controls.Add(Button("备用：用 GR 串口重启 CAT1", SerialRestart));
            steps.Controls.Add(Button("3. Luatools 已识别下载端口，已断开 BOOT↔EXT", delegate { Do(delegate { session.ConfirmUsbDownloadPort(); }); }));
            steps.Controls.Add(Button("4. Luatools 显示下载完成（释放 GR 串口）", delegate { session.ConfirmDownloadComplete(); CloseSerial(); ShowStatus(); Append("本轮完成，GR 串口已释放；下一轮点击“再次下载”，不要重复首次上电。"); }));
            steps.Controls.Add(Button("Luatools 已停止，取消本轮并释放串口", delegate { session.Cancel(); CloseSerial(); ShowStatus(); })); box.Controls.Add(steps);
            status.AutoSize = false; status.Dock = DockStyle.Fill; status.Font = new Font(Font.FontFamily, 12, FontStyle.Bold); status.ForeColor = Color.FromArgb(25, 75, 125); box.Controls.Add(status);
            log.Dock = DockStyle.Fill; log.Multiline = true; log.ReadOnly = true; log.ScrollBars = ScrollBars.Vertical; log.BackColor = Color.White; log.Font = new Font("Consolas", 9); box.Controls.Add(log);
            FormClosing += delegate { CloseSerial(); }; RefreshPorts(); ShowStatus(); Append("此工具不调用擦除、清 KV、清文件系统或 SOC 底包更新。");
        }
        FlowLayoutPanel Row() { return new FlowLayoutPanel { Dock = DockStyle.Fill, WrapContents = false, Padding = new Padding(0, 3, 0, 0) }; }
        Button Button(string text, Action action) { var b = new Button { Text = text, AutoSize = true, Height = 32, Margin = new Padding(0, 2, 5, 2) }; b.Click += delegate { try { action(); } catch (Exception ex) { Error(ex.Message); } }; return b; }
        // SAM | 2026-10-15 12:08 +08:00 | Prefer the historically verified GR UART0 COM26 and reject a silent non-GR port before changing CAT1 power.
        void RefreshPorts() { string selected = ports.Text; ports.Items.Clear(); var names = SerialPort.GetPortNames(); Array.Sort(names); ports.Items.AddRange(names); if (ports.Items.Contains(selected)) ports.SelectedItem = selected; else if (ports.Items.Contains("COM26")) ports.SelectedItem = "COM26"; else if (ports.Items.Count > 0) ports.SelectedIndex = 0; }
        // SAM | 2026-10-20 16:25 +08:00 | Connection is read-only apart from help because a serial reconnect must not shut down an already-running CAT1.
        void ConnectSerial() { OpenSerial(true); }
        // SAM | 2026-10-25 +08:00 | Cold rail enable must not depend on a help/AT probe; only explicit first-power-on bypasses help and verifies the rail command ACK instead.
        void OpenSerial(bool requireCliProbe) {
            if (port != null && port.IsOpen) { Append("GR 串口已连接；未发送电源命令。"); return; }
            if (ports.SelectedItem == null) throw new InvalidOperationException("请选择连接 GR UART0 的串口。");
            port = new SerialPort(ports.Text, 115200, Parity.None, 8, StopBits.One);
            port.Encoding = Encoding.ASCII; port.WriteTimeout = 1000; port.ReadTimeout = 100;
            port.DtrEnable = false; port.RtsEnable = false;
            try {
                port.Open(); SerialPort source = port;
                source.DiscardInBuffer();
                if (requireCliProbe) {
                source.Write("help\r\n");
                Append("TX > help；最多等待 2 秒确认 GR UART0，未发送上电或 PWRKEY。");
                // SAM | 2026-10-25 15:57 +08:00 | Poll and accumulate the complete CLI reply before installing
                // asynchronous CAT1 capture, avoiding a short one-shot read race on the initial handshake.
                string probe = DownloadSession.CollectGrCliProbe(
                    delegate { return source.ReadExisting(); },
                    delegate { Thread.Sleep(50); }, 40);
                if (probe.Length > 0) Append("RX < " + probe.TrimEnd());
                if (!DownloadSession.IsGrCliProbe(probe)) throw new InvalidOperationException("未取得 GR CLI 回显，请核对 GR UART0 端口；未发送电源命令。");
                }
                source.DataReceived += delegate { try { string rx = source.ReadExisting(); lock(captureLock) { if (captureEnabled && capture.Length < 16384) capture.Append(rx); } if (rx.Length > 0 && !IsDisposed) BeginInvoke((Action)delegate { Append("RX < " + rx.TrimEnd()); }); } catch { } };
                Append(requireCliProbe ? "GR 已连接；CAT1 电源状态不变。" : "所选 GR 串口已打开；首次上电将直接请求供电，并核对 GR 执行回执，不依赖 CAT1 AT 回复。");
            } catch { CloseSerial(); throw; }
        }
        void FirstPowerOn() {
            if (!session.CanBeginRepeat) throw new InvalidOperationException("本轮已开始；先停止 Luatools 下载并取消本轮，再恢复未开机模块。");
            // SAM | 2026-10-25 +08:00 | Operator explicitly selects a cold CAT1 with GR powered; unrelated PC ports and an absent CAT1 reply cannot block its rail enable.
            OpenSerial(false);
            session.Reset();
            try { session.ColdPowerOn(ExchangeGrPowerCommand, Thread.Sleep); }
            catch { CloseSerial(); throw; }
            finally { ShowStatus(); }
        }
        // SAM | 2026-10-25 +08:00 | Capture GR GPIO acknowledgements independently of CAT1 UART4; PWRKEY is sent only after rail-enable success.
        string ExchangeGrPowerCommand(string command, int timeoutMs) {
            lock(captureLock) { capture.Clear(); captureEnabled = true; }
            try {
                port.Write("\r\n" + command + "\r\n"); Append("TX > " + command + "；等待 GR 执行回执。");
                var timer = System.Diagnostics.Stopwatch.StartNew();
                while (timer.ElapsedMilliseconds < timeoutMs) {
                    string response;
                    lock(captureLock) { response = capture.ToString(); }
                    if (DownloadSession.HasColdPowerAck(command, response)) return response;
                    if (command == "cat_at AT_INFO" && DownloadSession.HasCat1Traffic(response)) return response;
                    Thread.Sleep(50);
                }
                lock(captureLock) { return capture.ToString(); }
            } finally { lock(captureLock) { captureEnabled = false; } }
        }
        void BeginRepeat() {
            if (!session.CanBeginRepeat) throw new InvalidOperationException("本轮尚未结束。先停止 Luatools 下载并取消本轮。");
            ConnectSerial();
            try {
                if (!ProbeCat1()) throw new InvalidOperationException("没有收到 CAT1 的 AT_INFO 实际回复，不能复用为已运行模块。若只剩 GR 串口，请点“首次上电”恢复；若有下载口，请核对 Luatools。未发送 PWRKEY 或重启。");
                session.BeginRepeat();
            } finally { CloseSerial(); }
            ShowStatus();
            Append("已准备下一轮，释放 GR 串口；Luatools 保持打开。先重新启动下载等待，再执行 BOOT/模块重启步骤。此操作本身不下载、不重启模块。");
        }
        bool ProbeCat1() {
            lock(captureLock) { capture.Clear(); captureEnabled=true; }
            try {
                port.Write("cat_at AT_INFO\r\n"); Append("检查 CAT1 实际回复：TX ok 不等于模块在线。");
                Thread.Sleep(1200);
                lock(captureLock) { return DownloadSession.HasCat1Response(capture.ToString()); }
            } finally { lock(captureLock) { captureEnabled=false; } }
        }
        void CloseSerial() { if (port == null) return; try { port.Close(); port.Dispose(); } catch { } port = null; }
        // SAM | 2026-10-15 12:56 +08:00 | Add an explicit PC-port close action without toggling CAT1 power, because closing UART must not power off a live module.
        void CloseSerialByUser() { if (port == null || !port.IsOpen) { Append("串口当前已关闭；CAT1 电源状态不变。"); return; } CloseSerial(); Append("PC 串口已关闭；未发送 CAT1 下电命令，CAT1 电源状态不变。"); }
        // SAM | 2026-10-20 16:28 +08:00 | Reopen only GR CLI and release it after one restart request because repeated attempts must not retain COM26 or pulse PWRKEY.
        void SerialRestart() {
            if (!session.CanUseSerialFallback) throw new InvalidOperationException("先确认 Luatools 正在等待下载、BOOT↔EXT 已接通。");
            ConnectSerial();
            if (!ProbeCat1()) { CloseSerial(); throw new InvalidOperationException("CAT1 没有实际回复，软重启不可用。先停止 Luatools 等待并取消本轮，检查下载口或恢复首次上电；不会反复发送重启。"); }
            session.MarkRestartIssued("serial"); ShowStatus();
            try {
                string command = DownloadSession.SerialFallbackCommand(); port.Write(command + "\r\n");
                Append("TX > " + command + "；仅发送一次；需由 Luatools 确认下载端口。若无响应，先停止 Luatools 等待并取消本轮，不自动重复。");
                Thread.Sleep(150);
            } finally { CloseSerial(); Append("GR 串口已释放；没有操作 CAT1 USB 日志口。"); }
        }
        void Do(Action action) { action(); ShowStatus(); }
        void ShowStatus() { status.Text = session.Status; Append("状态：" + session.Step); }
        void Append(string text) { log.AppendText(DateTime.Now.ToString("HH:mm:ss") + " " + text + Environment.NewLine); }
        // SAM | 2026-10-20 16:54 +08:00 | Release the host port on any failed action so the recovery path cannot strand COM26 again.
        void Error(string text) { CloseSerial(); Append("错误：" + text); MessageBox.Show(this, text, "操作未执行或未完成，请核对日志", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
        // SAM | 2026-10-20 16:28 +08:00 | Allow one assistant instance across new builds because competing windows otherwise contend for the GR port.
        [STAThread] public static void Main() {
            bool created;
            using (var instance = new Mutex(true, @"Local\YP001_CAT1_DownloadAssistant", out created)) {
                if (!created) { MessageBox.Show("下载助手已经打开，请使用现有窗口。旧版助手也请先关闭，避免占用 GR 串口。", "CAT1 下载助手"); return; }
                try { Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false); Application.Run(new MainForm()); }
                finally { instance.ReleaseMutex(); }
            }
        }
    }
}
