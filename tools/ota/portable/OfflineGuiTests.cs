// SAM | 2026-10-24 +08:00 | Verify offline opt-in and strict-space validation without serial, firmware generation or package duplication.
using System;using System.Reflection;using System.Windows.Forms;
namespace YpOta {class OfflineGuiTests {
 static void Need(bool ok,string why){if(!ok)throw new Exception(why);}
 static object Field(MainForm f,string name){return typeof(MainForm).GetField(name,BindingFlags.NonPublic|BindingFlags.Instance).GetValue(f);}
 static object Read(MainForm f){return typeof(MainForm).GetMethod("ReadPackagingSpace",BindingFlags.NonPublic|BindingFlags.Instance).Invoke(f,null);}
 static void Reject(MainForm f){try{Read(f);}catch(TargetInvocationException e){Need(e.InnerException is Exception,"No validation error");return;}throw new Exception("Strict mode accepted missing space");}
 [STAThread] static int Main(){try{using(var f=new MainForm()){
  var info=typeof(MainForm).GetField("offline",BindingFlags.NonPublic|BindingFlags.Instance);Need(info!=null,"Missing offline checkbox");
  var mode=(CheckBox)info.GetValue(f);var free=(TextBox)Field(f,"free");
  Need(!mode.Checked&&free.Enabled,"Strict mode must remain default");free.Text="";Reject(f);
  free.Text="450000";Need((int)Read(f)==450000,"Strict space lost");
  mode.Checked=true;Need(!free.Enabled&&Read(f)==null,"Offline fabricated a space reading");
  free.Text="not a reading";Need(Read(f)==null,"Offline requires serial reading");
  mode.Checked=false;Need(free.Enabled,"Strict field not restored");Reject(f);
  free.Text="0";Reject(f);free.Text="524289";Reject(f);
  Need(mode.Text.Contains("离线")&&mode.Text.Contains("安装"),"Offline boundary unclear");
  f.Show();Application.DoEvents();Need(((Button)Field(f,"pack")).Height<=40&&((TextBox)Field(f,"log")).Height>=100,"Pack button obscures log");
 }Console.WriteLine("PASS GUI strict default, offline opt-in, unknown space, mode restoration and visible log");return 0;
 }catch(Exception e){Console.Error.WriteLine("FAIL "+e.Message);return 1;}}
}}
