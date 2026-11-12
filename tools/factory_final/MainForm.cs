// SAM | 2026-10-13 15:00 +08:00 | Sealed-product engineer workflow using
// BLE evidence and explicit human observations, without hidden power probes.
using System;
using System.IO;
using System.Drawing;
using System.Windows.Forms;
using System.Collections.Generic;
using System.Threading.Tasks;
namespace FactoryFinal {
 public class MainForm:Form {
  readonly BleLink ble=new BleLink();readonly Session session=new Session();readonly LineParser parser=new LineParser();
  readonly ComboBox devices=new ComboBox(),pages=new ComboBox();
  readonly TextBox operatorBox=new TextBox(),batchBox=new TextBox(),labelBox=new TextBox(),log=new TextBox();
  readonly Label connection=new Label(),info=new Label(),status=new Label(),path=new Label(),lease=new Label();
  readonly DataGridView checks=new DataGridView();readonly List<Button> actions=new List<Button>();
  readonly Dictionary<ulong,FoundDevice> found=new Dictionary<ulong,FoundDevice>();
  readonly System.Windows.Forms.Timer timer=new System.Windows.Forms.Timer();
  TaskCompletionSource<Frame> waiting;Journal journal;string folder,address="",actual="NA";
  bool busy,linked,shipAccepted;uint shipToken;DateTime leaseUntil,tokenUntil,scanUntil;
  readonly string[] items={"机身标签、外壳及NFC标识","屏幕清晰、IMEI/二维码与标签核对","左键、右键分别响应","运动/摇晃响应","语音提示与双向音频","测试SIM的4G上线","GNSS定位（按工厂测试环境）","船运不被按键/运动唤醒，插5V恢复"};
  public MainForm(){
   Text="YP001 装壳成品测试 · 工程师试用 V1";Size=new Size(1120,920);MinimumSize=new Size(1000,820);StartPosition=FormStartPosition.CenterScreen;AutoScaleMode=AutoScaleMode.Dpi;BackColor=Color.FromArgb(243,246,249);Font=new Font("Microsoft YaHei UI",10);
   var root=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=9,Padding=new Padding(20)};
   int[] heights={65,50,50,76,72,45,220,55};for(int i=0;i<heights.Length;i++)root.RowStyles.Add(new RowStyle(SizeType.Absolute,heights[i]));root.RowStyles.Add(new RowStyle(SizeType.Percent,100));Controls.Add(root);
   root.Controls.Add(new Label{Text="YP001 装壳成品测试\n蓝牙连接 · 逐台记录 · 工程师试用",Dock=DockStyle.Fill,Font=new Font(Font.FontFamily,17,FontStyle.Bold),ForeColor=Color.FromArgb(28,50,75)});
   var link=Row();link.Controls.Add(Btn("扫描蓝牙",Scan));devices.Width=460;devices.DropDownStyle=ComboBoxStyle.DropDownList;link.Controls.Add(devices);link.Controls.Add(Btn("连接",Connect));link.Controls.Add(Btn("断开",delegate{return DisconnectTask();}));connection.Text="未连接";connection.AutoSize=true;connection.Padding=new Padding(10,8,0,0);link.Controls.Add(connection);root.Controls.Add(link);
   var fields=Row();AddField(fields,"工程师",operatorBox,100);AddField(fields,"批次",batchBox,140);AddField(fields,"标签IMEI",labelBox,190);labelBox.MaxLength=15;fields.Controls.Add(Btn("读取设备",ReadInfo));root.Controls.Add(fields);
   info.Dock=DockStyle.Fill;info.BackColor=Color.White;info.Padding=new Padding(12);info.Text="设备IMEI / 固件 / 电池 / 按键 / 网络：等待蓝牙设备实读\n未知项目保留未知，不自动判为通过。";root.Controls.Add(info);
   var controls=Row();controls.Controls.Add(Btn("按住左键解锁",Unlock));pages.DropDownStyle=ComboBoxStyle.DropDownList;pages.Width=155;pages.Items.AddRange(new object[]{"IMEI/二维码页","主状态页","时间页","低电量页","通话页","结束通话页"});pages.SelectedIndex=0;controls.Controls.Add(pages);controls.Controls.Add(Btn("显示测试页",Page));controls.Controls.Add(Btn("准备船运",PrepareShip));controls.Controls.Add(Btn("确认进入船运",ConfirmShip));controls.Controls.Add(Btn("取消准备",CancelShip));lease.AutoSize=true;lease.Padding=new Padding(6,9,0,0);controls.Controls.Add(lease);root.Controls.Add(controls);
   status.Text="先连接设备并读取；改变设备状态前，按住左键点击解锁，再松开。";status.Dock=DockStyle.Fill;status.ForeColor=Color.FromArgb(30,75,120);root.Controls.Add(status);
   checks.Dock=DockStyle.Fill;checks.BackgroundColor=Color.White;checks.AllowUserToAddRows=false;checks.AllowUserToDeleteRows=false;checks.RowHeadersVisible=false;checks.AutoSizeColumnsMode=DataGridViewAutoSizeColumnsMode.Fill;checks.RowTemplate.Height=24;
   checks.Columns.Add(new DataGridViewTextBoxColumn{Name="项目",ReadOnly=true,FillWeight=70});var result=new DataGridViewComboBoxColumn{Name="人工结果",FillWeight=30};result.Items.AddRange("未测试","通过","失败");checks.Columns.Add(result);foreach(string item in items)checks.Rows.Add(item,"未测试");root.Controls.Add(checks);
   var records=Row();records.Controls.Add(Btn("保存测试记录",Save));records.Controls.Add(Btn("打开记录目录",OpenFolder));path.AutoSize=true;path.MaximumSize=new Size(700,48);path.Padding=new Padding(6,6,0,0);path.Text="每次连接建立独立记录；蓝牙断开不等于零电流。";records.Controls.Add(path);root.Controls.Add(records);
   log.Multiline=true;log.ReadOnly=true;log.Dock=DockStyle.Fill;log.ScrollBars=ScrollBars.Vertical;log.Font=new Font("Consolas",9);log.BackColor=Color.White;root.Controls.Add(log);
   ble.Discovered+=delegate(FoundDevice d){OnUI(delegate{FoundDevice old;if(found.TryGetValue(d.Address,out old)){old.Rssi=d.Rssi;}else{found[d.Address]=d;devices.Items.Add(d);}});};
   ble.Received+=delegate(string text){OnUI(delegate{try{Log("RX",text);foreach(var f in parser.Feed(text)){var matched=session.Accept(f);if(matched!=null&&waiting!=null)waiting.TrySetResult(matched);}}catch(Exception e){LinkFailed("记录/解析失败："+e.Message);}});};
   ble.Lost+=delegate(string reason){OnUI(delegate{linked=false;shipToken=0;leaseUntil=DateTime.MinValue;connection.Text="已断开";session.Abort();if(waiting!=null)waiting.TrySetException(new IOException(reason));status.Text=shipAccepted?"船运指令已接受，随后蓝牙断开；请人工观察按键/运动及插5V恢复。":reason+"；结果不确定，请重新连接读取。";TryLog("LINK",status.Text);});};
   timer.Interval=250;timer.Tick+=delegate{if(scanUntil!=DateTime.MinValue&&DateTime.UtcNow>=scanUntil){ble.StopScan();scanUntil=DateTime.MinValue;connection.Text=linked?"已连接":"扫描结束，请选择产品";}lease.Text=DateTime.UtcNow<leaseUntil?"解锁剩余 "+Math.Ceiling((leaseUntil-DateTime.UtcNow).TotalSeconds)+" 秒":"未解锁";if(shipToken!=0&&DateTime.UtcNow>=tokenUntil){shipToken=0;status.Text="船运确认已过期，请取消准备后重试。";}};timer.Start();
   FormClosing+=delegate{ble.Dispose();if(journal!=null)journal.Dispose();timer.Stop();};
  }
  FlowLayoutPanel Row(){return new FlowLayoutPanel{Dock=DockStyle.Fill,WrapContents=true,Margin=new Padding(0)};}
  void AddField(FlowLayoutPanel row,string name,TextBox field,int width){row.Controls.Add(new Label{Text=name,AutoSize=true,Padding=new Padding(4,8,4,0)});field.Width=width;row.Controls.Add(field);}
  Button Btn(string text,Func<Task> action){var b=new Button{Text=text,AutoSize=true,Height=34,Padding=new Padding(5,2,5,2)};actions.Add(b);b.Click+=async delegate{if(busy)return;busy=true;EnableActions(false);try{await action();}catch(Exception e){status.Text=e.Message;status.ForeColor=Color.Firebrick;TryLog("ERROR",e.Message);}finally{busy=false;EnableActions(true);}};return b;}
  void EnableActions(bool enabled){foreach(var b in actions)b.Enabled=enabled;devices.Enabled=enabled;pages.Enabled=enabled;}
  void OnUI(Action a){if(IsDisposed||Disposing)return;try{if(InvokeRequired)BeginInvoke(a);else a();}catch(InvalidOperationException){}}
  void Log(string direction,string data){if(journal!=null)journal.Raw(direction,data);log.AppendText(Journal.Stamp()+" "+direction+" "+data+Environment.NewLine);if(log.TextLength>120000)log.Text=log.Text.Substring(log.TextLength-60000);}
  void TryLog(string direction,string data){try{Log(direction,data);}catch(Exception e){session.Abort();status.Text="本地记录失败："+e.Message;status.ForeColor=Color.Firebrick;}}
  void LinkFailed(string reason){linked=false;session.Abort();if(waiting!=null)waiting.TrySetException(new IOException(reason));ble.Disconnect();connection.Text="连接不可用";status.Text=reason;}
  async Task<Frame> Command(string op,string arg){
   if(!linked)throw new InvalidOperationException("请先连接产品。");
   string cmd=session.Start(op,arg,DateTime.UtcNow);waiting=new TaskCompletionSource<Frame>();
   Frame f;
   try{Log("TX",cmd);await ble.Send(cmd);int remain=(int)Math.Max(0,(session.Deadline-DateTime.UtcNow).TotalMilliseconds);var completed=await Task.WhenAny(waiting.Task,Task.Delay(remain));if(completed!=waiting.Task){session.Abort();throw new TimeoutException("等待设备回执超时，结果不确定。请重新连接后读取。");}f=await waiting.Task;}
   catch{session.Abort();throw;}finally{waiting=null;}
   if(!f.Ok)throw new InvalidOperationException("设备拒绝 "+op+"："+f.Raw);return f;
  }
  Task Scan(){if(linked)throw new InvalidOperationException("请先断开当前设备再扫描。");found.Clear();devices.Items.Clear();ble.Scan();scanUntil=DateTime.UtcNow.AddSeconds(12);connection.Text="扫描中（12秒）";status.ForeColor=Color.FromArgb(30,75,120);return Task.FromResult(0);}
  async Task Connect(){
   var d=devices.SelectedItem as FoundDevice;if(d==null)throw new InvalidOperationException("请选择本次扫描到的产品地址；不要仅凭相同名称判断。");
   // SAM | 2026-10-13 15:28 +08:00 | Associate a wake test with its prior
   // record only after identity match or an explicit same-label observation.
   string priorFolder=folder,priorLabel=labelBox.Text,priorActual=actual,priorAddress=address;
   bool recovery=shipAccepted;var priorResults=new string[items.Length];
   checks.EndEdit();for(int i=0;i<items.Length;i++)priorResults[i]=Convert.ToString(checks.Rows[i].Cells[1].Value);
   if(journal!=null){journal.Dispose();journal=null;}folder=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"YP001FactoryFinal","sessions",DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8)).ToString("yyyyMMdd_HHmmss")+"_"+Guid.NewGuid().ToString("N").Substring(0,8));
   journal=new Journal(folder);path.Text=folder;actual="NA";address=d.Address.ToString("X12");labelBox.Text="";shipAccepted=false;shipToken=0;leaseUntil=DateTime.MinValue;foreach(DataGridViewRow row in checks.Rows)row.Cells[1].Value="未测试";parser.Reset();session.Reconnect();
   try{Log("CONNECT",address);await ble.Connect(d.Address,d.AddressType);linked=true;connection.Text="已连接 "+address;await ReadInfo();
    if(recovery&&priorFolder!=null&&priorLabel.Length==15){
     bool verified=Session.IdentityMatches(priorLabel,actual)&&(priorActual=="NA"||Session.IdentityMatches(priorActual,actual));
     bool manual=!verified&&actual=="NA"&&address==priorAddress&&MessageBox.Show(this,
      "设备IMEI仍未知。请核对当前机身标签是否仍为 "+priorLabel+"。\n相同则关联原记录，仍标记为人工关联；不同请选择取消。",
      "关联插5V恢复测试",MessageBoxButtons.OKCancel,MessageBoxIcon.Question)==DialogResult.OK;
     if(verified||manual){labelBox.Text=priorLabel;for(int i=0;i<items.Length;i++)checks.Rows[i].Cells[1].Value=priorResults[i];
      Log("RECOVERY","prior_session="+priorFolder+" identity="+(verified?"device_imei_match":"manual_label_only"));
      SaveReport(verified?"插5V后蓝牙/身份读取恢复，关联原记录":"插5V后蓝牙读取恢复；人工关联原标签，设备IMEI仍未知");
     }else Log("RECOVERY","未关联：身份不匹配或未人工确认；原记录保留在 "+priorFolder);
    }
   }catch{linked=false;ble.Disconnect();throw;}
  }
  Task DisconnectTask(){TryLog("DISCONNECT","人工断开；不证明设备掉电");ble.Disconnect();linked=false;shipToken=0;leaseUntil=DateTime.MinValue;parser.Reset();session.Reconnect();connection.Text="已断开";return Task.FromResult(0);}
  async Task ReadInfo(){Frame f=await Command("INFO",null);actual=f.Get("imei");
   string battery=f.Get("adc")=="1"?f.Get("mv")+" mV / 估算 "+f.Get("bat")+"%":"未知";
   string[] calls={"空闲","拨号中","来电","通话中","已结束","失败","未知"};
   string[] networks={"未知","无SIM","注册中","IP就绪","MQTT就绪","离线"};
   uint call=f.Number("call",99),net=f.Number("net",99);
   info.Text="设备IMEI："+(actual=="NA"?"未知":actual)+"    测试固件标识："+f.Get("fw")+"    电池ADC："+battery+
    "\n左键："+Flag(f.Get("left"),"按下","松开")+"  右键："+Flag(f.Get("right"),"按下","松开")+
    "  报警："+Flag(f.Get("alarm"),"进行中","无")+"  通话："+(call<calls.Length?calls[call]:"未知")+
    "  网络："+(net<networks.Length?networks[net]:"未知")+"  5V输入："+(f.Get("chg_ok")=="1"?Flag(f.Get("vin"),"有","无"):"未知");
   status.Text=actual=="NA"?"设备IMEI尚未获取。记录保留未知，人工核对不能自动替代实读。":"设备信息已更新，请核对标签IMEI并逐项测试。";status.ForeColor=Color.FromArgb(30,75,120);
  }
  // SAM | 2026-10-13 16:08 +08:00 | Operators see state meanings;
  // raw enum numbers remain in logs for engineering diagnosis.
  static string Flag(string value,string yes,string no){return value=="1"?yes:value=="0"?no:"未知";}
  async Task Unlock(){leaseUntil=DateTime.MinValue;await Command("UNLOCK",null);leaseUntil=DateTime.UtcNow.AddSeconds(60);status.Text="已解锁，请松开左键。60秒内可选测试页或准备船运。";}
  void RequireLease(){if(DateTime.UtcNow>=leaseUntil)throw new InvalidOperationException("请按住左键点击解锁，然后松开。");}
  async Task Page(){RequireLease();await Command("PAGE",pages.SelectedIndex.ToString());status.Text="测试页已提交，请观察实屏；页面回执不代替屏幕检查。";}
  async Task PrepareShip(){RequireLease();await Command("CAT_OFF",null);
   // Wait for the existing business owner's real link timeout, not a host flag.
   DateTime offlineDeadline=DateTime.UtcNow.AddSeconds(25);Frame offline;
   do{offline=await Command("INFO",null);if(offline.Get("link")=="0")break;status.Text="CAT1关电请求已接受，等待业务离线确认…";await Task.Delay(500);}while(DateTime.UtcNow<offlineDeadline);
   if(offline.Get("link")!="0")throw new InvalidOperationException("业务仍在线，未进入船运准备。请核对供电/通信后重试。");
   Frame f=await Command("SHIP_PREP",null);for(int i=0;i<12&&f.Number("state",99)==1;i++){await Task.Delay(350);f=await Command("SHIP_STATUS",null);}if(f.Number("state",99)!=2||f.Number("token",0)==0)throw new InvalidOperationException("船运未就绪。请检查5V已拔、按键已松开、无报警/通话、CAT1离线；重新连接读取状态。");shipToken=f.Number("token",0);tokenUntil=DateTime.UtcNow.AddSeconds(25);status.Text="船运准备完成，确认有效约25秒。确认后约12秒切断，插5V恢复。";}
  async Task ConfirmShip(){RequireLease();if(shipToken==0||DateTime.UtcNow>=tokenUntil)throw new InvalidOperationException("请重新准备船运。");
   if(MessageBox.Show(this,"当前设备 "+address+"\n标签IMEI："+(labelBox.Text.Length==0?"未填写":labelBox.Text)+"\n确认后预计约12秒切断；需插5V恢复。请保持5V拔掉。","确认当前产品进入船运",MessageBoxButtons.OKCancel,MessageBoxIcon.Warning)!=DialogResult.OK)return;
   SaveReport("准备下发船运；尚未证明掉电");Frame f=await Command("SHIP_CONFIRM",shipToken.ToString());shipToken=0;
   if(f.Number("state",99)!=3||f.Get("attempted")!="1")throw new InvalidOperationException("船运接受状态异常，请保留记录并重新读取。");
   shipAccepted=true;Log("SHIP","指令已接受；等待蓝牙断开；零电流未测");SaveReport("船运指令已接受；物理断电/电流未测");status.Text="船运指令已接受，等待约12秒。蓝牙断开后人工观察，再插5V验证恢复。";
  }
  async Task CancelShip(){RequireLease();await Command("SHIP_CANCEL",null);shipToken=0;status.Text="准备已取消；已经尝试写BATFET的状态不能取消。";}
  void SaveReport(string forced){if(journal==null)throw new InvalidOperationException("请先建立设备测试记录。");checks.EndEdit();var results=new string[items.Length];bool pass=true,fail=false;for(int i=0;i<items.Length;i++){results[i]=Convert.ToString(checks.Rows[i].Cells[1].Value);pass&=results[i]=="通过";fail|=results[i]=="失败";}
   string summary=forced??(fail?"有失败项":pass&&Session.IdentityMatches(labelBox.Text,actual)?"人工项目通过且身份匹配；工程师试测记录，电流未测":"未完成或身份未核对");
   journal.Save(labelBox.Text,actual,address,operatorBox.Text,batchBox.Text,items,results,summary);status.Text="记录已保存："+summary;
  }
  Task Save(){SaveReport(null);return Task.FromResult(0);}
  Task OpenFolder(){if(folder==null||!Directory.Exists(folder))throw new InvalidOperationException("暂无本机测试记录。");System.Diagnostics.Process.Start("explorer.exe",folder);return Task.FromResult(0);}
  [STAThread]static void Main(string[] args){Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);using(var form=new MainForm()){
   if(args.Length==2&&args[0]=="--render-preview"){form.StartPosition=FormStartPosition.Manual;form.Location=new Point(-30000,-30000);form.ShowInTaskbar=false;form.Show();Application.DoEvents();using(var bitmap=new Bitmap(form.Width,form.Height)){form.DrawToBitmap(bitmap,new Rectangle(0,0,form.Width,form.Height));bitmap.Save(Path.GetFullPath(args[1]),System.Drawing.Imaging.ImageFormat.Png);}return;}
   Application.Run(form);
  }}
 }
}
