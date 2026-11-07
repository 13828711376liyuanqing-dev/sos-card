// SAM | 2026-10-23 +08:00 | Reject signed-build identity metadata that does not describe the actual decompressed SOTA.
using System;using System.IO;using System.Collections.Generic;
namespace YpOta {class IdentityRecordTests {
 static int Main(string[] args){try{
  string dir=args[2];Directory.CreateDirectory(dir);string copy=Path.Combine(dir,"candidate.sota");
  File.Copy(args[0],copy,true);string original=File.ReadAllText(args[0]+".json");
  File.WriteAllText(copy+".json",original);Cat1Native.Inspect(copy,args[1],Path.Combine(dir,"valid"));
  foreach(string mode in new[]{"hash","missing","extra","count","absent"}){
   var record=PackCore.Json.Deserialize<Dictionary<string,object>>(original);
   var hashes=(Dictionary<string,object>)record["compiled_sha256"];
   if(mode=="hash")hashes["main.luac"]=new string('0',64);
   if(mode=="missing")hashes.Remove("main.luac");
   if(mode=="extra")hashes["../extra.luac"]=new string('0',64);
   if(mode=="count")record["file_count"]=0;
   if(mode=="absent")record.Remove("compiled_sha256");
   File.WriteAllText(copy+".json",PackCore.Json.Serialize(record));bool rejected=false;
   try{Cat1Native.Inspect(copy,args[1],Path.Combine(dir,mode));}catch(Exception){rejected=true;}
   if(!rejected)throw new Exception("Accepted inconsistent identity: "+mode);
  }
  File.WriteAllText(copy+".json",original);Console.WriteLine("PASS actual SOTA identity: valid plus 5 inconsistent records rejected");return 0;
 }catch(Exception e){Console.Error.WriteLine(e.Message);return 1;}}
}}
