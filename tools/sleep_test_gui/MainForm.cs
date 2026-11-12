// SAM | 2026-10-16 +08:00 | Standalone serial GUI because testers need a double-click EXE.
using System;
using System.Drawing;
using System.IO;
using System.IO.Ports;
using System.Linq;
using System.Text;
using System.Windows.Forms;

class SleepTestForm : Form
{
    readonly ComboBox ports = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Width = 120 };
    readonly Button connect = new Button { Text = "打开串口", AutoSize = true };
    readonly TextBox log = new TextBox { Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Both,
        WordWrap = false, Dock = DockStyle.Fill, Font = new Font("Consolas", 10) };
    readonly Label status = new Label { Text = "未连接", AutoSize = true, Padding = new Padding(4, 7, 0, 0) };
    readonly Label wake = new Label { Text = "等待设备通知", Dock = DockStyle.Fill, AutoSize = true,
        Font = new Font("Microsoft YaHei UI", 12), ForeColor = Color.DarkBlue };
    readonly Timer poll = new Timer { Interval = 80 };
    readonly StringBuilder line = new StringBuilder();
    SerialPort serial;
    public SleepTestForm()
    {
        Text = "GR5526 深度休眠串口测试";
        Size = new Size(940, 640); MinimumSize = new Size(780, 500);
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Microsoft YaHei UI", 9);
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 5, ColumnCount = 1, Padding = new Padding(12) };
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 46));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 58));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 30));
        var top = new FlowLayoutPanel { Dock = DockStyle.Fill };
        var refresh = new Button { Text = "刷新串口", AutoSize = true };
        top.Controls.AddRange(new Control[] { ports, refresh, connect,
            new Label { Text = "115200 / 8N1", AutoSize = true, Padding = new Padding(8, 7, 8, 0) }, status });
        refresh.Click += delegate { RefreshPorts(); };
        connect.Click += delegate { if (serial != null) ClosePort(); else OpenPort(); };
        var actions = new FlowLayoutPanel { Dock = DockStyle.Fill };
        AddAction(actions, "进入深度休眠", "enter");
        AddAction(actions, "查询状态", "status");
        AddAction(actions, "退出休眠测试", "exit");
        var clear = new Button { Text = "清空日志", AutoSize = true };
        clear.Click += delegate { log.Clear(); };
        var save = new Button { Text = "保存日志", AutoSize = true };
        save.Click += delegate {
            using (var dialog = new SaveFileDialog { Filter = "文本日志|*.txt", FileName = "sleep_test_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".txt" })
                if (dialog.ShowDialog(this) == DialogResult.OK)
                    try { File.WriteAllText(dialog.FileName, log.Text, Encoding.UTF8); }
                    catch (Exception ex) { MessageBox.Show(this, ex.Message, "保存失败"); }
        };
        actions.Controls.AddRange(new Control[] { clear, save });
        layout.Controls.Add(top, 0, 0); layout.Controls.Add(actions, 0, 1);
        layout.Controls.Add(wake, 0, 2); layout.Controls.Add(log, 0, 3);
        // SAM | 2026-10-16 17:00 +08:00 | Explain that UART is intentionally offline during the v2 sleep window.
        layout.Controls.Add(new Label { Text = "深睡期间串口暂停；按键/GS_INT恢复后通知。60秒救援超时；睡眠中查询/退出命令不可用。",
            AutoSize = true, Dock = DockStyle.Fill }, 0, 4);
        Controls.Add(layout);
        poll.Tick += delegate { Receive(); }; poll.Start();
        FormClosed += delegate { poll.Stop(); ClosePort(); poll.Dispose(); };
        RefreshPorts();
    }
    void AddAction(FlowLayoutPanel panel, string label, string action)
    {
        var b = new Button { Text = label, AutoSize = true, Height = 32 };
        b.Click += delegate { Send(action); }; panel.Controls.Add(b);
    }
    void Append(string text)
    {
        if (log.TextLength > 500000) log.Text = log.Text.Substring(log.TextLength - 250000);
        log.AppendText(text);
    }
    void RefreshPorts()
    {
        string selected = ports.Text;
        try {
            var names = SerialPort.GetPortNames().OrderBy(x => x).ToArray();
            ports.Items.Clear(); ports.Items.AddRange(names);
            string preferred = names.Contains(selected) ? selected : names.Contains("COM26") ? "COM26" : names.FirstOrDefault();
            if (preferred != null) ports.SelectedItem = preferred;
        } catch (Exception ex) { Append("串口枚举失败：" + ex.Message + "\r\n"); }
    }
    void OpenPort()
    {
        if (ports.SelectedItem == null) { MessageBox.Show(this, "请连接设备并刷新串口。"); return; }
        var candidate = new SerialPort(ports.Text, 115200, Parity.None, 8, StopBits.One) {
            DtrEnable = false, RtsEnable = false, WriteTimeout = 1000, ReadTimeout = 200 };
        try {
            candidate.Open(); serial = candidate; line.Clear();
            connect.Text = "关闭串口"; ports.Enabled = false; status.Text = "已连接 " + serial.PortName;
            Append("\r\n[上位机] " + status.Text + "\r\n");
        } catch (Exception ex) { candidate.Dispose(); MessageBox.Show(this, ex.Message, "打开串口失败"); }
    }
    void ClosePort()
    {
        var previous = serial; serial = null;
        if (previous != null) { try { previous.Close(); } catch { } finally { previous.Dispose(); } }
        connect.Text = "打开串口"; ports.Enabled = true; status.Text = "未连接";
    }
    void Send(string action)
    {
        if (serial == null) { MessageBox.Show(this, "请先打开串口。"); return; }
        try {
            string command = "sleep_test " + action;
            serial.Write(command + "\r\n"); Append("\r\n[发送] " + command + "\r\n");
            if (action == "enter") wake.Text = "已发送入睡命令，等待设备确认和唤醒通知";
        } catch (Exception ex) { Append("[串口错误] " + ex.Message + "\r\n"); ClosePort(); }
    }
    void Receive()
    {
        if (serial == null) return;
        try {
            string text = serial.ReadExisting(); if (text.Length == 0) return;
            Append(text);
            foreach (char c in text) {
                if (c == '\n') {
                    string record = line.ToString(); line.Clear();
                    if (record.Contains("[WAKE] MCU AWAKE")) { wake.Text = "设备已唤醒：" + record.Trim(); wake.ForeColor = Color.DarkGreen; }
                    else if (record.Contains("refused") && record.Contains("SLEEP TEST")) { wake.Text = "设备拒绝入睡，请查看日志"; wake.ForeColor = Color.DarkRed; }
                    else if (record.Contains("[SLEEP TEST v2] entering")) { wake.Text = "正在尝试深睡；串口暂停，等待按键 / GS_INT 或60秒超时"; wake.ForeColor = Color.DarkBlue; }
                    else if (record.Contains("[SLEEP TEST] requested")) { wake.Text = "设备已接受测试，等待按键 / G-sensor"; wake.ForeColor = Color.DarkBlue; }
                } else if (line.Length < 4096) line.Append(c);
            }
        } catch (Exception ex) { Append("[串口断开] " + ex.Message + "\r\n"); ClosePort(); }
    }
    [STAThread]
    static void Main(string[] args)
    {
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        using (var form = new SleepTestForm()) {
            if (args.Contains("--self-test")) {
                form.CreateControl(); form.Dispose(); return;
            }
            Application.Run(form);
        }
    }
}
