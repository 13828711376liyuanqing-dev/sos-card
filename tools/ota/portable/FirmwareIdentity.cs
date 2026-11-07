// SAM | 2026-10-22 +08:00 | Match actual compiled component identities to the product target, not just a ZIP filename.
using System;using System.Text;using System.Text.RegularExpressions;
namespace YpOta {
public sealed class GrIdentity {public string Version;public int Build;}
public static class FirmwareIdentity {
 public static string Normalize(string version){
  if(version==null||!Regex.IsMatch(version,@"^[0-9]{1,3}\.[0-9]{1,3}(\.[0-9]{1,3})?$"))throw new Exception("受控版本须为2或3段数字，每段0～999");
  string[] p=version.Split('.');return int.Parse(p[0])+"."+int.Parse(p[1])+"."+(p.Length==3?int.Parse(p[2]):0);
 }
 public static GrIdentity ReadGr(byte[] image){
  MatchCollection found=Regex.Matches(Encoding.ASCII.GetString(image),@"YP001_FW\|GR5526\|([0-9]{3}\.[0-9]{3}\.[0-9]{3})\|([0-9]{1,5})\|END");
  if(found.Count!=1)throw new Exception("GR5526固件缺少唯一受控版本标记，请先用新版工程设置版本并重新编译HEX");
  int build=int.Parse(found[0].Groups[2].Value);if(build<1||build>65535)throw new Exception("GR5526构建序号超出16位范围");
  return new GrIdentity{Version=found[0].Groups[1].Value,Build=build};
 }
 public static GrIdentity MatchTarget(byte[] gr,string catVersion,string target){
  GrIdentity identity=ReadGr(gr);string expected=Normalize(target);
  if(Normalize(identity.Version)!=expected||Normalize(catVersion)!=expected)
   throw new Exception("实际固件版本与目标不符：GR="+identity.Version+"，CAT1="+catVersion+"，整机目标="+target+"。先设置两端版本并重新编译/生成，不能只改包名。");
  return identity;
 }
}
}
