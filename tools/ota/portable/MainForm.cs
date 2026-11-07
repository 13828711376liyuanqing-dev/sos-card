// SAM | 2026-10-22 +08:00 | Portable WinForms operator UI; capacity checks precede archive generation.
using System;
using System.IO;
using System.IO.Ports;
using System.Diagnostics;
using System.Drawing;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace YpOta {
public class MainForm:Form {
 TextBox gr=new TextBox(),cat=new TextBox(),from=new TextBox(),to=new TextBox(),prefix=new TextBox(),suffix=new TextBox(),output=new TextBox(),free=new TextBox();
 TextBox log=new TextBox();Label preview=new Label();Button pack=new Button();ComboBox ports=new ComboBox();
 // SAM | 2026-10-22 11:35 +08:00 | Expose native generation so operators never have to guess a CAT1 input file.
 TextBox source=new TextBox(),luatools=new TextBox();Button generateCat=new Button();
 Button prepareVersion=new Button();
 // SAM | 2026-10-24 +08:00 | Optional explicit device admission; empty keeps transport-only archives.
 TextBox admission=new TextBox();
 // SAM | 2026-10-24 +08:00 | Offline candidates need no invented FS reading; keep strict packaging as the default.
 CheckBox offline=new CheckBox();
 // SAM | 2026-10-22 +08:00 | Source-version preparation, serial reads and packaging must not overlap through separate buttons.
 bool busy;
 public MainForm() {
  Text="YP001 双固件OTA打包工具 — CAT1原生生成 / 容量检查";Size=new Size(1050,920);MinimumSize=new Size(950,850);
  Font=new Font("Microsoft YaHei UI",10);StartPosition=FormStartPosition.CenterScreen;
  TableLayoutPanel table=new TableLayoutPanel();table.Dock=DockStyle.Fill;table.Padding=new Padding(16);table.ColumnCount=3;table.RowCount=17;table.AutoScroll=true;
  table.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,190));table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));table.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,120));
  Controls.Add(table);int row=0;
  Add(table,row++,"CAT1源码文件夹",source,()=>PickFolder(source));
  source.Text=Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"..","Air780EGH"));
  Add(table,row++,"Luatools工具文件夹",luatools,()=>PickFolder(luatools));if(Directory.Exists(@"D:\Installers\_temp\tools"))luatools.Text=@"D:\Installers";
  generateCat.Text="① 从源码生成CAT1 OTA（.sota）";generateCat.AutoSize=true;generateCat.Dock=DockStyle.Fill;generateCat.Click+=(s,e)=>BuildCat();table.Controls.Add(generateCat,0,row);table.SetColumnSpan(generateCat,3);row++;
  Add(table,row++,"GR5526 HEX/BIN",gr,()=>Pick(gr));Add(table,row++,"CAT1原生OTA（.sota）",cat,()=>Pick(cat));
  // SAM | 2026-10-22 +08:00 | Show the real baseline/target used for the first controlled firmware pair.
  Add(table,row++,"整机源版本（如1.0.0）",from,null);from.Text="1.0.0";Add(table,row++,"整机目标版本（如1.0.1）",to,null);to.Text="1.0.1";
  // SAM | 2026-10-22 +08:00 | Preparing a higher version must rebuild the actual firmware instead of relabeling existing files.
  prepareVersion.Text="准备目标版本固件（更新两端版本、编译GR、生成CAT1）";prepareVersion.AutoSize=true;prepareVersion.Dock=DockStyle.Fill;prepareVersion.Click+=(s,e)=>PrepareVersion();table.Controls.Add(prepareVersion,0,row);table.SetColumnSpan(prepareVersion,3);row++;
  Add(table,row++,"名称前缀（可改）",prefix,null);prefix.Text="YP001";Add(table,row++,"名称后缀（可改）",suffix,null);
  Add(table,row++,"输出文件夹",output,()=>{using(FolderBrowserDialog d=new FolderBrowserDialog()){if(d.ShowDialog()==DialogResult.OK)output.Text=d.SelectedPath;}});
  output.Text=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"output");
  Add(table,row++,"CAT1可用FS字节（必填）",free,null);
  offline.Text="仅生成离线候选（空间未知，不授权终端安装）";offline.AutoSize=true;
  offline.CheckedChanged+=(s,e)=>free.Enabled=!offline.Checked;
  table.Controls.Add(offline,0,row);table.SetColumnSpan(offline,3);row++;
  Add(table,row++,"安装准入JSON（可选）",admission,()=>{
   using(var d=new OpenFileDialog()){d.Filter="安装准入记录 (*.json)|*.json";if(d.ShowDialog()==DialogResult.OK)admission.Text=d.FileName;}
  });
  FlowLayoutPanel serial=new FlowLayoutPanel();serial.AutoSize=true;ports.DropDownStyle=ComboBoxStyle.DropDownList;ports.Width=110;
  foreach(string p in SerialPort.GetPortNames())ports.Items.Add(p);if(ports.Items.Count>0)ports.SelectedIndex=0;
  // SAM | 2026-10-22 +08:00 | Make the power-changing action explicit; the previous query could not reach an unpowered CAT1.
  // SAM | 2026-10-22 +08:00 | Present one complete action instead of making the operator choose rail-only versus cold start.
  Button query=new Button();query.Text="启动CAT1并读取空间";query.AutoSize=true;query.Click+=(s,e)=>Query(query);serial.Controls.Add(ports);serial.Controls.Add(query);
  Button refresh=new Button();refresh.Text="刷新串口";refresh.AutoSize=true;refresh.Click+=(s,e)=>{ports.Items.Clear();ports.Items.AddRange(SerialPort.GetPortNames());if(ports.Items.Count>0)ports.SelectedIndex=0;};serial.Controls.Add(refresh);
  table.Controls.Add(new Label(){Text="终端诊断口",AutoSize=true},0,row);table.Controls.Add(serial,1,row++);
  preview.AutoSize=true;preview.MaximumSize=new Size(750,0);table.Controls.Add(preview,0,row);table.SetColumnSpan(preview,3);row++;
  Label note=new Label();note.AutoSize=true;note.MaximumSize=new Size(900,0);note.ForeColor=Color.DarkRed;
// SAM | 2026-10-23 +08:00 | Enforce selected preserved-data slot limit; deployment is not approved.
  note.Text="两端实际固件版本必须对应整机目标版本；只改包名会被拒绝，需先设置源码版本并重新编译。\r\n5526槽442368B（含904B签名预算）；CAT1脚本512KiB，用户FS保留16384B。\r\n使用keys/OTA_TEST_PRIVATE.key签名；终端验签与安装待验收。CAT1支持V2052 Air780EGH_113同底包。";
  table.Controls.Add(note,0,row);table.SetColumnSpan(note,3);row++;
  pack.Text="检查容量、KEY签名并生成升级归档";pack.AutoSize=true;pack.Dock=DockStyle.Fill;pack.Click+=(s,e)=>Generate();table.Controls.Add(pack,0,row);table.SetColumnSpan(pack,3);row++;
  log.Multiline=true;log.ReadOnly=true;log.ScrollBars=ScrollBars.Vertical;log.Dock=DockStyle.Fill;table.Controls.Add(log,0,row);table.SetColumnSpan(log,3);table.RowStyles.Add(new RowStyle(SizeType.AutoSize));
  // SAM | 2026-10-24 +08:00 | Keep the new mode row from consuming the log area through implicit table row sizing.
  table.RowCount=row+1;table.RowStyles.Clear();
  for(int i=0;i<row;i++)table.RowStyles.Add(new RowStyle(SizeType.AutoSize));
  table.RowStyles[row-1]=new RowStyle(SizeType.Absolute,40);
  table.RowStyles.Add(new RowStyle(SizeType.Percent,100));log.MinimumSize=new Size(0,100);
  // SAM | 2026-10-29 08:16 +08:00 | Preview matches the short upload name (no random tag, .zip) requested by the user.
  foreach(TextBox t in new[]{from,to,prefix,suffix})t.TextChanged+=(s,e)=>{preview.Text="包名预览："+prefix.Text+"_"+from.Text+"---"+to.Text+"_"+suffix.Text+".zip";};
  foreach(TextBox t in new[]{gr,cat,output,source,luatools}) {
   ContextMenuStrip menu=new ContextMenuStrip();menu.Items.Add("打开所在文件夹",null,(s,e)=>Reveal(t.Text));t.ContextMenuStrip=menu;
  }
 }
 void Add(TableLayoutPanel table,int row,string text,TextBox value,Action choose) {
  table.Controls.Add(new Label(){Text=text,AutoSize=true,Margin=new Padding(3,8,3,8)},0,row);value.Dock=DockStyle.Fill;table.Controls.Add(value,1,row);
  if(choose!=null){Button b=new Button(){Text="选择…",Dock=DockStyle.Fill};b.Click+=(s,e)=>choose();table.Controls.Add(b,2,row);}
 }
 void PickFolder(TextBox t){using(FolderBrowserDialog d=new FolderBrowserDialog()){if(Directory.Exists(t.Text))d.SelectedPath=t.Text;if(d.ShowDialog()==DialogResult.OK)t.Text=d.SelectedPath;}}
 void Pick(TextBox t){using(OpenFileDialog d=new OpenFileDialog()){d.Filter=t==cat?"CAT1原生脚本OTA (*.sota)|*.sota":"GR5526应用固件 (*.hex;*.bin)|*.hex;*.bin";if(t==cat&&Directory.Exists(Path.Combine(source.Text,"_ota_release")))d.InitialDirectory=Path.Combine(source.Text,"_ota_release");if(d.ShowDialog()==DialogResult.OK)t.Text=d.FileName;}}
 async void BuildCat(){
  if(busy)return;busy=true;
  string src=source.Text,tools=luatools.Text;generateCat.Enabled=false;pack.Enabled=false;prepareVersion.Enabled=false;
  try{log.Text="正在编译Lua、生成原生SOTA并解压逐字节校验，请稍候…";
   Cat1Image result=await Task.Run(()=>Cat1Native.Build(src,tools,Path.Combine(src,"_ota_release")));cat.Text=result.File;
   log.Text="CAT1原生脚本OTA已生成并自动选中：\r\n"+result.File+"\r\n源码实际版本："+result.Version+"（工具未修改）\r\n脚本 "+result.ScriptBytes+" / "+Cat1Native.ScriptCapacity+" 字节；OTA "+result.PackageBytes+" / "+(Cat1Native.FotaRegion-Cat1Native.BackupBytes)+" 字节。\r\n解压读回、MD5、写入地址检查通过。请与同名.json一起保留；实板安装尚未验证。";
  }catch(Exception e){Error(e);log.Text=e.Message;}finally{busy=false;generateCat.Enabled=true;pack.Enabled=true;prepareVersion.Enabled=true;}
 }
 async void PrepareVersion(){
  if(busy)return;busy=true;
  prepareVersion.Enabled=false;generateCat.Enabled=false;pack.Enabled=false;
  try{
   string target=FirmwareIdentity.Normalize(to.Text.Trim());if(PackCore.CompareVersion(target,from.Text.Trim())<=0)throw new Exception("目标版本必须高于源版本");
   string root=Path.GetFullPath(Path.Combine(source.Text,"..")),release=Path.Combine(root,"firmware_releases",target),tools=luatools.Text;
   if(!Directory.Exists(release)){
    string script=Path.Combine(root,@"tools\ota\Build-VersionedRelease.ps1");if(!File.Exists(script))throw new Exception("准备新版本需要完整项目和已配置Keil；请选择项目Air780EGH目录");
    if(script.Contains("\"")||tools.Contains("\""))throw new Exception("目录不能含引号");
    // SAM | 2026-10-24 +08:00 | Match the user's main-project-only release policy; no delivery build is performed.
    log.Text="正在准备目标 "+target+"：会更新两端源码版本并编译主GR工程，耗时数分钟；不会烧录设备。\r\n";
    await Task.Run(()=>{
     string powershell=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),@"WindowsPowerShell\v1.0\powershell.exe");
     var si=new ProcessStartInfo(powershell,"-NoProfile -ExecutionPolicy Bypass -File \""+script+"\" -Version "+target+" -LuatoolsRoot \""+tools+"\""){UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true};
     using(var p=new Process()){p.StartInfo=si;p.OutputDataReceived+=(s,e)=>{if(e.Data!=null&&!IsDisposed&&IsHandleCreated)BeginInvoke((Action)(()=>log.AppendText(e.Data+Environment.NewLine)));};p.Start();p.BeginOutputReadLine();Task<string> errors=p.StandardError.ReadToEndAsync();p.WaitForExit();if(p.ExitCode!=0)throw new Exception("版本准备失败："+errors.Result+"\r\n请查看firmware_releases中的_building目录日志；未烧录设备。");}
    });
   }else log.Text="选择已冻结的目标版本 "+target+"；复用其固件，不覆盖版本目录或重新编译当前源码。\r\n";
   string g=Path.Combine(release,@"GR5526\YP001_GR5526.hex");string[] files=Directory.GetFiles(Path.Combine(release,"CAT1"),"*.sota");if(files.Length!=1)throw new Exception("受控版本目录缺少唯一CAT1 SOTA");
   FirmwareIdentity.MatchTarget(PackCore.ReadGr(g),target,target);gr.Text=g;cat.Text=files[0];
   log.AppendText("目标版固件已选中：\r\n"+g+"\r\n"+files[0]+"\r\n继续读取设备空间并生成签名升级归档；设备当前版本仍需实测确认。");
  }catch(Exception e){Error(e);}finally{busy=false;prepareVersion.Enabled=true;generateCat.Enabled=true;pack.Enabled=true;}
 }
 void Reveal(string path){try{if(File.Exists(path))Process.Start("explorer.exe","/select,\""+Path.GetFullPath(path)+"\"");else if(Directory.Exists(path))Process.Start("explorer.exe","\""+Path.GetFullPath(path)+"\"");else MessageBox.Show("路径不存在");}catch(Exception e){Error(e);}}
 // SAM | 2026-10-22 +08:00 | Probe first, then request the rail once and wait without blocking the operator UI or toggling PWRKEY.
 async void Query(Button button) {
  if(busy)return;busy=true;
  button.Parent.Enabled=false;pack.Enabled=false;generateCat.Enabled=false;prepareVersion.Enabled=false;free.Clear();
  try {
   if(ports.SelectedItem==null)throw new Exception("请选择终端诊断串口");
   string name=ports.SelectedItem.ToString();log.Text="正在检查CAT1响应；必要时通过GR5526上电并等待启动…";
   string response=await Task.Run(()=>{
    using(SerialPort port=new SerialPort(name,115200)){port.DtrEnable=false;port.RtsEnable=false;port.WriteTimeout=2000;port.Open();StringBuilder buffer=new StringBuilder();
     Func<string,int,string> exchange=(command,wait)=>{buffer.Clear();port.DiscardInBuffer();port.Write(command+"\r\n");System.Diagnostics.Stopwatch timer=System.Diagnostics.Stopwatch.StartNew();
      while(timer.ElapsedMilliseconds<wait){Thread.Sleep(100);buffer.Append(port.ReadExisting());if(buffer.Length>131072)throw new Exception("诊断日志量过大，停止查询");
       string current=buffer.ToString();if(Regex.IsMatch(current,@"OTA_SPACE=\{[^\r\n]*\}"))return current;
       if(command=="cat1_power on"&&Regex.IsMatch(current,@"\[CAT1 POWER\][^\r\n]*rail_request=on code=0x[0-9A-Fa-f]{4}[^\r\n]*\r?\n"))return current;
      }return buffer.ToString();};
     return DeviceSpace.Query(exchange,message=>BeginInvoke((Action)(()=>log.Text=message)),false,()=>
      (bool)Invoke((Func<bool>)(()=>MessageBox.Show(this,"CAT1电源轨已开启，但尚无空间回包。当前GR固件没有提供可靠的模块运行状态，无法区分未启动与通信故障。\r\n\r\n仅当确认CAT1尚未启动时，执行一次启动键；已运行时请取消并检查通信。\r\n是否执行一次启动键操作？","确认CAT1启动状态",MessageBoxButtons.OKCancel,MessageBoxIcon.Question)==DialogResult.OK)));
    }
   });
   Match m=Regex.Match(response,@"OTA_SPACE=(\{[^\r\n]*\})");if(!m.Success)throw new Exception("未收到完整CAT1空间回包");
   var values=PackCore.Json.Deserialize<System.Collections.Generic.Dictionary<string,object>>(m.Groups[1].Value);
   if(!values.ContainsKey("ok")||!(bool)values["ok"])throw new Exception("设备报告空间无效");
   int total=Convert.ToInt32(values["total_bytes"]),available=Convert.ToInt32(values["free_bytes"]);
   if(total!=PackCore.CatFsTotal || available<0 || available>total)throw new Exception("设备文件区与当前容量基线不符，拒绝自动套用");
   free.Text=available.ToString();log.Text="设备空间查询成功：FS总"+total+"字节，可用"+available+"字节。\r\n无回复时已请求开启CAT1电源轨；模块保持当前电源状态。未执行烧录或安装。";
  } catch(Exception e){log.Text=e.Message;Error(e);}finally{busy=false;button.Parent.Enabled=true;pack.Enabled=true;generateCat.Enabled=true;prepareVersion.Enabled=true;}
 }
 // SAM | 2026-10-24 +08:00 | Null denotes unknown offline space; zero/invalid input never passes strict mode.
 int? ReadPackagingSpace(){
  if(offline.Checked)return null;
  int available;
  if(!int.TryParse(free.Text,out available)||available<=PackCore.Reserve||available>PackCore.CatFsTotal)
   throw new Exception("严格模式必须读取或输入CAT1真实可用空间（大于16384且不超过524288字节）；未知时只能选择离线候选");
  return available;
 }
 async void Generate() {
  if(busy)return;busy=true;
  pack.Enabled=false;generateCat.Enabled=false;prepareVersion.Enabled=false;
  try {
   int? available=ReadPackagingSpace();
   string g=gr.Text,c=cat.Text,o=output.Text,f=from.Text.Trim(),t=to.Text.Trim(),p=prefix.Text,s=suffix.Text,l=luatools.Text,a=admission.Text.Trim();
   if(a.Length>0&&!available.HasValue)throw new Exception("安装测试包必须读取真实可用空间，不能使用离线空间模式");
   log.Text="正在检查容量并解压验证CAT1原生OTA…";
   // SAM | 2026-10-24 +08:00 | Capture mode before background work; both routes retain capacity, firmware identity and signature checks.
   string file=await Task.Run(()=>a.Length>0?PackCore.PackageForDevice(g,c,o,f,t,p,s,available.Value,a,l,null):available.HasValue?PackCore.Package(g,c,o,f,t,p,s,available.Value,l):PackCore.PackageOfflineCandidate(g,c,o,f,t,p,s, l));
   log.Text="容量检查、CAT1原生解压、KEY签名及固定公钥验签、组件HASH读回通过：\r\n"+file+
    (available.HasValue?"\r\n采用操作员提供的空间值，终端仍须实时检查。":"\r\n仅离线候选：实机可用空间未知（null），仅静态布局检查，终端仍须实时检查。")+
    (a.Length>0?"\r\n安装测试准入已绑定本次组件和底包，device_installable=true；终端仍检查实时安全条件，真实安装尚未验收。":"\r\n仅联调归档，device_installable=false。未选择或未满足安装准入不能用于安装。")+"\r\n本地测试KEY；私钥未装入归档。";
   MessageBox.Show(log.Text,"联调归档生成完成",MessageBoxButtons.OK,MessageBoxIcon.Information);
  } catch(Exception e){Error(e);} finally {busy=false;pack.Enabled=true;generateCat.Enabled=true;prepareVersion.Enabled=true;}
 }
 static void Error(Exception e){Program.Record(e);MessageBox.Show(e.Message+"\r\n详细原因已写入错误日志。","检查未通过",MessageBoxButtons.OK,MessageBoxIcon.Error);}
}
public static class Program {
 public static void Record(Exception e){try{File.AppendAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"startup_error.log"),DateTimeOffset.Now.ToString("o")+" "+e+Environment.NewLine,Encoding.UTF8);}catch{}}
 [STAThread] public static void Main(string[] args){
  try{Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);if(args.Length>0&&args[0]=="--startup-check"){using(MainForm f=new MainForm()){f.Show();Application.DoEvents();f.PerformLayout();f.Refresh();if(args.Length>1){using(Bitmap preview=new Bitmap(f.Width,f.Height)){f.DrawToBitmap(preview,new Rectangle(Point.Empty,f.Size));preview.Save(args[1],System.Drawing.Imaging.ImageFormat.Png);}}}return;}Application.Run(new MainForm());}
  // SAM | 2026-10-22 11:35 +08:00 | Automated startup checks must fail without blocking on a desktop dialog.
  catch(Exception e){Record(e);if(args.Length==0||args[0]!="--startup-check")MessageBox.Show("工具启动失败："+e.Message+"\r\n请查看同目录startup_error.log。");Environment.ExitCode=1;}
 }
}}
