// SAM | 2026-10-10 22:49 +08:00 | Add a standalone manual GR5526 DTM controller because方案2 must run without Keil or the existing CAT1 UI.
using System;
using System.Drawing;
using System.IO;
using System.IO.Ports;
using System.Text;
using System.Windows.Forms;

namespace Yp001BleDtm
{
    public sealed class DtmForm : Form
    {
        private readonly ComboBox ports = new ComboBox();
        private readonly NumericUpDown channel = new NumericUpDown();
        private readonly NumericUpDown packetLength = new NumericUpDown();
        private readonly NumericUpDown sentCount = new NumericUpDown();
        private readonly Label stateLabel = new Label();
        private readonly Label resultLabel = new Label();
        private readonly Label logPath = new Label();
        private readonly TextBox logBox = new TextBox();
        private readonly Button connectButton = new Button();
        private readonly Button resetButton = new Button();
        private readonly Button txButton = new Button();
        private readonly Button rxButton = new Button();
        private readonly Button stopButton = new Button();
        private readonly Timer timer = new Timer();
        private readonly HciParser parser = new HciParser();
        private SerialPort port;
        private StreamWriter journal;
        private string sessionFolder;
        private string state = "未连接";
        private ushort pending;
        private DateTime pendingAt;
        private int expectedRxPackets;
        private bool rxSequence;
        private int connectionToken;

        public DtmForm()
        {
            Text = "YP001 蓝牙 DTM 手动测试（方案2）";
            Width = 930;
            Height = 640;
            MinimumSize = new Size(780, 560);
            Font = new Font("Microsoft YaHei UI", 9F);
            var body = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(14), ColumnCount = 1, RowCount = 6 };
            body.RowStyles.Add(new RowStyle(SizeType.Absolute, 44));
            body.RowStyles.Add(new RowStyle(SizeType.Absolute, 58));
            body.RowStyles.Add(new RowStyle(SizeType.Absolute, 56));
            body.RowStyles.Add(new RowStyle(SizeType.Absolute, 62));
            body.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
            body.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            Controls.Add(body);

            var connection = Row();
            connection.Controls.Add(Label("YP001 UART0 / 115200 8N1"));
            ports.DropDownStyle = ComboBoxStyle.DropDownList;
            ports.Width = 115;
            connection.Controls.Add(ports);
            connection.Controls.Add(MakeButton("刷新串口", RefreshPorts, 92));
            connectButton = MakeButton("连接", ToggleConnection, 78);
            connection.Controls.Add(connectButton);
            connection.Controls.Add(Label("连接本身不发 HCI 命令"));
            body.Controls.Add(connection);

            var settings = Row();
            settings.Controls.Add(Label("DTM 信道 0–39"));
            channel.Minimum = 0; channel.Maximum = 39; channel.Value = 19; channel.Width = 62;
            settings.Controls.Add(channel);
            settings.Controls.Add(Label("TX 包长"));
            packetLength.Minimum = 0; packetLength.Maximum = 37; packetLength.Value = 37; packetLength.Width = 62;
            settings.Controls.Add(packetLength);
            settings.Controls.Add(Label("仪器发包数（RX PER）"));
            // SAM | 2026-10-10 22:55 +08:00 | Limit the instrument packet count to the 16-bit HCI Test End counter because larger values would make PER misleading.
            sentCount.Minimum = 0; sentCount.Maximum = 65535; sentCount.Value = 1000; sentCount.Width = 90;
            settings.Controls.Add(sentCount);
            settings.Controls.Add(Label("BLE 1M / PRBS9；功率由测试固件默认值决定"));
            body.Controls.Add(settings);

            var actions = Row();
            resetButton = MakeButton("HCI 复位", ResetController, 100);
            txButton = MakeButton("开始 TX", StartTx, 100);
            rxButton = MakeButton("开始 RX", StartRx, 100);
            stopButton = MakeButton("停止 / 读计数", StopTest, 135);
            actions.Controls.Add(resetButton); actions.Controls.Add(txButton); actions.Controls.Add(rxButton); actions.Controls.Add(stopButton);
            actions.Controls.Add(Label("同一时刻只能有一个程序打开该 COM 口"));
            body.Controls.Add(actions);

            stateLabel.Dock = DockStyle.Fill;
            stateLabel.Font = new Font(Font.FontFamily, 12F, FontStyle.Bold);
            resultLabel.Dock = DockStyle.Fill;
            resultLabel.Text = "RX 计数：—；PER：—（须与仪器发包数配对）";
            var status = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 2 };
            status.Controls.Add(stateLabel, 0, 0); status.Controls.Add(resultLabel, 0, 1);
            body.Controls.Add(status);

            logPath.Dock = DockStyle.Fill;
            logPath.Text = "日志：连接后生成";
            body.Controls.Add(logPath);
            logBox.Dock = DockStyle.Fill;
            logBox.Multiline = true;
            logBox.ReadOnly = true;
            logBox.ScrollBars = ScrollBars.Both;
            logBox.WordWrap = false;
            body.Controls.Add(logBox);

            timer.Interval = 250;
            timer.Tick += delegate
            {
                if (pending != 0 && (DateTime.UtcNow - pendingAt).TotalSeconds >= 5)
                {
                    Log("HCI 命令超时，板端状态未知；先点停止或复位，不把发送成功当作执行成功。");
                    pending = 0;
                    SetState("状态未知");
                }
            };
            timer.Start();
            FormClosing += delegate { Disconnect(); };
            RefreshPorts();
            SetState("未连接");
        }

        private static FlowLayoutPanel Row()
        {
            return new FlowLayoutPanel { Dock = DockStyle.Fill, WrapContents = false, AutoScroll = true, FlowDirection = FlowDirection.LeftToRight };
        }
        private static Label Label(string text)
        {
            return new Label { Text = text, AutoSize = true, Margin = new Padding(4, 9, 4, 0) };
        }
        private Button MakeButton(string text, Action action, int width)
        {
            var button = new Button { Text = text, Width = width, Height = 29 };
            button.Click += delegate { try { action(); } catch (Exception ex) { Log("操作失败：" + ex.Message); MessageBox.Show(this, ex.Message, "DTM 错误", MessageBoxButtons.OK, MessageBoxIcon.Error); } };
            return button;
        }
        private void RefreshPorts()
        {
            string chosen = ports.Text;
            ports.Items.Clear();
            string[] names = SerialPort.GetPortNames();
            Array.Sort(names);
            ports.Items.AddRange(names);
            if (ports.Items.Contains(chosen)) ports.SelectedItem = chosen;
        }
        private void ToggleConnection()
        {
            if (port != null) { Disconnect(); return; }
            if (ports.SelectedItem == null) throw new InvalidOperationException("请先选择实际连接 YP001 UART0 的串口");
            sessionFolder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "YP001_BLE_DTM", "sessions", DateTime.Now.ToString("yyyyMMdd_HHmmss_fff") + "_" + Guid.NewGuid().ToString("N").Substring(0, 6));
            Directory.CreateDirectory(sessionFolder);
            try
            {
                journal = new StreamWriter(Path.Combine(sessionFolder, "hci.log"), false, new UTF8Encoding(true));
                journal.AutoFlush = true;
                SerialPort source = new SerialPort(ports.Text, 115200, Parity.None, 8, StopBits.One);
                source.ReadTimeout = 500; source.WriteTimeout = 1000;
                int token = ++connectionToken;
                source.DataReceived += delegate
                {
                    try
                    {
                        int n = source.BytesToRead;
                        if (n <= 0) return;
                        byte[] data = new byte[n];
                        int read = source.Read(data, 0, data.Length);
                        if (read > 0) BeginInvoke((Action)delegate { if (token == connectionToken && port == source) Receive(data, read); });
                    }
                    catch (Exception ex)
                    {
                        try { BeginInvoke((Action)delegate { if (token == connectionToken) { Log("串口读取失败：" + ex.Message); Disconnect(); } }); }
                        catch (InvalidOperationException) { }
                    }
                };
                source.Open();
                port = source;
                parser.Clear();
                pending = 0;
                connectButton.Text = "断开";
                ports.Enabled = false;
                logPath.Text = "日志：" + sessionFolder;
                SetState("已连接，未复位");
                Log("串口已连接；点击 HCI 复位，收到确认后再开始测试。");
            }
            catch
            {
                Disconnect();
                throw;
            }
        }
        private void Disconnect()
        {
            connectionToken++;
            if (port != null)
            {
                if (state == "TX 中" || state == "RX 中" || state == "状态未知" || pending != 0)
                {
                    try { port.Write(HciCommands.TestEnd(), 0, 4); Log("断开前尝试发送 TEST_END；未等待确认，须重新上电或复位板端核实已停止。"); }
                    catch (Exception ex) { Log("断开前停止发送失败：" + ex.Message); }
                }
                try { port.Close(); port.Dispose(); } catch (Exception ex) { Log("关闭串口失败：" + ex.Message); }
                port = null;
            }
            pending = 0;
            parser.Clear();
            connectButton.Text = "连接";
            ports.Enabled = true;
            SetState("未连接");
            if (journal != null) { try { journal.Dispose(); } finally { journal = null; } }
        }
        private void Request(ushort opcode, byte[] frame, string waiting)
        {
            if (port == null || !port.IsOpen) throw new InvalidOperationException("串口未连接");
            if (pending != 0 && opcode != HciCommands.TestEndOpcode) throw new InvalidOperationException("上一条 HCI 命令尚未确认");
            port.Write(frame, 0, frame.Length);
            Log("TX > " + HciCommands.Hex(frame));
            pending = opcode;
            pendingAt = DateTime.UtcNow;
            SetState(waiting);
        }
        private void StartTx()
        {
            if (state != "空闲") throw new InvalidOperationException("先 HCI 复位并等待确认，或停止当前测试");
            Request(HciCommands.TransmitterTestOpcode, HciCommands.TransmitterTest((int)channel.Value, (int)packetLength.Value), "等待 TX 确认");
            rxSequence = false;
        }
        private void StartRx()
        {
            if (state != "空闲") throw new InvalidOperationException("先 HCI 复位并等待确认，或停止当前测试");
            expectedRxPackets = (int)sentCount.Value;
            resultLabel.Text = "RX 计数：等待停止回执；仪器预设发包数：" + expectedRxPackets;
            Request(HciCommands.ReceiverTestOpcode, HciCommands.ReceiverTest((int)channel.Value), "等待 RX 确认");
            // SAM | 2026-10-10 22:55 +08:00 | Accept RX counting only after a successful HCI ACK because UART write alone does not prove the DUT entered RX mode.
            rxSequence = false;
        }
        // SAM | 2026-10-10 22:49 +08:00 | Keep TX STOP separate from RX packet results because a prior RX count must never become a TX PER result.
        private void ResetController()
        {
            Request(HciCommands.ResetOpcode, HciCommands.Reset(), "等待复位确认");
            rxSequence = false;
            expectedRxPackets = 0;
        }
        private void StopTest()
        {
            if (port == null) throw new InvalidOperationException("串口未连接");
            Request(HciCommands.TestEndOpcode, HciCommands.TestEnd(), "等待停止确认");
        }
        private void Receive(byte[] data, int count)
        {
            try
            {
                byte[] exact = new byte[count];
                Array.Copy(data, exact, count);
                Log("RX < " + HciCommands.Hex(exact));
                foreach (HciEvent evt in parser.Feed(exact, count))
                {
                    if (pending == 0 || !evt.IsCommandComplete(pending)) continue;
                    ushort opcode = pending;
                    pending = 0;
                    if (evt.Status != 0)
                    {
                        SetState("状态未知");
                        Log("HCI 命令失败：opcode=0x" + opcode.ToString("X4") + " status=0x" + evt.Status.ToString("X2"));
                        continue;
                    }
                    if (opcode == HciCommands.ResetOpcode) SetState("空闲");
                    else if (opcode == HciCommands.TransmitterTestOpcode) SetState("TX 中");
                    else if (opcode == HciCommands.ReceiverTestOpcode) { rxSequence = true; SetState("RX 中"); }
                    else if (opcode == HciCommands.TestEndOpcode)
                    {
                        SetState("空闲");
                        if (rxSequence && evt.ReceivedPackets >= 0)
                        {
                            string per = "—";
                            if (expectedRxPackets > 0 && evt.ReceivedPackets <= expectedRxPackets)
                                per = (100.0 * (expectedRxPackets - evt.ReceivedPackets) / expectedRxPackets).ToString("F2") + "%";
                            resultLabel.Text = "RX 收包：" + evt.ReceivedPackets + " / 仪器发包：" + expectedRxPackets + "；PER：" + per;
                            Log("TEST_END 收包数=" + evt.ReceivedPackets + "；PER=" + per + "（仅在仪器包数与本轮 RX 对应时有效）");
                        }
                        else resultLabel.Text = "TX/空闲测试已停止；无 RX 收包结果";
                        rxSequence = false;
                    }
                    Log("HCI 确认：opcode=0x" + opcode.ToString("X4") + " status=0");
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, "接收或日志失败：" + ex.Message, "DTM 错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
                Disconnect();
            }
        }
        private void SetState(string value)
        {
            state = value;
            stateLabel.Text = "状态：" + state;
            bool connected = port != null && port.IsOpen;
            resetButton.Enabled = connected && pending == 0 && state != "TX 中" && state != "RX 中";
            txButton.Enabled = connected && pending == 0 && state == "空闲";
            rxButton.Enabled = connected && pending == 0 && state == "空闲";
            stopButton.Enabled = connected;
        }
        private void Log(string message)
        {
            string line = DateTimeOffset.Now.ToString("o") + " " + message;
            logBox.AppendText(line + Environment.NewLine);
            if (journal != null) journal.WriteLine(line);
        }
    }

    static class Program
    {
        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new DtmForm());
        }
    }
}
