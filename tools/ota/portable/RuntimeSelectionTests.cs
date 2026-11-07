// SAM | 2026-10-24 +08:00 | Capacity fix may omit only an unreferenced legacy installer and must retain source compatibility.
using System;
using System.Collections.Generic;
namespace YpOta { class RuntimeSelectionTests {
 static int Main(){try{
  var s=new Dictionary<string,string>{{"main.lua","require 'update'"},{"update.lua","require 'ota_runtime'"},{"ota_runtime.lua","return {}"},{"libfota2.lua","return {}"}};
  if(!Cat1Native.OmitLegacyFota(s))throw new Exception("unused legacy installer retained");
  s["main.lua"]="require 'libfota2'";if(Cat1Native.OmitLegacyFota(s))throw new Exception("active installer omitted");
  s["main.lua"]="local name='libfota2'; require(name)";if(Cat1Native.OmitLegacyFota(s))throw new Exception("dynamic named reference omitted");
  s["main.lua"]="-- require 'libfota2'\nrequire 'update'";if(!Cat1Native.OmitLegacyFota(s))throw new Exception("comment treated as live reference");
  s.Remove("ota_runtime.lua");if(Cat1Native.OmitLegacyFota(s))throw new Exception("uncontrolled project changed");
  Console.WriteLine("PASS runtime selection: unused installer only, static/dynamic named references and legacy projects retained");return 0;
 }catch(Exception e){Console.Error.WriteLine(e.Message);return 1;}}
}}
