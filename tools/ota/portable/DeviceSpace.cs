// SAM | 2026-10-22 +08:00 | Wake the CAT1 rail through the existing guarded GR command before retrying space queries.
using System;using System.Text;using System.Text.RegularExpressions;
namespace YpOta {
public static class DeviceSpace {
 // SAM | 2026-10-22 +08:00 | A single UI action may request one key confirmation when the legacy firmware exposes no measured run state.
 public static string Query(Func<string,int,string> exchange,Action<string> progress,bool coldStart=false,Func<bool> confirmKey=null){
  string response=exchange("cat_at OTA_SPACE",2000);
  if(HasSpace(response))return response;
  progress("CAT1未回复，正在请求GR5526打开CAT1电源…");
  string ack=exchange("cat1_power on",1800);
  if(!Regex.IsMatch(ack,@"\[CAT1 POWER\] rail_request=on code=0x0000\b"))
   throw new Exception("未确认CAT1电源开启成功。请确认GR诊断串口、固件命令及OTA电源互锁状态；未触发PWRKEY。");
  progress("CAT1电源轨已请求开启，正在等待模块启动并读取空间（最长约40秒）…");
  // SAM | 2026-10-22 +08:00 | Only an explicit cold-start button permits one key pulse, never a retry loop.
  if(coldStart||confirmKey!=null){
   for(int i=0;i<2;i++){response=exchange("cat_at OTA_SPACE",4000);if(HasSpace(response))return response;}
   if(!coldStart&&!confirmKey())throw new Exception("已保留CAT1当前电源状态，未触发启动键。空间尚未读取，请检查模块运行与串口通信。");
   progress("正在执行一次CAT1启动键操作，随后等待空间回包…");
   ack=exchange("cat1_power key",3000);
   if(!Regex.IsMatch(ack,@"\[CAT1 POWER\] manual_key code=0x0000\b"))throw new Exception("未确认启动键执行成功，已停止；不会再次触发。");
  }
  for(int i=0;i<10;i++){response=exchange("cat_at OTA_SPACE",4000);if(HasSpace(response))return response;}
  throw new Exception("GR已确认CAT1电源开启，但40秒内未收到空间回包。模块可能仍需一次PWRKEY启动，或UART/当前固件不支持OTA_SPACE；未自动反复触发电源键。");
 }
 static bool HasSpace(string response){return Regex.IsMatch(response??"",@"OTA_SPACE=(\{[^\r\n]*\})");}
}
}
