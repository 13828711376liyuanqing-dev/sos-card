// SAM | 2026-10-22 11:35 +08:00 | End-to-end host verification using the real vendor tools and current source.
using System;using System.IO;using System.IO.Compression;using System.Security.Cryptography;
namespace YpOta {class NativeTests {
 static int count;static void Check(bool b,string message){count++;if(!b)throw new Exception(message);}
 static void Reject(Action action,string label){bool rejected=false;try{action();}catch{rejected=true;}Check(rejected,"Accepted invalid input: "+label);}
 static uint Crc(byte[] b){uint c=0xffffffff;for(int i=8;i<92;i++){c^=b[i];for(int j=0;j<8;j++)c=(c>>1)^((c&1)!=0?0xedb88320u:0);}return c;}
 static void Repair(byte[] b){using(MD5 m=MD5.Create())Array.Copy(m.ComputeHash(b,92,b.Length-92),0,b,60,16);Array.Copy(BitConverter.GetBytes(Crc(b)),0,b,4,4);}
 static int Main(string[] args){try{Run(args);return 0;}catch(Exception e){Console.Error.WriteLine("FAIL native: "+e.Message);return 1;}}
 static void Run(string[] args){
  string source=args[0],tools=args[1],output=args[2];string before=Cat1Native.FileHash(Path.Combine(source,"main.lua"));
  Cat1Image result=Cat1Native.Build(source,tools,output);Console.WriteLine("GENERATED "+result.File);
  Check(before==Cat1Native.FileHash(Path.Combine(source,"main.lua")),"Source main changed");Check(result.Version==Cat1Native.Identity(File.ReadAllText(Path.Combine(source,"main.lua")))[1],"Source version changed");
  Cat1Image verified=Cat1Native.Inspect(result.File,tools,Path.Combine(output,"verify_"+Guid.NewGuid().ToString("N")));Check(verified.Hash==result.Hash,"Readback differs");
  // SAM | 2026-10-23 +08:00 | Only the just-generated image is a test input; an unrelated Luatools USB cache may contain padding or a different project's files.
  // Build and Inspect above independently decode and verify the current LuaDB, including its exact end and main.luac.
  byte[] good=File.ReadAllBytes(result.File),bad=(byte[])good.Clone();bad[95]^=1;Reject(()=>Cat1Native.CheckContainer(bad),"payload corruption");
  bad=(byte[])good.Clone();Array.Copy(BitConverter.GetBytes(0x754000u),0,bad,124,4);Repair(bad);Reject(()=>Cat1Native.CheckContainer(bad),"user FS address even with repaired checksums");
  bad=(byte[])good.Clone();Array.Copy(BitConverter.GetBytes(524289u),0,bad,100,4);Repair(bad);Reject(()=>Cat1Native.CheckContainer(bad),"decompressed script oversized");
  bad=(byte[])good.Clone();bad[8]=1;Repair(bad);Reject(()=>Cat1Native.CheckContainer(bad),"core/full OTA flag");
  bad=new byte[good.Length-1];Array.Copy(good,bad,bad.Length);Reject(()=>Cat1Native.CheckContainer(bad),"truncated SOTA");
  bad=(byte[])good.Clone();bad[150]^=0xff;Repair(bad);Reject(()=>Cat1Native.Decode(bad,tools,Path.Combine(output,"corrupt_"+Guid.NewGuid().ToString("N"))),"corrupt LZMA with repaired outer checksum");
  var files=new System.Collections.Generic.SortedDictionary<string,byte[]>();files.Add("main.lua",new byte[524288]);Reject(()=>Cat1Native.LuaDb(files),"LuaDB beyond script slot");
  string originalRecord=File.ReadAllText(result.File+".json");File.WriteAllText(result.File+".json",originalRecord.Replace(result.Version,"999.999.999"));
  try{Reject(()=>Cat1Native.Inspect(result.File,tools,Path.Combine(output,"wrong_version_"+Guid.NewGuid().ToString("N"))),"metadata version does not match bytecode");}finally{File.WriteAllText(result.File+".json",originalRecord,new System.Text.UTF8Encoding(false));}
  string app=Path.Combine(Environment.CurrentDirectory,"ble_app_uart_c","Keil_6","Objects","YP001_GR5526.hex");
  string keys=args.Length>3?args[3]:Path.Combine(output,"test_keys");BundleSigning.Initialize(keys);
  string actualTarget=FirmwareIdentity.Normalize(result.Version);
  string package=PackCore.Package(app,result.File,output,"0.0.0",actualTarget,"HOST_SIGNED_CHECK","",495616,tools,keys,Path.Combine(Environment.CurrentDirectory,"OTA_Packager","contracts"));
  using(ZipArchive z=ZipFile.OpenRead(package)){Check(z.Entries.Count==6,"Archive entries");Check(z.GetEntry("CAT1/payload.sota").Length==good.Length,"Archive native payload");Check(z.GetEntry("signature.json")!=null&&z.GetEntry(BundleSigning.PrivateName)==null,"Signature/private key boundary");}
  Check(BundleSigning.VerifyArchive(package,Path.Combine(keys,BundleSigning.PublicName)).Length==64,"Full signed bundle verification");
  Console.WriteLine("HOST_ARCHIVE "+package);Console.WriteLine("PASS native generation/decompression/partition/corruption/archive checks: "+count);
 }
}}
