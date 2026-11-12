// SAM | 2026-10-13 15:00 +08:00 | Factory host checks for stale/invalid
// replies and report integrity before the user-facing operator workflow.
using System;
using System.IO;
namespace FactoryFinal {
 class Tests {
  static void Check(bool x,string message){if(!x)throw new Exception(message);}
  static int Main(){try{
   Check(Frame.Parse("FT v=1 seq=1 op=INFO ok=1 imei=NA").Seq==1,"valid reply");
   Check(Frame.Parse("FT v=1 seq=1 seq=2 op=INFO ok=1")==null,"duplicate key");
   Check(Frame.Parse("FT v=2 seq=1 op=INFO ok=1")==null,"unsupported version");
   Check(Frame.Parse("FT v=1 seq=-1 op=INFO ok=1")==null,"negative sequence");
   Check(Frame.Parse("FT v=1 seq=4294967296 op=INFO ok=1")==null,"overflow");
   Check(Frame.Parse("FT v=1 seq=1 op=ERASE ok=1")==null,"unsupported op");
   Check(Frame.Parse("FT v=1 seq=1 op=INFO ok=2")==null,"unknown boolean");
   var p=new LineParser();Check(p.Feed("FT v=1 seq=3 op=").Count==0,"fragment");
   Check(p.Feed("INFO ok=1\n").Count==1,"completed fragment");
   Check(p.Feed(new string('x',600)+"\nFT v=1 seq=4 op=INFO ok=1\n").Count==1,"overflow recovers");
   var s=new Session();string cmd=s.Start("INFO",null,DateTime.UtcNow);
   Check(cmd=="FT INFO 1","request");
   Check(s.Accept(Frame.Parse("FT v=1 seq=2 op=INFO ok=1"))==null,"stale seq");
   Check(s.Accept(Frame.Parse("FT v=1 seq=1 op=PAGE ok=1"))==null,"wrong op");
   Check(s.Accept(Frame.Parse("FT v=1 seq=1 op=INFO ok=1"))!=null,"matched reply");
   Check(!Session.IdentityMatches("123456789012345","NA"),"unknown identity not match");
   Check(!Session.IdentityMatches("123456789012345","123456789012346"),"identity mismatch");
   Check(Session.IdentityMatches("123456789012345","123456789012345"),"identity match");
   Check(Csv.Cell("=cmd").Contains("'=cmd"),"spreadsheet formula guard");
   string folder=Path.Combine(Path.GetTempPath(),"ft_test_"+Guid.NewGuid().ToString("N"));
   try{using(var j=new Journal(folder)){j.Raw("RX","FT test");j.Save("123456789012345","NA","EA:CB","SAM","batch",new[]{"屏幕"},new[]{"未测试"},"未完成");}
    Check(File.ReadAllText(Path.Combine(folder,"report.csv")).Contains("未完成"),"unknown report retained");
    Check(File.ReadAllText(Path.Combine(folder,"raw.log")).Contains("FT test"),"raw log retained");
   }finally{File.Delete(Path.Combine(folder,"raw.log"));File.Delete(Path.Combine(folder,"report.csv"));if(Directory.Exists(folder))Directory.Delete(folder);}
   Console.WriteLine("PASS: factory reply validation, fragmentation, correlation, identity and report integrity");return 0;
  }catch(Exception e){Console.Error.WriteLine(e);return 1;}}
 }
}
