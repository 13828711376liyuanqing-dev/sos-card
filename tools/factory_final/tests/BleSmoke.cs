// SAM | 2026-10-13 15:28 +08:00 | Bounded live BLE scan/INFO test;
// deliberately excludes physical unlock and all product-changing commands.
using System;
using System.IO;
using System.Threading.Tasks;
using System.Collections.Generic;
namespace FactoryFinal {
 class Smoke {
  static int Main(string[] args){try{return Run(args).GetAwaiter().GetResult();}catch(Exception e){Console.Error.WriteLine(e);return 1;}}
  static async Task<int> Run(string[] args){
   using(var link=new BleLink()){
    var devices=new Dictionary<ulong,FoundDevice>();string lost="";
    link.Discovered+=delegate(FoundDevice d){lock(devices){devices[d.Address]=d;}};
    link.Lost+=delegate(string x){lost=x;};
    link.Scan();await Task.Delay(8000);link.StopScan();
    lock(devices){foreach(var d in devices.Values)Console.WriteLine("FOUND "+d.ToString());}
    if(lost.Length>0){Console.WriteLine("SCAN_ERROR "+lost);return 2;}
    if(args.Length==0){Console.WriteLine("SCAN_ONLY count="+devices.Count);return 0;}
    ulong address=UInt64.Parse(args[0],System.Globalization.NumberStyles.HexNumber);
    lock(devices){if(!devices.ContainsKey(address)){Console.WriteLine("TARGET_NOT_SEEN "+args[0]);return 3;}}
    var parser=new LineParser();var result=new TaskCompletionSource<Frame>();
    link.Received+=delegate(string data){Console.Write(data);lock(parser){foreach(var f in parser.Feed(data))if(f.Op=="INFO"&&f.Seq==1)result.TrySetResult(f);}};
    FoundDevice selected;lock(devices){selected=devices[address];}
    await link.Connect(address,selected.AddressType);Console.WriteLine("GATT_CONNECTED "+args[0]);
    await link.Send("FT INFO 1");
    if(await Task.WhenAny(result.Task,Task.Delay(8000))!=result.Task){Console.WriteLine("INFO_TIMEOUT");return 4;}
    Frame info=await result.Task;if(!info.Ok)return 5;
    Console.WriteLine("LIVE_INFO_OK "+info.Raw);return 0;
   }
  }
 }
}
