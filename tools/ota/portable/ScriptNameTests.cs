// SAM | 2026-10-24 +08:00 | Reproduce Luatools USB filename boundary before packaging firmware.
using System;
using System.Collections.Generic;
namespace YpOta { class ScriptNameTests {
 static int Main(){try{
  var files=new SortedDictionary<string,byte[]>();files.Add("main.lua",new byte[]{1});
  files.Add(new string('a',18)+".luac",new byte[]{2});
  Cat1Native.ReadLuaDb(Cat1Native.LuaDb(files));
  files.Remove(new string('a',18)+".luac");files.Add("ota_candidate_files.luac",new byte[]{2});
  bool rejected=false;try{Cat1Native.LuaDb(files);}catch{rejected=true;}
  if(!rejected)throw new Exception("24-byte filename accepted although Luatools permits at most 23 bytes");
  Console.WriteLine("PASS script filename: 23 bytes accepted; 24 bytes rejected");return 0;
 }catch(Exception e){Console.Error.WriteLine(e.Message);return 1;}}
}}
