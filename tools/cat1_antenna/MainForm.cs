// SAM | 2026-10-10 16:53 +08:00 | Native local operator UI with durable logs, honest ACK status and fresh metrics.
using System;
using System.IO;
using System.IO.Ports;
using System.Text;
using System.Drawing;
using System.Windows.Forms;
using System.Collections.Generic;
namespace Antenna {
 public class MainForm:Form {
  ComboBox ports=new ComboBox(),mode=new ComboBox();NumericUpDown interval=new NumericUpDown();TextBox antenna=new TextBox(),custom=new TextBox(),log=new TextBox();
  Label status=new Label(),paths=new Label(),lte=new Label(),gnss=new Label(),lteAge=new Label(),gnssAge=new Label();Button connect;
  SerialPort port;Protocol parser=new Protocol();Session session=new Session();Journal journal;string folder;int lifetime;
  DateTime lteTime=DateTime.MinValue,gnssTime=DateTime.MinValue;System.Windows.Forms.Timer timer=new System.Windows.Forms.Timer();
  public MainForm(){
   Text="CAT1 双天线调试台";Size=new Size(1060,820);MinimumSize=new Size(900,730);StartPosition=FormStartPosition.CenterScreen;BackColor=Color.FromArgb(242,245,249);Font=new Font("Microsoft YaHei UI",10);
   var grid=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=1,RowCount=8,Padding=new Padding(24)};
   grid.RowStyles.Add(new RowStyle(SizeType.Absolute,76));grid.RowStyles.Add(new RowStyle(SizeType.Absolute,54));grid.RowStyles.Add(new RowStyle(SizeType.Absolute,60));grid.RowStyles.Add(new RowStyle(SizeType.Absolute,48));grid.RowStyles.Add(new RowStyle(SizeType.Absolute,204));grid.RowStyles.Add(new RowStyle(SizeType.Absolute,50));grid.RowStyles.Add(new RowStyle(SizeType.Absolute,66));grid.RowStyles.Add(new RowStyle(SizeType.Percent,100));Controls.Add(grid);
   var title=new Label {Text="CAT1 双天线调试台\n4G 主天线 / GNSS 天线 · 本地串口采集",Dock=DockStyle.Fill,Font=new Font(Font.FontFamily,19,FontStyle.Bold),ForeColor=Color.FromArgb(25,45,70)};grid.Controls.Add(title);
   var connection=Row();ports.Width=130;ports.DropDownStyle=ComboBoxStyle.DropDownList;connection.Controls.Add(new Label {Text="UART0",AutoSize=true,Padding=new Padding(0,8,3,0)});connection.Controls.Add(ports);connection.Controls.Add(Button("刷新端口",RefreshPorts));connect=Button("连接",Toggle);connection.Controls.Add(connect);connection.Controls.Add(Button("恢复串口 460800",RecoverBridge));connection.Controls.Add(Button("CAT1 上电",delegate{Send("cat1_power on");}));connection.Controls.Add(new Label {Text="PC：115200 / 8N1",AutoSize=true,Padding=new Padding(6,8,0,0)});grid.Controls.Add(connection);
   var controls=Row();mode.Items.AddRange(new object[]{"ALL","LTE","GNSS"});mode.DropDownStyle=ComboBoxStyle.DropDownList;mode.SelectedIndex=0;mode.Width=90;mode.DrawMode=DrawMode.OwnerDrawFixed;mode.DrawItem+=delegate(object sender,DrawItemEventArgs e){e.DrawBackground();TextRenderer.DrawText(e.Graphics,e.Index>=0?mode.Items[e.Index].ToString():mode.Text,e.Font,e.Bounds,e.ForeColor,TextFormatFlags.Left|TextFormatFlags.VerticalCenter);};interval.Minimum=1;interval.Maximum=60;interval.Value=2;interval.Width=60;antenna.Width=140;antenna.Text="天线 A";
   controls.Controls.Add(new Label {Text="模式",AutoSize=true,Padding=new Padding(0,7,0,0)});controls.Controls.Add(mode);controls.Controls.Add(new Label {Text="间隔 / 秒",AutoSize=true,Padding=new Padding(4,7,0,0)});controls.Controls.Add(interval);controls.Controls.Add(new Label {Text="天线编号",AutoSize=true,Padding=new Padding(4,7,0,0)});controls.Controls.Add(antenna);
   controls.Controls.Add(Button("开始采样",delegate{Request("START","AT+ANTSTART="+mode.Text+","+interval.Value);}));controls.Controls.Add(Button("停止",delegate{Request("STOP","AT+ANTSTOP");}));controls.Controls.Add(Button("查询状态",delegate{Request("STATUS","AT+ANTSTATUS");}));grid.Controls.Add(controls);
   status.Dock=DockStyle.Fill;status.Font=new Font(Font.FontFamily,12,FontStyle.Bold);status.ForeColor=Color.FromArgb(30,80,135);status.Text=session.State;grid.Controls.Add(status);
   var metrics=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=2};metrics.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));metrics.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));metrics.Controls.Add(Card("4G / LTE",lte,lteAge),0,0);metrics.Controls.Add(Card("GNSS / 定位",gnss,gnssAge),1,0);grid.Controls.Add(metrics);ClearMetrics();
   var command=Row();command.Controls.Add(new Label {Text="模块命令",AutoSize=true,Padding=new Padding(0,7,0,0)});custom.Width=490;custom.Text="AT+ANTSTATUS";command.Controls.Add(custom);command.Controls.Add(Button("发送",Custom));grid.Controls.Add(command);
   paths.Dock=DockStyle.Fill;paths.Cursor=Cursors.Hand;paths.Click+=delegate{try{if(folder!=null&&Directory.Exists(folder))System.Diagnostics.Process.Start("explorer.exe",folder);}catch(Exception e){Error("无法打开日志目录："+e.Message);}};paths.Text="日志：连接时在本机 LocalAppData 自动创建会话目录\n原始收发 + CSV；所有指标均以模块真实回报为准。";paths.AutoEllipsis=true;grid.Controls.Add(paths);
   log.Multiline=true;log.ReadOnly=true;log.ScrollBars=ScrollBars.Vertical;log.Dock=DockStyle.Fill;log.BackColor=Color.White;log.Font=new Font("Consolas",9);grid.Controls.Add(log);
   timer.Interval=250;timer.Tick+=delegate{session.Tick(DateTime.UtcNow);status.Text=session.State;Age(lteAge,lteTime);Age(gnssAge,gnssTime);};timer.Start();RefreshPorts();FormClosing+=delegate{Disconnect();};
  }
  FlowLayoutPanel Row(){return new FlowLayoutPanel {Dock=DockStyle.Fill,WrapContents=false,Padding=new Padding(0,3,0,0)};}
  Button Button(string text,Action action){var b=new Button {Text=text,AutoSize=true,Height=34,FlatStyle=FlatStyle.Flat,BackColor=Color.White,Padding=new Padding(7,3,7,3),Margin=new Padding(4,0,4,0)};b.Click+=delegate{try{action();}catch(Exception e){Error(e.Message);}};return b;}
  Control Card(string title,Label value,Label age){var card=new Panel {Dock=DockStyle.Fill,BackColor=Color.White,Padding=new Padding(14),Margin=new Padding(0,0,12,12)};var heading=new Label {Text=title,Dock=DockStyle.Top,Height=30,Font=new Font(Font.FontFamily,13,FontStyle.Bold)};age.Dock=DockStyle.Bottom;age.Height=24;value.Dock=DockStyle.Fill;value.Font=new Font(Font.FontFamily,10);card.Controls.Add(value);card.Controls.Add(heading);card.Controls.Add(age);return card;}
  // SAM | 2026-10-10 19:35 +08:00 | Require explicit UART0 selection because CAT1 USB exposes lower numbered COM ports.
  void RefreshPorts(){string chosen=ports.Text;ports.Items.Clear();var names=SerialPort.GetPortNames();Array.Sort(names);ports.Items.AddRange(names);if(ports.Items.Contains(chosen))ports.SelectedItem=chosen;}
  void ClearMetrics(){lte.Text="CSQ / 注册：NA / NA\nRSRP / RSRQ / SNR：NA\nRSSI：NA    Cell / TAC：NA";gnss.Text="定位：NA    卫星可见 / 使用：NA\nCN0 / HDOP：NA  原始 SNR：NA（单位待核）\n经纬度：NA\n首次定位 / 已运行：NA";lteTime=gnssTime=DateTime.MinValue;lteAge.Text=gnssAge.Text="尚无采样数据";}
  // SAM | 2026-10-10 17:05 +08:00 | Freshness follows module ACK, not an unsent spinner edit.
  void Age(Label label,DateTime time){if(time==DateTime.MinValue){label.Text="尚无采样数据";return;}double age=(DateTime.UtcNow-time).TotalSeconds;bool stale=Session.IsStale(time,DateTime.UtcNow,session.ConfirmedInterval,session.Connected);label.Text=(stale?"过期 · ":"已更新 · ")+((int)age)+" 秒前";label.ForeColor=stale?Color.Firebrick:Color.FromArgb(30,120,90);}
  void OpenLogs(){folder=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"CAT1Antenna","sessions",DateTime.Now.ToString("yyyyMMdd_HHmmss_fff")+"_"+Guid.NewGuid().ToString("N").Substring(0,6));try{journal=new Journal(folder);paths.Text="日志目录（点击打开）："+folder+"\nraw.log（原始收发） · samples.csv（采样帧）";}catch{CloseLogs();throw;}}
  // SAM | 2026-10-10 17:59 +08:00 | Connect without sending commands because the operator flashes USB before starting AT tests.
  // SAM | 2026-10-10 19:33 +08:00 | Reinitialize UART4 at 115200 then 460800 because live antenna traffic recovered after this manual sequence.
  void RecoverBridge(){Send("cat_baud 115200");Send("cat_baud 460800");Append("已重新初始化汇顶 UART4；请查询状态确认模块回执。");}
  void Toggle(){if(session.Connected){Disconnect();return;}if(ports.SelectedItem==null)throw new InvalidOperationException("未找到串口，请连接设备后刷新");OpenLogs();try{port=new SerialPort(ports.Text,115200,Parity.None,8,StopBits.One);port.Encoding=Encoding.ASCII;port.WriteTimeout=1000;port.ReadTimeout=1000;int token=++lifetime;SerialPort source=port;port.DataReceived+=delegate{try{string data=source.ReadExisting();if(data.Length>0)BeginInvoke((Action)delegate{if(token==lifetime&&session.Connected)Receive(data);});}catch(Exception e){try{BeginInvoke((Action)delegate{if(token==lifetime){Error("串口读取失败："+e.Message);Disconnect();}});}catch(InvalidOperationException){}}};port.Open();parser=new Protocol();ClearMetrics();session.Connect();connect.Text="断开";ports.Enabled=false;Append("串口已连接，未下发命令。先完成 CAT1 USB 烧写，再点恢复串口 460800并查询状态开始 AT 调试。");}catch{Disconnect();throw;}}
  void Disconnect(){lifetime++;if(port!=null){try{port.Close();port.Dispose();}catch(Exception e){Append("关闭串口："+e.Message);}port=null;}session.Disconnect();parser=new Protocol();ClearMetrics();connect.Text="连接";ports.Enabled=true;CloseLogs();status.Text=session.State;}
  void CloseLogs(){try{if(journal!=null)journal.Dispose();}catch(Exception e){Error("日志关闭失败："+e.Message);}journal=null;}
  void WriteRaw(string direction,string text){if(journal==null)throw new IOException("日志不可用，已禁止继续操作");journal.Raw(direction,text);}
  void Send(string line){if(!session.Connected||port==null||!port.IsOpen)throw new InvalidOperationException("请先连接串口");try{WriteRaw("TX",line+"\r\n");port.Write(line+"\r\n");Append("TX > "+line);}catch(Exception e){Disconnect();throw new IOException("发送或日志失败："+e.Message);}}
  void Module(string text){if(text.IndexOf('\r')>=0||text.IndexOf('\n')>=0||text.IndexOf('\0')>=0)throw new ArgumentException("命令必须是单行文本");foreach(char c in text)if(c<32||c>126)throw new ArgumentException("模块命令仅支持 ASCII 可打印字符");if(text.Length==0||Encoding.ASCII.GetByteCount(text)+2>480)throw new ArgumentException("模块命令长度必须为 1–478 字节");if(text.Split(new char[]{' '},StringSplitOptions.RemoveEmptyEntries).Length>7)throw new ArgumentException("桥接最多支持 7 个命令文本分段");Send("cat_at "+text);}
  void Request(string op,string text){string before=session.State;session.Request(op,DateTime.UtcNow);try{Module(text);}catch{session.Pending=null;if(session.Connected)session.State=before;throw;}status.Text=session.State;}
  void Custom(){string text=custom.Text.Trim();if(text.StartsWith("AT+ANTSTART=",StringComparison.OrdinalIgnoreCase))Request("START",text);else if(text.Equals("AT+ANTSTOP",StringComparison.OrdinalIgnoreCase))Request("STOP",text);else if(text.Equals("AT+ANTSTATUS",StringComparison.OrdinalIgnoreCase))Request("STATUS",text);else Module(text);}
  void Receive(string data){try{WriteRaw("RX",data);Append("RX < "+data.TrimEnd());foreach(var f in parser.Feed(data)){if(f.Get("type")=="ACK"&&f.Get("op")=="START"&&session.Pending=="START"&&f.Get("ok")=="1")ClearMetrics();session.Accept(f);string type=f.Get("type");if(type!="LTE"&&type!="GNSS")continue;journal.Sample(f,antenna.Text);if(type=="LTE"){lteTime=DateTime.UtcNow;lte.Text="CSQ / 注册："+f.Get("csq")+" / "+f.Get("reg")+"\nRSRP / RSRQ / SNR："+f.Get("rsrp")+" / "+f.Get("rsrq")+" / "+f.Get("snr")+"\nRSSI："+f.Get("rssi")+"    Cell / TAC："+f.Get("cell")+" / "+f.Get("tac");}else{gnssTime=DateTime.UtcNow;gnss.Text="定位："+(f.Get("fix")=="1"?"有效":f.Get("fix")=="0"?"未定位":"NA")+"    卫星可见 / 使用："+f.Get("sats_view")+" / "+f.Get("sats_used")+"\nCN0 / HDOP："+f.Get("cn0_max")+" / "+f.Get("hdop")+"  原始 SNR："+f.Get("snr_max")+"（单位待核）"+"\n纬度 / 经度："+f.Get("lat")+" / "+f.Get("lon")+"\n首次定位 / 已运行 (ms)："+f.Get("ttff_ms")+" / "+f.Get("elapsed_ms");}}}catch(Exception e){Error("采集或日志失败："+e.Message);Disconnect();}}
  void Append(string text){if(log.TextLength>60000)log.Text=log.Text.Substring(log.TextLength-30000);log.AppendText(DateTime.Now.ToString("HH:mm:ss")+" "+text+Environment.NewLine);}
  void Error(string text){Append("错误："+text);MessageBox.Show(this,text,"操作失败",MessageBoxButtons.OK,MessageBoxIcon.Error);}
  [STAThread] public static void Main(string[] args){Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);using(var form=new MainForm()){if(args.Length==2&&args[0]=="--render-preview"){form.StartPosition=FormStartPosition.Manual;form.Location=new Point(-30000,-30000);form.ShowInTaskbar=false;form.Show();Application.DoEvents();File.WriteAllText(Path.GetFullPath(args[1])+".txt","UI render only; no device opened. Mode="+form.mode.Text+"; index="+form.mode.SelectedIndex);using(var bitmap=new Bitmap(form.Width,form.Height)){form.DrawToBitmap(bitmap,new Rectangle(0,0,form.Width,form.Height));bitmap.Save(Path.GetFullPath(args[1]),System.Drawing.Imaging.ImageFormat.Png);}return;}Application.Run(form);}}
 }
}










