// SAM | 2026-10-22 +08:00 | Boundary checks execute without device writes or WinForms.
using System;using System.IO;using System.IO.Compression;
namespace YpOta {class CoreTests {
 static int count;
 static void Check(bool value){count++;if(!value)throw new Exception("Assertion "+count);}
 static void Reject(Action action){bool failed=false;try{action();}catch{failed=true;}Check(failed);}
 static void RejectMessage(Action action,string text){string message="";try{action();}catch(Exception e){message=e.Message;}Check(message.Contains(text));}
 // SAM | 2026-10-22 11:24 +08:00 | Report negative-test failures without a Windows unhandled-exception dialog.
 static int Main(){try{Run();return 0;}catch(Exception e){Console.Error.WriteLine("FAIL: "+e.Message);return 1;}}
 static void Run(){
  Check(PackCore.CompareVersion("1.10","1.9")>0);Check(PackCore.CompareVersion("1.0","1.0.0")==0);
  Reject(()=>PackCore.CompareVersion("01.0","1.0"));Reject(()=>PackCore.CompareVersion("v1.0","1.0"));
  PackCore.CheckSpace(PackCore.GrSlot-PackCore.SignatureBytes,100,495616);count++;
  Reject(()=>PackCore.CheckSpace(PackCore.GrSlot-PackCore.SignatureBytes+1,100,495616));
  Reject(()=>PackCore.CheckSpace(100,479233,495616));Reject(()=>PackCore.CheckSpace(100,100,0));
  Reject(()=>PackCore.CheckSpace(100,100,524289));Reject(()=>PackCore.CheckSpace(477536,100,478439+16384));
  string dir=Path.Combine(Path.GetTempPath(),"unused"); // No file writes against this path.
  Reject(()=>PackCore.Package("missing","missing",dir,"1.3","1.0","name","",495616));
  string root=Path.Combine(Environment.CurrentDirectory,"logs","portable_packager_tests",Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);
  string app=Path.Combine(Environment.CurrentDirectory,"ble_app_uart_c","Keil_6","Objects","YP001_GR5526.hex");
  if(File.Exists(app)){byte[] actual=PackCore.ReadGr(app);Check(actual.Length+PackCore.SignatureBytes<=PackCore.GrSlot);}
  byte[] gr=new byte[64];Array.Copy(BitConverter.GetBytes(0x20040000u),0,gr,0,4);Array.Copy(BitConverter.GetBytes(0x00202009u),0,gr,4,4);
  string g=Path.Combine(root,"gr.bin"),c=Path.Combine(root,"cat.bin");File.WriteAllBytes(g,gr);File.WriteAllBytes(c,new byte[]{1,2,3});
  // SAM | 2026-10-22 11:23 +08:00 | A renamed random BIN must not enter the CAT1 OTA archive.
  Reject(()=>PackCore.Package(g,c,root,"1.0","1.3","客户","测试",495616));
  string fake=Path.Combine(root,"fake.sota");File.WriteAllBytes(fake,new byte[200]);Reject(()=>PackCore.Package(g,fake,root,"1.0","1.3","客户","测试",495616));
  string denied=Path.Combine(root,"nvds.hex");File.WriteAllText(denied,":02000004002FCB\n:02E0000001021B\n:00000001FF\n");RejectMessage(()=>PackCore.ReadGr(denied),"越界");
  var entries=new System.Collections.Generic.SortedDictionary<string,byte[]>(StringComparer.Ordinal);entries.Add("main.lua",System.Text.Encoding.UTF8.GetBytes("PROJECT='TEST'\nVERSION='001.000.000'\n"));
  byte[] db=Cat1Native.LuaDb(entries);Check(Cat1Native.ReadLuaDb(db).Count==1);db[30]^=1;Reject(()=>Cat1Native.ReadLuaDb(db));
  Check(Cat1Native.Identity("-- VERSION='999.999.999'\nPROJECT='TEST'\nVERSION='001.000.000'\n")[1]=="001.000.000");
  Reject(()=>Cat1Native.Identity("PROJECT='TEST'\nVERSION='1.0'"));
  // SAM | 2026-10-22 +08:00 | Version gating must use the embedded identity, not an operator's target label.
  byte[] controlled=System.Text.Encoding.ASCII.GetBytes("YP001_FW|GR5526|001.000.001|2|END");
  Check(FirmwareIdentity.MatchTarget(controlled,"001.000.001","1.0.1").Build==2);
  Reject(()=>FirmwareIdentity.MatchTarget(controlled,"001.000.000","1.0.1"));Reject(()=>FirmwareIdentity.MatchTarget(controlled,"001.000.001","1.4"));
  Reject(()=>FirmwareIdentity.ReadGr(new byte[128]));Reject(()=>FirmwareIdentity.ReadGr(System.Text.Encoding.ASCII.GetBytes("YP001_FW|GR5526|001.000.001|65536|END")));
  // SAM | 2026-10-22 +08:00 | Verify the operator power sequence without writing to a real serial port.
  string space="OTA_SPACE={\"ok\":true,\"total_bytes\":524288,\"free_bytes\":495616}";int calls=0;
  Check(DeviceSpace.Query((cmd,wait)=>{calls++;Check(cmd=="cat_at OTA_SPACE");return space;},msg=>{})==space);Check(calls==1);
  calls=0;int on=0;
  Check(DeviceSpace.Query((cmd,wait)=>{calls++;if(cmd=="cat1_power on"){on++;return "[CAT1 POWER] rail_request=on code=0x0000; USB may supply VBAT; no AT sent\r\n";}Check(cmd=="cat_at OTA_SPACE");return calls>=4?space:"";},msg=>{})==space);Check(on==1&&calls==4);
  calls=0;Reject(()=>DeviceSpace.Query((cmd,wait)=>{calls++;return cmd=="cat1_power on"?"[OTA] power change denied: installation pending or journal unknown":"";},msg=>{}));Check(calls==2);
  on=0;calls=0;Reject(()=>DeviceSpace.Query((cmd,wait)=>{calls++;if(cmd=="cat1_power on"){on++;return "[CAT1 POWER] rail_request=on code=0x0000; no AT sent\r\n";}Check(cmd=="cat_at OTA_SPACE");return "";},msg=>{}));Check(on==1&&calls==12);
  int keys=0;calls=0;Check(DeviceSpace.Query((cmd,wait)=>{calls++;if(cmd=="cat1_power on")return "[CAT1 POWER] rail_request=on code=0x0000\r\n";if(cmd=="cat1_power key"){keys++;return "[CAT1 POWER] manual_key code=0x0000; no AT sent\r\n";}Check(cmd=="cat_at OTA_SPACE");return keys==1?space:"";},msg=>{},true)==space);Check(keys==1&&calls==6);
  keys=0;Check(DeviceSpace.Query((cmd,wait)=>{Check(cmd=="cat_at OTA_SPACE");return space;},msg=>{},true)==space);Check(keys==0);
  // SAM | 2026-10-22 +08:00 | Single-button flow never presses a key after the operator declines or before a successful rail acknowledgment.
  int prompts=0;keys=0;
  Reject(()=>DeviceSpace.Query((cmd,wait)=>{if(cmd=="cat1_power on")return "[CAT1 POWER] rail_request=on code=0x0000\r\n";if(cmd=="cat1_power key")keys++;return "";},msg=>{},false,()=>{prompts++;return false;}));Check(prompts==1&&keys==0);
  prompts=0;keys=0;
  Check(DeviceSpace.Query((cmd,wait)=>{if(cmd=="cat1_power on")return "[CAT1 POWER] rail_request=on code=0x0000\r\n";if(cmd=="cat1_power key"){keys++;return "[CAT1 POWER] manual_key code=0x0000\r\n";}return keys>0?space:"";},msg=>{},false,()=>{prompts++;return true;})==space);Check(prompts==1&&keys==1);
  prompts=0;Check(DeviceSpace.Query((cmd,wait)=>space,msg=>{},false,()=>{prompts++;return true;})==space);Check(prompts==0);
  gr[4]=0;gr[5]=0;gr[6]=0;gr[7]=0;File.WriteAllBytes(g,gr);Reject(()=>PackCore.ReadGr(g));
  File.WriteAllBytes(c,new byte[479233]);Reject(()=>PackCore.Package(g,c,root,"1.0","1.3","客户","",495616));
  Console.WriteLine("PASS portable capacity/version/archive checks: "+count);
 }
}}
