// SAM | 2026-10-22 +08:00 | Developer release pipeline uses the same version/capacity/signing core as the operator GUI; no flashing.
using System;using System.IO;
namespace YpOta {class ReleaseCli {
 static int Main(string[] a){try{
  if(a.Length==4&&a[0]=="cat1"){
   Cat1Image r=Cat1Native.Build(a[1],a[2],a[3]);Console.WriteLine(PackCore.Json.Serialize(new{file=r.File,version=r.Version,sha256=r.Hash,bytes=r.PackageBytes,script_bytes=r.ScriptBytes}));return 0;
  }
  if(a.Length==2&&a[0]=="gr"){
   byte[] b=PackCore.ReadGr(a[1]);GrIdentity r=FirmwareIdentity.ReadGr(b);Console.WriteLine(PackCore.Json.Serialize(new{version=r.Version,build=r.Build,bytes=b.Length,sha256=PackCore.Hash(b)}));return 0;
  }
  // SAM | 2026-10-24 +08:00 | Explicit first-test command preserves frozen GR bytes and does not impersonate production acceptance.
  // SAM | 2026-10-29 07:07 +08:00 | Optional 10th argument selects a whitelisted first-trial target; omitted keeps the original 1.5.0 scope.
  // SAM | 2026-10-29 22:02 +08:00 | Optional 11th argument: whitelisted source version (default 1.0.2).
  if((a.Length>=9&&a.Length<=11)&&a[0]=="pack-trial"){
   Console.WriteLine(PackCore.PackageForFirstTrial(a[1],a[2],a[3],int.Parse(a[4]),a[5],a[6],a[7],a[8],a.Length>=10?a[9]:"1.5.0",a.Length==11?a[10]:"1.0.2"));return 0;
  }
  if(a.Length==4&&a[0]=="usb-scripts"){
   var files=Cat1Native.ReadLuaDb(File.ReadAllBytes(a[1]));string main=File.ReadAllText(a[2]);string version=Cat1Native.Identity(main)[1];
   if(!System.Text.Encoding.ASCII.GetString(files["main.luac"]).Contains(version))throw new Exception("Plain main.lua does not match the compiled LuaDB version");
   // SAM | 2026-10-24 +08:00 | Reject historical overlong entries before creating any USB import files.
   foreach(var item in files)if(System.Text.Encoding.UTF8.GetByteCount(item.Key)>23)throw new Exception("Luatools USB filename exceeds 23 bytes: "+item.Key);
   // SAM | 2026-10-23 +08:00 | Luatools v3.4.14 scans text main for dependencies and cannot discover imports inside bytecode. Declare every module in a non-executing branch.
   var anchor=new System.Text.StringBuilder("-- SAM | 2026-10-23 +08:00 | Packaging dependency inventory only; never execute or initialize modules here.\r\nif false then\r\n");
   // SAM | 2026-10-24 +08:00 | Keep every binary dependency discoverable without duplicating literal imports already visible in text main; recover USB merge headroom.
   var visible=new System.Collections.Generic.HashSet<string>(StringComparer.Ordinal);
   foreach(System.Text.RegularExpressions.Match m in System.Text.RegularExpressions.Regex.Matches(Cat1Native.WithoutComments(main),@"\brequire\s*(?:\(\s*)?[""']([A-Za-z_][A-Za-z_0-9]*)[""']"))visible.Add(m.Groups[1].Value);
   foreach(var item in files)if(item.Key.EndsWith(".luac")&&item.Key!="main.luac"){
    string module=Path.GetFileNameWithoutExtension(item.Key);if(!System.Text.RegularExpressions.Regex.IsMatch(module,@"^[A-Za-z_][A-Za-z_0-9]*$"))throw new Exception("Invalid module name");
    if(!visible.Contains(module))anchor.Append("    require(\"").Append(module).Append("\")\r\n");
   }
   anchor.Append("end\r\n").Append(main);
   Directory.CreateDirectory(a[3]);foreach(var item in files){string name=item.Key=="main.luac"?"main.lua":item.Key;byte[] bytes=item.Key=="main.luac"?System.Text.Encoding.UTF8.GetBytes(anchor.ToString()):item.Value;using(var f=new FileStream(Path.Combine(a[3],name),FileMode.CreateNew,FileAccess.Write))f.Write(bytes,0,bytes.Length);}
   File.WriteAllText(Path.Combine(Path.GetDirectoryName(Path.GetFullPath(a[3])),"USB_IMPORT_REQUIREMENTS.txt"),"Import ALL files from "+Path.GetFullPath(a[3])+"\r\nText main declares ALL bytecode modules. Keep FS/KV.\r\nVerify final generated LuaDB contains every module before download.\r\n");
   Console.WriteLine("USB_SCRIPT_FILES="+files.Count);return 0;
  }
  if(a.Length==9&&a[0]=="pack"){
   Console.WriteLine(PackCore.Package(a[1],a[2],a[3],a[4],a[5],"YP001","LOCAL_TEST",int.Parse(a[8]),a[6],a[7]));return 0;
  }
  // SAM | 2026-10-24 +08:00 | Explicit evidence-bound installation test package;
  // legacy GUI/offline paths retain their non-installable default.
  if(a.Length==10&&a[0]=="pack-device"){
   Console.WriteLine(PackCore.PackageForDevice(a[1],a[2],a[3],a[4],a[5],"YP001","INSTALL_TEST",int.Parse(a[8]),a[9],a[6],a[7]));return 0;
  }
  // SAM | 2026-10-24 +08:00 | A distinct command creates an offline-only candidate without accepting an invented free-space number.
  if(a.Length==8&&a[0]=="pack-offline"){
   Console.WriteLine(PackCore.PackageOfflineCandidate(a[1],a[2],a[3],a[4],a[5],"YP001","LOCAL_TEST_OFFLINE",a[6],a[7]));return 0;
  }
  Console.Error.WriteLine("Usage: cat1 SOURCE LUATOOLS OUTPUT | gr HEX | pack GR CAT OUTPUT FROM TO LUATOOLS KEYS FREE | pack-offline GR CAT OUTPUT FROM TO LUATOOLS KEYS | pack-device GR CAT OUTPUT FROM TO LUATOOLS KEYS FREE ADMISSION_JSON");return 2;
 }catch(Exception e){Console.Error.WriteLine("RELEASE_FAILED: "+e.Message);return 1;}}
}}
