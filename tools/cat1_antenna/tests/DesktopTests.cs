// SAM | 2026-10-10 16:53 +08:00 | Test protocol and connection lifetime before implementation.
using System;
using Antenna;
class Tests {
 static int n; static void Check(bool x,string s){n++;if(!x)throw new InvalidOperationException("FAIL: "+s);}
 // SAM | 2026-10-10 20:14 +08:00 | Keep double-click results visible, including failures, because the console previously closed immediately.
 static int Main(string[] args){
  bool pause=Array.IndexOf(args,"--no-pause")<0&&!Console.IsInputRedirected;
  try { Run(args); return 0; }
  catch(Exception ex){Console.Error.WriteLine(ex.Message);return 1;}
  finally { if(pause){Console.WriteLine("按任意键关闭测试窗口...");Console.ReadKey(true);} }
 }
 static void Run(string[] args){
 var p=new Protocol(); Check(p.Feed("noise\r\n[CAT1 RX] [ANT] v=1 type=LTE seq=1 csq=").Count==0,"fragment");
 var a=p.Feed("99 reg=1 mystery=foo\r\n");Check(a.Count==1,"complete");Check(a[0].Get("csq")=="NA","csq99");Check(a[0].Get("rsrp")=="NA","missing");
 Check(p.Feed("[ANT] v=2 type=LTE\r\n").Count==0,"unknown version");
 var f=p.Feed("[ANT] v=1 type=GNSS fix=0 lat=22 lon=113\r\n")[0];Check(f.Get("lat")=="NA"&&f.Get("lon")=="NA","invalid fix");
 var s=new Session(); var t=DateTime.UtcNow; s.Connect();s.Request("START",t);Check(s.State!="采集中","no optimistic start");s.Tick(t.AddSeconds(6));Check(s.State.Contains("超时"),"start timeout");
 bool blocked=false;try{s.Request("START",t);}catch(InvalidOperationException){blocked=true;}Check(blocked,"timeout requires status resync");s.Request("STATUS",t);s.Accept(p.Feed("[ANT] v=1 type=ACK op=STATUS ok=1 running=1\r\n")[0]);s.Request("STOP",t);s.Tick(t.AddSeconds(6));Check(s.State.Contains("停止未确认"),"stop timeout");
 s.Connect();s.Request("START",t);s.Accept(p.Feed("[ANT] v=1 type=ACK op=START ok=1\r\n")[0]);Check(s.State=="采集中","ACK");s.Disconnect();Check(!s.Connected&&s.Pending==null,"disconnect resets");s.Connect();s.Accept(p.Feed("[ANT] v=1 type=ACK op=START ok=1\r\n")[0]);Check(s.State!="采集中","late ack ignored");
 Check(Csv.Escape("a,\"b\n")=="\"a,\"\"b\n\"","csv escape");
 var bad=p.Feed("[ANT] v=1 type=LTE csq=bad rsrp=NaN snr=Infinity\r\n")[0];Check(bad.Get("csq")=="NA"&&bad.Get("rsrp")=="NA"&&bad.Get("snr")=="NA","invalid numeric");
 Check(p.Feed("[ANT] v=1 type=GNSS fix=1 lat=91 lon=181\r\n")[0].Get("lat")=="NA","out of bounds coordinate");
 var q=new Protocol();q.Feed("[ANT] v=1 type=LTE "+new string('x',5000));Check(q.Feed("\r\n[ANT] v=1 type=LTE csq=20\r\n").Count==1,"overflow resync");
 Check(p.Feed("[ANT] v=1 type=FUTURE x=1\r\n").Count==0,"unknown type");
 Check(Session.IsStale(t,t.AddSeconds(11),2,true),"stale frame");Check(Session.IsStale(t,t,2,false),"disconnected stale");Check(!Session.IsStale(t,t.AddSeconds(2),2,true),"fresh frame");var dir=System.IO.Path.Combine(System.IO.Path.GetTempPath(),"CAT1Antenna_HOSTTEST_"+Guid.NewGuid().ToString("N"));using(var journal=new Journal(dir)){journal.Raw("TX","hello\r\n");journal.Sample(f,"天线,\"A");}Check(System.IO.File.ReadAllText(System.IO.Path.Combine(dir,"samples.csv")).Contains("天线,\"\"A"),"logged csv label escaped");Check(System.IO.File.ReadAllText(System.IO.Path.Combine(dir,"raw.log")).Contains("TX hello"),"raw persisted");bool logFailed=false;try{using(var j=new Journal(System.IO.Path.Combine(dir,"raw.log"))){}}catch(System.IO.IOException){logFailed=true;}Check(logFailed,"unwritable log fails visibly");s.Request("STATUS",t);s.Accept(p.Feed("[ANT] v=1 type=ACK op=STATUS ok=1 running=garbage\r\n")[0]);Check(s.State=="模块状态未知","malformed status is unknown");s.Request("START",t);s.Accept(p.Feed("[ANT] v=1 type=ACK op=STOP ok=1\r\n")[0]);Check(s.Pending=="START","mismatched ACK ignored");s.Accept(p.Feed("[ANT] v=1 type=ACK op=START ok=0 error=BUSY\r\n")[0]);Check(s.State.Contains("BUSY"),"module error visible");Check(p.Feed("[ANT] v=1 type=GNSS fix=1 lat=22.123 lon=113.456 snr_max=42\r\n")[0].Get("snr_max")=="42","optional raw SNR");// SAM | 2026-10-10 17:06 +08:00 | Regression: confirmed interval and actual Lua wire fixture.
 var timing=new Session();timing.Connect();Check(timing.ConfirmedInterval==2,"safe default interval");
 timing.Request("START",t);timing.Accept(Protocol.Parse("[ANT] v=1 type=ACK op=START ok=1 interval=20"));Check(timing.ConfirmedInterval==20,"custom start ACK interval");
 timing.Request("STATUS",t);timing.Accept(Protocol.Parse("[ANT] v=1 type=ACK op=STATUS ok=1 running=1 interval=4"));Check(timing.ConfirmedInterval==4,"status interval");
 timing.Request("STATUS",t);timing.Accept(Protocol.Parse("[ANT] v=1 type=ACK op=STATUS ok=1 running=bad interval=60"));Check(timing.ConfirmedInterval==4,"invalid status cannot replace interval");
 foreach(string invalid in new string[]{"NA","0","61","2.5","bad"}){timing.Request("STATUS",t);timing.Accept(Protocol.Parse("[ANT] v=1 type=ACK op=STATUS ok=1 running=1 interval="+invalid));Check(timing.ConfirmedInterval==4,"malformed interval unchanged");}
 Check(Session.IsStale(t,t.AddSeconds(13),timing.ConfirmedInterval,true),"confirmed interval expires independently of spinner");timing.Connect();Check(timing.ConfirmedInterval==2,"reconnect resets interval");
 // SAM | 2026-10-10 20:19 +08:00 | Regress STOP after a lost ACK so the operator can transmit a stop request without falsely claiming success.
 var emergency=new Session();emergency.Connect();emergency.Request("START",t);emergency.Request("STOP",t);Check(emergency.Pending=="STOP"&&emergency.State.Contains("等待"),"stop preempts start");emergency.Accept(Protocol.Parse("[ANT] v=1 type=ACK op=START ok=1"));Check(emergency.Pending=="STOP","late start ack ignored after stop");emergency.Tick(t.AddSeconds(6));Check(emergency.State.Contains("停止未确认"),"missing stop ack remains unconfirmed");emergency.Request("STOP",t);emergency.Accept(Protocol.Parse("[ANT] v=1 type=ACK op=STOP ok=1"));Check(emergency.State=="已停止","confirmed stop clears timeout");emergency.Request("STATUS",t);emergency.Request("STOP",t);Check(emergency.Pending=="STOP","stop preempts status");
 foreach(string arg in args)if(arg!="--no-pause")Fixture(arg);
 Console.WriteLine("PASS "+n+" assertions");
 } static void Fixture(string path){
  var parser=new Protocol();var frames=new System.Collections.Generic.List<Frame>();string raw=System.IO.File.ReadAllText(path);
  for(int i=0;i<raw.Length;i+=7)frames.AddRange(parser.Feed(raw.Substring(i,Math.Min(7,raw.Length-i))));
  bool start=false,lte=false,nofix=false,fix=false,stop=false,status=false;var state=new Session();state.Connect();int previousSeq=-1;
  foreach(var frame in frames){string type=frame.Get("type"),op=frame.Get("op");
   if(type=="ACK"&&frame.Get("ok")=="1"){
    if(op=="START"){Check(!stop,"fixture START before STOP");state.Request(op,DateTime.UtcNow);state.Accept(frame);start=true;Check(state.State=="采集中","fixture START accepted");}
    else if(op=="STOP"){Check(start&&lte&&nofix&&fix,"fixture samples precede STOP");state.Request(op,DateTime.UtcNow);state.Accept(frame);stop=true;Check(state.State=="已停止","fixture STOP accepted");}
    else if(op=="STATUS"){state.Request(op,DateTime.UtcNow);state.Accept(frame);status=true;Check(state.State=="已停止"||state.State=="采集中","fixture STATUS valid");}
   }else if(type=="LTE"||type=="GNSS"){
    Check(start&&!stop,"fixture sample while running");int seq;Check(Int32.TryParse(frame.Get("seq"),out seq)&&seq>previousSeq,"fixture sequence increasing");previousSeq=seq;
    if(type=="LTE")lte=true;
    else if(frame.Get("fix")=="0"){nofix=true;Check(frame.Get("lat")=="NA"&&frame.Get("lon")=="NA","fixture nofix coordinates NA");}
    else if(frame.Get("fix")=="1"){fix=true;Check(frame.Get("lat")!="NA"&&frame.Get("lon")!="NA","fixture fix coordinates valid");}
   }
  }
  Check(start&&lte&&nofix&&fix&&stop&&status,"complete Lua fixture coverage");Console.WriteLine("Lua fixture PASS: "+path);
 }
}









