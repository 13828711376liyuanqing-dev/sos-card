// SAM | 2026-11-05 +08:00 | Reuse GUS transport in a manual console for initial link verification.
using System;
using System.IO;
using System.Text;
using System.Drawing;
using System.Windows.Forms;
using System.Threading.Tasks;
using System.Collections.Generic;
namespace FactoryFinal {
 public class ConsoleForm : Form {
  readonly BleLink link = new BleLink();
  readonly ComboBox devices = new ComboBox();
  readonly TextBox command = new TextBox(), output = new TextBox();
  readonly Label status = new Label();
  readonly List<Button> buttons = new List<Button>();
  readonly Dictionary<ulong,FoundDevice> found = new Dictionary<ulong,FoundDevice>();
  readonly System.Windows.Forms.Timer scanTimer = new System.Windows.Forms.Timer();
  readonly LineParser parser = new LineParser();
  TaskCompletionSource<Frame> pending;
  uint sequence;
  bool connected;
  public ConsoleForm() {
   Text = "YP001 BLE GUS 串口式调试工具 · 首测版";
   Size = new Size(1050,700); MinimumSize = new Size(850,550);
   Font = new Font("Microsoft YaHei UI",10); StartPosition = FormStartPosition.CenterScreen;
   var root = new TableLayoutPanel {Dock=DockStyle.Fill,RowCount=5,ColumnCount=1,Padding=new Padding(12)};
   root.RowStyles.Add(new RowStyle(SizeType.Absolute,65));
   root.RowStyles.Add(new RowStyle(SizeType.Absolute,48));
   root.RowStyles.Add(new RowStyle(SizeType.Absolute,48));
   root.RowStyles.Add(new RowStyle(SizeType.Absolute,45));
   root.RowStyles.Add(new RowStyle(SizeType.Percent,100)); Controls.Add(root);
   root.Controls.Add(new Label {Dock=DockStyle.Fill,Text="Windows 系统蓝牙 → YP001 GUS。COM31 Nordic CDC 需要专用协议适配。\n先扫描并核对设备地址，连接后点击 INFO 查询。手动发送仅适用于设备支持的 ASCII 协议。"});
   var row = new FlowLayoutPanel {Dock=DockStyle.Fill}; root.Controls.Add(row);
   row.Controls.Add(ActionButton("扫描",Scan)); devices.Width=470; devices.DropDownStyle=ComboBoxStyle.DropDownList; row.Controls.Add(devices);
   row.Controls.Add(ActionButton("连接",Connect)); row.Controls.Add(ActionButton("断开",Disconnect));
   var send = new FlowLayoutPanel {Dock=DockStyle.Fill}; root.Controls.Add(send);
   command.Width=480; command.MaxLength=62; send.Controls.Add(command);
   send.Controls.Add(ActionButton("发送（追加 LF）",SendManual)); send.Controls.Add(ActionButton("INFO 查询",Info));
   var tools = new FlowLayoutPanel {Dock=DockStyle.Fill}; root.Controls.Add(tools);
   tools.Controls.Add(ActionButton("保存日志",Save)); tools.Controls.Add(ActionButton("清空显示",delegate {output.Clear();return Task.FromResult(0);}));
   status.AutoSize=true; status.Text="未连接"; tools.Controls.Add(status);
   output.Multiline=true; output.ReadOnly=true; output.ScrollBars=ScrollBars.Both; output.WordWrap=false; output.Dock=DockStyle.Fill; output.Font=new Font("Consolas",10);root.Controls.Add(output);
   link.Discovered += delegate(FoundDevice d) {Ui(delegate {if(!found.ContainsKey(d.Address)){found[d.Address]=d;devices.Items.Add(d);}});};
   link.Received += delegate(string data) {Ui(delegate {Log("RX",data);foreach(Frame f in parser.Feed(data))if(pending!=null&&f.Op=="INFO"&&f.Seq==sequence)pending.TrySetResult(f);});};
   link.Lost += delegate(string reason) {Ui(delegate {connected=false;link.Disconnect();parser.Reset();status.Text="连接不可用";if(pending!=null)pending.TrySetException(new IOException(reason));Log("LINK",reason);});};
   scanTimer.Interval=12000;scanTimer.Tick+=delegate {scanTimer.Stop();link.StopScan();status.Text="扫描结束，共 "+devices.Items.Count+" 台；请选择设备";};
   FormClosing+=delegate {scanTimer.Stop();scanTimer.Dispose();if(pending!=null)pending.TrySetCanceled();link.Dispose();};
  }
  void Ui(Action action) {if(IsDisposed||Disposing)return;try {if(InvokeRequired)BeginInvoke(action);else action();}catch(InvalidOperationException){}}
  void Log(string direction,string text) {if(output.TextLength>200000)output.Text=output.Text.Substring(output.TextLength-100000);output.AppendText(DateTimeOffset.Now.ToString("HH:mm:ss.fff zzz")+" "+direction+" "+text+Environment.NewLine);}
  Button ActionButton(string text,Func<Task> action) {
   var button=new Button {Text=text,AutoSize=true};buttons.Add(button);
   button.Click+=async delegate {foreach(Button b in buttons)b.Enabled=false;devices.Enabled=false;try {await action();}catch(Exception e){Log("ERROR",e.Message);status.Text=e.Message;}finally {if(!IsDisposed){foreach(Button b in buttons)b.Enabled=true;devices.Enabled=true;}}};return button;
  }
  Task Scan() {if(connected)throw new InvalidOperationException("先断开当前设备");scanTimer.Stop();found.Clear();devices.Items.Clear();link.Scan();scanTimer.Start();status.Text="扫描中，12 秒后结束";Log("SCAN","仅列出 YP001 名称设备");return Task.FromResult(0);}
  async Task Connect() {
   FoundDevice d=devices.SelectedItem as FoundDevice;if(d==null)throw new InvalidOperationException("请选择扫描到的设备");
   scanTimer.Stop();link.StopScan();connected=false;parser.Reset();
   try {await link.Connect(d.Address,d.AddressType);connected=true;status.Text="已连接 "+d.Address.ToString("X12");Log("LINK",status.Text+"；尚未验证应用回应");}
   catch {link.Disconnect();throw;}
  }
  Task Disconnect() {scanTimer.Stop();link.StopScan();link.Disconnect();connected=false;parser.Reset();status.Text="已断开";Log("LINK","人工断开");return Task.FromResult(0);}
  async Task SendManual() {
   if(!connected)throw new InvalidOperationException("请先连接");string text=command.Text;
   if(text.Length==0)throw new InvalidOperationException("请输入命令");foreach(char c in text)if(c<32||c>126)throw new InvalidOperationException("首测协议仅支持单行 ASCII");
   Log("TX",text+" [LF]");await link.Send(text);Log("SEND","写入完成，业务结果请核对 RX；不自动重发");
  }
  async Task Info() {
   if(!connected)throw new InvalidOperationException("请先连接");sequence++;if(sequence==0)sequence++;
   parser.Reset();pending=new TaskCompletionSource<Frame>();
   try {string request="FT INFO "+sequence;Log("TX",request+" [LF]");await link.Send(request);
    if(await Task.WhenAny(pending.Task,Task.Delay(8000))!=pending.Task)throw new TimeoutException("INFO 无匹配回应，GUS 应用收发尚未通过");
    Frame frame=await pending.Task;status.Text=frame.Ok?"GUS INFO 收发通过":"设备拒绝 INFO";Log("RESULT",status.Text);
   }finally {pending=null;}
  }
  Task Save() {using(var dialog=new SaveFileDialog {Filter="日志 (*.log)|*.log",FileName="YP001_BLE_"+DateTime.Now.ToString("yyyyMMdd_HHmmss")+".log"})if(dialog.ShowDialog(this)==DialogResult.OK)File.WriteAllText(dialog.FileName,output.Text,new UTF8Encoding(true));return Task.FromResult(0);}
  [STAThread]static void Main(string[] args) {
   Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
   using(var form=new ConsoleForm()) {
    if(args.Length==2&&args[0]=="--render-preview") {form.ShowInTaskbar=false;form.StartPosition=FormStartPosition.Manual;form.Location=new Point(-30000,-30000);form.Show();Application.DoEvents();using(var bitmap=new Bitmap(form.Width,form.Height)){form.DrawToBitmap(bitmap,new Rectangle(0,0,form.Width,form.Height));bitmap.Save(Path.GetFullPath(args[1]));}return;}
    Application.Run(form);
   }
  }
 }
}
