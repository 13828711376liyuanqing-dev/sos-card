// SAM | 2026-10-24 +08:00 | Check the exact baseline USB import payload with the vendor-compiled text main, without downloading or accepting a Luatools merge.
using System;using System.IO;using YpOta;
class TrialUsbCheck {
 static int Main(string[] a){try{
  if(a.Length!=4)throw new Exception("Expected native script.bin, compiled text main, USB directory, new expected output");
  var files=Cat1Native.ReadLuaDb(File.ReadAllBytes(a[0]));files["main.luac"]=File.ReadAllBytes(a[1]);
  if(Directory.GetFiles(a[2]).Length!=files.Count)throw new Exception("USB file count mismatch");
  foreach(var p in files)if(p.Key!="main.luac"&&Cat1Native.FileHash(Path.Combine(a[2],p.Key))!=PackCore.Hash(p.Value))throw new Exception("USB bytecode mismatch: "+p.Key);
  byte[] b=Cat1Native.LuaDb(files);Cat1Native.ReadLuaDb(b);
  using(var f=new FileStream(a[3],FileMode.CreateNew,FileAccess.Write))f.Write(b,0,b.Length);
  Console.WriteLine(PackCore.Json.Serialize(new{expected_script_bytes=b.Length,limit=Cat1Native.ScriptCapacity,spare=Cat1Native.ScriptCapacity-b.Length,usb_files=files.Count,non_main_matches=true,luatools_actual_merge_verified=false}));return 0;
 }catch(Exception e){Console.Error.WriteLine(e.Message);return 1;}}
}
