// SAM | 2026-10-13 15:00 +08:00 | Bounded FT1 replies, command correlation
// and durable local evidence; a disconnected radio is not a current reading.
using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
using System.Globalization;
namespace FactoryFinal {
 public class Frame {
  public string Raw,Op;public uint Seq;public bool Ok;
  public readonly Dictionary<string,string> Values=new Dictionary<string,string>();
  public string Get(string key){string v;return Values.TryGetValue(key,out v)?v:"NA";}
  public uint Number(string key,uint fallback){uint v;return UInt32.TryParse(Get(key),NumberStyles.None,CultureInfo.InvariantCulture,out v)?v:fallback;}
  public static bool ValidOp(string op){return op=="INFO"||op=="UNLOCK"||op=="PAGE"||op=="CAT_OFF"||op=="SHIP_PREP"||op=="SHIP_STATUS"||op=="SHIP_CONFIRM"||op=="SHIP_CANCEL";}
  public static Frame Parse(string line){
   if(line==null||line.Length>512||!line.StartsWith("FT ",StringComparison.Ordinal))return null;
   var f=new Frame();f.Raw=line;
   foreach(string part in line.Substring(3).Split(' ')){
    if(part.Length==0)continue;int i=part.IndexOf('=');
    if(i<1||i==part.Length-1)return null;string key=part.Substring(0,i);
    if(f.Values.ContainsKey(key))return null;f.Values.Add(key,part.Substring(i+1));
   }
   uint seq;if(f.Get("v")!="1"||!UInt32.TryParse(f.Get("seq"),NumberStyles.None,CultureInfo.InvariantCulture,out seq)||seq==0||!ValidOp(f.Get("op"))||(f.Get("ok")!="0"&&f.Get("ok")!="1"))return null;
   f.Seq=seq;f.Op=f.Get("op");f.Ok=f.Get("ok")=="1";return f;
  }
 }
 public class LineParser {
  readonly StringBuilder line=new StringBuilder();bool dropping;
  public List<Frame> Feed(string data){var frames=new List<Frame>();foreach(char c in data){
   if(c=='\n'){if(!dropping){var f=Frame.Parse(line.ToString().TrimEnd('\r'));if(f!=null)frames.Add(f);}line.Length=0;dropping=false;}
   else if(!dropping){if(line.Length>=512){line.Length=0;dropping=true;}else line.Append(c);}
  }return frames;}
  public void Reset(){line.Length=0;dropping=false;}
 }
 public class Session {
  uint sequence;public string Pending;public uint PendingSeq;public bool Uncertain;
  public DateTime Deadline;
  public string Start(string op,string arg,DateTime now){
   if(Uncertain)throw new InvalidOperationException("上次操作结果不确定，请重新连接后读取状态。");
   if(Pending!=null)throw new InvalidOperationException("已有命令等待设备回执。");
   if(!Frame.ValidOp(op))throw new ArgumentException("Unknown operation");
   Pending=op;PendingSeq=++sequence;if(PendingSeq==0)PendingSeq=++sequence;
   Deadline=now.AddSeconds(8);
   return "FT "+op+" "+PendingSeq.ToString(CultureInfo.InvariantCulture)+(arg==null?"":" "+arg);
  }
  public Frame Accept(Frame f){if(f==null||f.Op!=Pending||f.Seq!=PendingSeq)return null;Pending=null;return f;}
  public void Abort(){Pending=null;Uncertain=true;}
  public void Reconnect(){Pending=null;Uncertain=false;}
  public static bool IdentityMatches(string label,string actual){
   if(label==null||actual==null||label.Length!=15||actual.Length!=15)return false;
   for(int i=0;i<15;i++)if(label[i]<'0'||label[i]>'9'||actual[i]!=label[i])return false;return true;
  }
 }
 public static class Csv {
  public static string Cell(string value){value=value??"";if(value.Length>0&&"=+-@".IndexOf(value[0])>=0)value="'"+value;return "\""+value.Replace("\"","\"\"")+"\"";}
 }
 public class Journal:IDisposable {
  readonly string folder;StreamWriter raw;
  public Journal(string path){folder=path;Directory.CreateDirectory(folder);raw=new StreamWriter(Path.Combine(folder,"raw.log"),false,new UTF8Encoding(true));raw.AutoFlush=true;}
  public static string Stamp(){return DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8)).ToString("o");}
  public void Raw(string direction,string data){if(raw==null)throw new ObjectDisposedException("Journal");raw.WriteLine(Stamp()+" "+direction+" "+data);}
  public void Save(string label,string actual,string address,string op,string batch,string[] names,string[] results,string outcome){
   using(var report=new StreamWriter(Path.Combine(folder,"report.csv"),false,new UTF8Encoding(true))){
    report.WriteLine("time,operator,batch,label_imei,device_imei,ble_address,item,result,summary");
    for(int i=0;i<names.Length;i++)report.WriteLine(String.Join(",",new[]{Csv.Cell(Stamp()),Csv.Cell(op),Csv.Cell(batch),Csv.Cell(label),Csv.Cell(actual),Csv.Cell(address),Csv.Cell(names[i]),Csv.Cell(results[i]),Csv.Cell(outcome)}));
   }
   Raw("REPORT",outcome);
  }
  public void Dispose(){if(raw!=null){raw.Dispose();raw=null;}}
 }
}
