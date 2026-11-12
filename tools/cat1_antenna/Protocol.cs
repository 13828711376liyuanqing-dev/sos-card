// SAM | 2026-10-10 16:53 +08:00 | Bound line parsing and ACK state so host cannot claim unconfirmed sampling.
using System;
using System.Collections.Generic;
using System.Text;
namespace Antenna {
 public class Frame {
  public string Raw; public Dictionary<string,string> Values=new Dictionary<string,string>();
  public string Get(string k){string v;if(!Values.TryGetValue(k,out v))return "NA";if(k=="csq"&&v=="99")return "NA";if((k=="lat"||k=="lon")&&Get("fix")!="1")return "NA";
   if(",seq,csq,reg,rsrp,rsrq,snr,rssi,cell,tac,fix,sats_view,sats_used,cn0_max,snr_max,lat,lon,hdop,elapsed_ms,ttff_ms,".Contains(","+k+",")){
    double d;if(!Double.TryParse(v,System.Globalization.NumberStyles.Float,System.Globalization.CultureInfo.InvariantCulture,out d)||Double.IsNaN(d)||Double.IsInfinity(d))return "NA";
    if((k=="lat"&&Math.Abs(d)>90)||(k=="lon"&&Math.Abs(d)>180)||(k=="csq"&&(d<0||d>31))||(k=="fix"&&d!=0&&d!=1))return "NA";
   }return v;}
 }
 public class Protocol {
  StringBuilder buffer=new StringBuilder();bool dropping;
  public List<Frame> Feed(string data){var result=new List<Frame>();foreach(char c in data){if(c=='\n'){if(!dropping){var f=Parse(buffer.ToString().TrimEnd('\r'));if(f!=null)result.Add(f);}buffer.Length=0;dropping=false;}else if(!dropping){if(buffer.Length>=4096){buffer.Length=0;dropping=true;}else buffer.Append(c);}}return result;}
  public static Frame Parse(string line){const string prefix="[CAT1 RX] ";if(line.StartsWith(prefix))line=line.Substring(prefix.Length);if(!line.StartsWith("[ANT] "))return null;var f=new Frame();f.Raw=line;foreach(var part in line.Substring(6).Split(' ')){int i=part.IndexOf('=');if(i>0)f.Values[part.Substring(0,i)]=part.Substring(i+1);}if(f.Get("v")!="1")return null;string type=f.Get("type");return type=="ACK"||type=="LTE"||type=="GNSS"?f:null;}
 }
 // SAM | 2026-10-10 17:05 +08:00 | Use only ACK-confirmed intervals so UI edits cannot hide stale measurements.
 public class Session {
  public bool Connected;bool requireStatus;public int ConfirmedInterval {get;private set;}public string State="未连接",Pending;DateTime deadline;
  public static bool IsStale(DateTime sample,DateTime now,int interval,bool connected){return !connected||sample==DateTime.MinValue||(now-sample).TotalSeconds>Math.Max(10,interval*3);}
  public void Connect(){Connected=true;Pending=null;requireStatus=false;ConfirmedInterval=2;State="已连接 · 采样状态未知";}
  public void Disconnect(){Connected=false;Pending=null;State="已断开 · 模块可能仍在采样";}
  // SAM | 2026-10-10 20:19 +08:00 | Let STOP preempt a missing START/STATUS ACK because an operator must still be able to request sampling stop.
  public void Request(string op,DateTime now){if(!Connected)throw new InvalidOperationException("请先连接串口");if(Pending!=null&&op!="STOP")throw new InvalidOperationException("请等待当前 ACK");if(requireStatus&&op!="STATUS"&&op!="STOP")throw new InvalidOperationException("上一命令超时，请先查询状态并等待有效回执");Pending=op;deadline=now.AddSeconds(5);State="等待 "+op+" ACK";}
  public void Tick(DateTime now){if(Pending!=null&&now>=deadline){State=Pending=="STOP"?"停止未确认 · ACK 超时":"命令超时 · 模块状态未知";Pending=null;requireStatus=true;}}
  // SAM | 2026-10-10 20:19 +08:00 | A confirmed STOP resolves the old timeout; only its ACK may claim sampling stopped.
  public void Accept(Frame f){if(!Connected||f.Get("type")!="ACK"||f.Get("op")!=Pending)return;string op=Pending;Pending=null;if(f.Get("ok")!="1"){State="模块拒绝："+f.Get("error");return;}int confirmed;if((op=="START"||(op=="STATUS"&&(f.Get("running")=="0"||f.Get("running")=="1")))&&Int32.TryParse(f.Get("interval"),out confirmed)&&confirmed>=1&&confirmed<=60)ConfirmedInterval=confirmed;if((op=="STATUS"&&(f.Get("running")=="0"||f.Get("running")=="1"))||op=="STOP")requireStatus=false;State=op=="START"?"采集中":op=="STOP"?"已停止":f.Get("running")=="1"?"采集中":f.Get("running")=="0"?"已停止":"模块状态未知";}
 }
 public static class Csv { public static string Escape(string s){return "\""+(s??"").Replace("\"","\"\"")+"\"";} }
}






