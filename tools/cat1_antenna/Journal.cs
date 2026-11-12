// SAM | 2026-10-10 16:53 +08:00 | Stream and flush local evidence; propagate IO errors instead of losing data silently.
using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
namespace Antenna {
 public sealed class Journal:IDisposable {
  StreamWriter raw,csv;
  public Journal(string folder){Directory.CreateDirectory(folder);try{raw=new StreamWriter(Path.Combine(folder,"raw.log"),false,new UTF8Encoding(true));raw.AutoFlush=true;csv=new StreamWriter(Path.Combine(folder,"samples.csv"),false,new UTF8Encoding(true));csv.AutoFlush=true;csv.WriteLine("timestamp,antenna,type,seq,csq,reg,rsrp,rsrq,snr,rssi,cell,tac,fix,sats_view,sats_used,cn0_max,lat,lon,hdop,elapsed_ms,ttff_ms,snr_max,raw_frame");}catch{Dispose();throw;}}
  public void Raw(string direction,string text){raw.WriteLine(DateTimeOffset.Now.ToString("o")+" "+direction+" "+text);}
  public void Sample(Frame f,string antenna){string[] keys={"type","seq","csq","reg","rsrp","rsrq","snr","rssi","cell","tac","fix","sats_view","sats_used","cn0_max","lat","lon","hdop","elapsed_ms","ttff_ms","snr_max"};var row=new List<string>();row.Add(Csv.Escape(DateTimeOffset.Now.ToString("o")));row.Add(Csv.Escape(antenna));foreach(string k in keys)row.Add(Csv.Escape(f.Get(k)));row.Add(Csv.Escape(f.Raw));csv.WriteLine(String.Join(",",row));}
  public void Dispose(){try{if(raw!=null)raw.Dispose();}finally{if(csv!=null)csv.Dispose();raw=null;csv=null;}}
 }
}


