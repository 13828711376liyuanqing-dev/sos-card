// SAM | 2026-10-22 11:25 +08:00 | Generate script-only EC7xx SOTA with the installed vendor tools,
// then decompress/read back every byte. Never turn a USB image or a filename into install authority.
using System;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Collections.Generic;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Threading.Tasks;

namespace YpOta {
public sealed class Cat1Image {
 public string File, Project, Version, ScriptHash, Hash, RecordHash;
 public int ScriptBytes, PackageBytes, FileCount;
}
public static class Cat1Native {
 public const uint Magic=0xeac37218, ScriptAddress=0x56e000;
 public const int ScriptCapacity=0x80000, BlockSize=0x40000, FotaRegion=0x106000, BackupBytes=0x18000;
 public const string SocName="LuatOS-SoC_V2052_Air780EGH_113.soc";
 public const string SocHash="29a3f2dc4eb07badc1093bf8b48f04fa54b40a6d537d1c0814dcfadf53693eec";
 const string CrcName=".airm2m_all_crc#.bin";
 static readonly string[] LibNames={"air1103","es8311","exsipclient","exsipproto"};
 static readonly string[] LibHashes={"223455916c8ff2330129fc717f6ac5eb8f90f976c77cbf89023dbffe4b88c022","36facad70f0198659dee017b99dd2562fe0e8e67bf6bb79bfbc79a026e7f59dd","292068c5fd0307a3bc6a6ac74da111c113a4a18ff3c29cba2c826962162790ee","8bf33ca310c33bb47fea4d4194fa8d46af0581c1a7f3c2e3834db422cccb8020"};
 static readonly UTF8Encoding Utf8=new UTF8Encoding(false,true);
 // SAM | 2026-10-24 +08:00 | Keep legacy libfota2 source, but omit its unused second installer from controlled-runtime images; any live reference keeps it.
 public static bool OmitLegacyFota(IDictionary<string,string> sources){
  if(!sources.ContainsKey("libfota2.lua")||!sources.ContainsKey("ota_runtime.lua")||!sources.ContainsKey("update.lua"))return false;
  foreach(var p in sources)if(p.Key!="libfota2.lua"&&WithoutComments(p.Value).Contains("libfota2"))return false;
  return true;
 }
 public static string FileHash(string p){return PackCore.Hash(File.ReadAllBytes(p));}
 // SAM | 2026-10-24 +08:00 | Reuse the validated native decoder for first-test review binding; never run or install decoded bytes.
 public static byte[] DecodeForReview(string file,string luatools,string work){return Decode(ReadBounded(file,FotaRegion-BackupBytes),luatools,work);}
 static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
 static byte[] Md5(byte[] b){using(MD5 md=MD5.Create())return md.ComputeHash(b);}
 static byte[] Slice(byte[] b,int start,int count){Need(start>=0&&count>=0&&(long)start+count<=b.Length,"CAT1文件截断");byte[] r=new byte[count];Buffer.BlockCopy(b,start,r,0,count);return r;}
 static bool Equal(byte[] a,byte[] b){if(a.Length!=b.Length)return false;for(int i=0;i<a.Length;i++)if(a[i]!=b[i])return false;return true;}
 static uint U32(byte[] b,int at){Need(at>=0&&at+4<=b.Length,"CAT1头截断");return BitConverter.ToUInt32(b,at);}
 static uint HeaderCrc(byte[] b,int start,int count){uint c=0xffffffff;for(int i=start;i<start+count;i++){c^=b[i];for(int j=0;j<8;j++)c=(c>>1)^((c&1)!=0?0xedb88320u:0);}return c;}
 static byte[] ReadBounded(string file,int limit){Need(File.Exists(file),"文件不存在："+file);Need(new FileInfo(file).Length<=limit,"文件超过允许容量："+Path.GetFileName(file));byte[] b=File.ReadAllBytes(file);Need(b.Length<=limit,"读取期间文件超限");return b;}
 static string Tool(string root,string relative,string hash){string p=Path.Combine(Path.GetFullPath(root),relative);Need(File.Exists(p),"缺少Luatools配套工具："+relative+"。请选择已解压运行过的Luatools目录。");Need(FileHash(p)==hash,"Luatools工具版本未匹配已验证基线："+relative);return p;}
 static string ZipTool(string root){return Tool(root,@"_temp\uis_download\7zip\32\7z.exe","da50299f5d8cc7700f6c15ec0dafe46d5e3681b807a80618b37f5e3ee4f93fb7");}
 static string Quote(string s){Need(s.IndexOf('"')<0&&s.IndexOf('\r')<0&&s.IndexOf('\n')<0,"路径包含非法字符");return "\""+s+"\"";}
 static string Run(string exe,string args,string work,string log){
  ProcessStartInfo si=new ProcessStartInfo(exe,args){WorkingDirectory=work,UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true};
  using(Process p=Process.Start(si)){
   Task<string> stdout=p.StandardOutput.ReadToEndAsync(),stderr=p.StandardError.ReadToEndAsync();
   if(!p.WaitForExit(60000)){p.Kill();throw new Exception("厂商工具超时："+Path.GetFileName(exe));}
   string text=stdout.Result+stderr.Result;File.AppendAllText(log,Path.GetFileName(exe)+" "+args+Environment.NewLine+text+Environment.NewLine,Encoding.UTF8);
   Need(p.ExitCode==0,"厂商工具失败："+Path.GetFileName(exe)+"；详见 "+log);return text;
  }
 }
 // Remove comments only for dependency/version discovery; original bytes are compiled unchanged.
 public static string WithoutComments(string s){
  StringBuilder b=new StringBuilder();int i=0;
  while(i<s.Length){
   if(s[i]=='\''||s[i]=='"'){char q=s[i];b.Append(s[i++]);while(i<s.Length){char x=s[i++];b.Append(x);if(x=='\\'&&i<s.Length)b.Append(s[i++]);else if(x==q)break;}continue;}
   bool comment=i+1<s.Length&&s[i]=='-'&&s[i+1]=='-';int start=i+(comment?2:0);
   int bracket=start;if(bracket<s.Length&&s[bracket]=='['){bracket++;while(bracket<s.Length&&s[bracket]=='=')bracket++;}else bracket=-1;
   if(bracket>=0&&bracket<s.Length&&s[bracket]=='['){string end="]"+new string('=',bracket-start-1)+"]";int close=s.IndexOf(end,bracket+1,StringComparison.Ordinal);Need(close>=0,"Lua长注释/字符串未闭合");int length=close+end.Length-i;
    if(comment){for(int j=0;j<length;j++)b.Append(s[i+j]=='\n'?'\n':' ');}else b.Append(s,i,length);i+=length;continue;}
   if(comment){while(i<s.Length&&s[i]!='\n'){b.Append(' ');i++;}continue;}
   b.Append(s[i++]);
  }return b.ToString();
 }
 public static string[] Identity(string main){
  string clean=WithoutComments(main);MatchCollection p=Regex.Matches(clean,@"(?m)^\s*PROJECT\s*=\s*[""']([A-Za-z0-9_]+)[""']\s*(?:;?\s*)$"),v=Regex.Matches(clean,@"(?m)^\s*VERSION\s*=\s*[""']([0-9]{3}\.[0-9]{3}\.[0-9]{3})[""']\s*(?:;?\s*)$");
  Need(p.Count==1&&v.Count==1,"main.lua须有唯一PROJECT和三段三位VERSION（如001.000.001）；工具不会改版本");return new[]{p[0].Groups[1].Value,v[0].Groups[1].Value};
 }
 static void AddChecksum(BinaryWriter w,byte[] head){w.Write(head);int sum=0;foreach(byte x in head)sum+=x;w.Write((ushort)sum);}
 // SAM | 2026-10-24 +08:00 | Match the observed Luatools USB import limit, so native generation cannot emit an unusable USB collection.
 static byte[] EntryHead(string name,int size){byte[] n=Utf8.GetBytes(name);Need(n.Length>0&&n.Length<=23&&Path.GetFileName(name)==name,"Luatools文件名超过23字节或不是平铺文件名："+name);
  using(MemoryStream m=new MemoryStream())using(BinaryWriter w=new BinaryWriter(m)){w.Write((byte)1);w.Write((byte)4);w.Write(0xa55aa55au);w.Write((byte)2);w.Write((byte)n.Length);w.Write(n);w.Write((byte)3);w.Write((byte)4);w.Write(size);w.Write((byte)254);w.Write((byte)2);return m.ToArray();}}
 public static byte[] LuaDb(SortedDictionary<string,byte[]> files){
  Need(files.Count>0&&files.Count<1000,"LuaDB文件数错误");using(MemoryStream m=new MemoryStream())using(BinaryWriter w=new BinaryWriter(m)){
   using(MemoryStream h=new MemoryStream())using(BinaryWriter x=new BinaryWriter(h)){x.Write((byte)1);x.Write((byte)4);x.Write(0xa55aa55au);x.Write((byte)2);x.Write((byte)2);x.Write((ushort)2);x.Write((byte)3);x.Write((byte)4);x.Write(24);x.Write((byte)4);x.Write((byte)2);x.Write((ushort)(files.Count+1));x.Write((byte)254);x.Write((byte)2);AddChecksum(w,h.ToArray());}
   foreach(var pair in files){Need(pair.Key!=CrcName,"保留校验文件名");AddChecksum(w,EntryHead(pair.Key,pair.Value.Length));w.Write(pair.Value);Need(m.Length+64<=ScriptCapacity,"CAT1编译后LuaDB超过512KiB脚本分区");}
   AddChecksum(w,EntryHead(CrcName,16));w.Write(Md5(m.ToArray()));return m.ToArray();
  }
 }
 static void CheckSum(byte[] b,int start,int end){int sum=0;for(int i=start;i<end-2;i++)sum+=b[i];Need((ushort)sum==BitConverter.ToUInt16(b,end-2),"LuaDB头校验失败");}
 public static SortedDictionary<string,byte[]> ReadLuaDb(byte[] b){
  Need(b.Length>=24&&b.Length<=ScriptCapacity,"LuaDB脚本容量超限");Need(Equal(Slice(b,0,18),new byte[]{1,4,0x5a,0xa5,0x5a,0xa5,2,2,2,0,3,4,24,0,0,0,4,2})&&b[20]==254&&b[21]==2,"不是LuaDB v2脚本镜像");CheckSum(b,0,24);
  int count=BitConverter.ToUInt16(b,18),pos=24;Need(count>=2&&count<1001,"LuaDB文件数错误");var result=new SortedDictionary<string,byte[]>(StringComparer.Ordinal);
  for(int i=0;i<count;i++){
   int start=pos;Need(Equal(Slice(b,pos,8),new byte[]{1,4,0x5a,0xa5,0x5a,0xa5,2,b[pos+7]}),"LuaDB文件头错误");int n=b[pos+7];Need(n>0&&n<=28,"LuaDB名字长度错误");pos+=8;
   string name=Utf8.GetString(Slice(b,pos,n));pos+=n;Need(Equal(Slice(b,pos,2),new byte[]{3,4}),"LuaDB长度字段错误");pos+=2;uint size=U32(b,pos);pos+=4;Need(size<=ScriptCapacity,"LuaDB条目超限");Need(Equal(Slice(b,pos,2),new byte[]{254,2}),"LuaDB校验字段错误");pos+=4;CheckSum(b,start,pos);
   byte[] data=Slice(b,pos,(int)size);
   if(i==count-1){Need(name==CrcName&&size==16&&Equal(data,Md5(Slice(b,0,pos))),"LuaDB整包MD5错误");}
   else {Need(name!=CrcName&&!result.ContainsKey(name)&&name.IndexOfAny(new[]{'/','\\',':','\0'})<0,"LuaDB重复/非法文件名");result.Add(name,data);}
   pos+=(int)size;
  }Need(pos==b.Length,"LuaDB尾部存在额外数据");Need(result.ContainsKey("main.luac")||result.ContainsKey("main.lua"),"LuaDB缺少main入口");return result;
 }
 public static byte[] CheckContainer(byte[] b){
  Need(b.Length>=138&&b.Length<=FotaRegion-BackupBytes,"CAT1原生OTA包超过FOTA区扣除备份后的预算，或文件过短");
  Need(U32(b,0)==Magic&&U32(b,4)==HeaderCrc(b,8,84),"CAT1不是有效EC7xx SOTA头（不能选Lua/SOC/普通BIN）");
  for(int i=8;i<52;i++)Need(b[i]==0,"仅支持脚本升级：拒绝底包/AP/CP/整片升级标志");
  Need(U32(b,56)==0&&U32(b,52)==b.Length-92,"SOTA组件长度错误或包含底包差分");for(int i=76;i<92;i++)Need(b[i]==0,"SOTA包含非脚本组件");
  byte[] payload=Slice(b,92,b.Length-92);Need(Equal(Md5(payload),Slice(b,60,16)),"SOTA脚本压缩包MD5不匹配");
  Need(U32(payload,0)==Magic&&U32(payload,4)==payload.Length-36,"脚本OTA压缩头错误");
  uint raw=U32(payload,8);Need(raw>=24&&raw<=ScriptCapacity,"CAT1脚本解压后超过512KiB");
  Need(U32(payload,28)==BlockSize&&U32(payload,32)==ScriptAddress,"CAT1脚本地址/块大小不匹配：禁止写入用户FS/FDB/NVRAM");
  int pos=36,blocks=0;while(pos<payload.Length){Need(pos+10<=payload.Length&&payload[pos]==5&&payload[pos+1]==102&&U32(payload,pos+2)==BlockSize,"脚本LZMA块头不匹配");uint size=U32(payload,pos+6);Need(size>0&&size<=BlockSize+4096&&(long)pos+10+size<=payload.Length,"脚本LZMA块长度错误");pos+=10+(int)size;blocks++;}
  Need(blocks==(raw+BlockSize-1)/BlockSize,"脚本块数与解压长度不匹配");return payload;
 }
 public static byte[] Decode(byte[] b,string luatools,string work){
  byte[] payload=CheckContainer(b);Directory.CreateDirectory(work);string seven=ZipTool(luatools);int pos=36,index=0,remaining=(int)U32(payload,8);
  using(MemoryStream all=new MemoryStream()){
   while(pos<payload.Length){int packed=(int)U32(payload,pos+6),expected=Math.Min(BlockSize,remaining);string name="block"+index;string lzma=Path.Combine(work,name+".lzma");
    using(BinaryWriter w=new BinaryWriter(File.Create(lzma))){w.Write(payload[pos+1]);w.Write(BlockSize);w.Write((ulong)expected);w.Write(payload,pos+10,packed);}
    Run(seven,"e "+name+".lzma -odecoded -y",work,Path.Combine(work,"vendor.log"));byte[] decoded=ReadBounded(Path.Combine(work,"decoded",name),expected);Need(decoded.Length==expected,"LZMA解压长度不符");all.Write(decoded,0,decoded.Length);pos+=10+packed;remaining-=expected;index++;
   }byte[] script=all.ToArray();Need(Equal(Md5(script),Slice(payload,12,16)),"脚本解压后MD5不符");ReadLuaDb(script);return script;
  }
 }
 public static Cat1Image Inspect(string file,string luatools,string work){
  Need(Path.GetExtension(file).Equals(".sota",StringComparison.OrdinalIgnoreCase),"CAT1请选择本工具生成的.sota及同名.json；Lua、SOC、普通BIN不可选");
  byte[] bytes=ReadBounded(file,FotaRegion-BackupBytes);byte[] script=Decode(bytes,luatools,work);string side=file+".json";
  byte[] record=ReadBounded(side,1024*1024);var report=PackCore.Json.Deserialize<Dictionary<string,object>>(Utf8.GetString(record));
  Need(Convert.ToString(report["schema"])=="YP001_CAT1_SCRIPT_SOTA_V1"&&Convert.ToString(report["soc_sha256"])==SocHash,"CAT1生成记录底包/格式不符");
  Need(Convert.ToString(report["sha256"])==PackCore.Hash(bytes)&&Convert.ToString(report["script_sha256"])==PackCore.Hash(script),"CAT1文件与生成记录不匹配");
  string version=Convert.ToString(report["version"]),project=Convert.ToString(report["project"]);Need(Regex.IsMatch(version,@"^\d{3}\.\d{3}\.\d{3}$")&&Regex.IsMatch(project,@"^[A-Za-z0-9_]+$"),"CAT1生成记录版本格式错误");
  var files=ReadLuaDb(script);
  // SAM | 2026-10-23 +08:00 | Bind every boot-identity hash to decoded bytes before signing the record; a correct outer SOTA hash does not authenticate its sidecar file map.
  object recordedHashes,recordedCount;
  Need(report.TryGetValue("compiled_sha256",out recordedHashes)&&recordedHashes is Dictionary<string,object>,"CAT1生成记录缺少完整文件指纹，请重新生成");
  var fileHashes=(Dictionary<string,object>)recordedHashes;
  Need(report.TryGetValue("file_count",out recordedCount)&&recordedCount is int&&(int)recordedCount==files.Count&&fileHashes.Count==files.Count,"CAT1生成记录文件数量与实际固件不一致");
  foreach(var item in files){object digest;Need(fileHashes.TryGetValue(item.Key,out digest)&&digest is string&&(string)digest==PackCore.Hash(item.Value),"CAT1生成记录文件指纹不匹配："+item.Key);}
  byte[] main;Need(files.TryGetValue("main.luac",out main),"缺少编译后的main");string text=Encoding.ASCII.GetString(main);
  Need(text.Contains(version)&&text.Contains(project),"生成记录版本/项目与main字节码不一致");
  return new Cat1Image{File=file,Project=project,Version=version,Hash=PackCore.Hash(bytes),RecordHash=PackCore.Hash(record),ScriptHash=PackCore.Hash(script),ScriptBytes=script.Length,PackageBytes=bytes.Length,FileCount=files.Count};
 }
 public static Cat1Image Build(string source,string luatools,string output){
  source=Path.GetFullPath(source);luatools=Path.GetFullPath(luatools);output=Path.GetFullPath(output);
  Need(Directory.Exists(source),"请选择Air780EGH源码文件夹");string soc=Path.Combine(source,"soc",SocName);Need(File.Exists(soc)&&FileHash(soc)==SocHash,"仅支持已验证的V2052 Air780EGH_113底包；SOC不匹配，拒绝套用分区");
  string compiler=Tool(luatools,@"_temp\tools\luac_64bit.exe","e4180102b388a09153c416ca2aa80dd90df257a10efe8abbbd5bcc5285ab0957");
  string vendor=Tool(luatools,@"_temp\tools\soc_tools.exe","2379a11446a8e3d6436f5acde5be14d76cb41e7c3fd64c620ac74d1340bf07d4");ZipTool(luatools);
  var paths=new SortedDictionary<string,string>(StringComparer.Ordinal);foreach(string path in Directory.GetFiles(source,"*.lua")){Need(!paths.ContainsKey(Path.GetFileName(path)),"重复脚本名");paths.Add(Path.GetFileName(path),path);}
  int sourceLuaCount=paths.Count;
  var sourceText=new Dictionary<string,string>();foreach(var p in paths)sourceText.Add(p.Key,File.ReadAllText(p.Value,Utf8));
  bool omittedLegacy=OmitLegacyFota(sourceText);if(omittedLegacy)paths.Remove("libfota2.lua");
  Need(paths.ContainsKey("main.lua"),"缺少main.lua");Need(paths.Count<1000,"脚本数异常");
  string libs=Path.Combine(luatools,@"resource\soc_script\v2026.10.13.20\lib");
  for(int i=0;i<LibNames.Length;i++){string name=LibNames[i]+".lua";if(paths.ContainsKey(name))continue;string p=Path.Combine(libs,name);Need(File.Exists(p)&&FileHash(p)==LibHashes[i],"缺少已验证的厂商依赖："+name+"；需要Luatools资源v2026.10.13.20");paths.Add(name,p);}
  string audio=Path.Combine(source,"sample-6s.mp3");Need(File.Exists(audio),"缺少业务音频sample-6s.mp3");paths.Add("sample-6s.mp3",audio);
  var snapshot=new SortedDictionary<string,byte[]>(StringComparer.Ordinal);var hashes=new Dictionary<string,string>();long inputSize=0;
  foreach(var item in paths){byte[] raw=ReadBounded(item.Value,4*1024*1024);inputSize+=raw.Length;Need(inputSize<=16*1024*1024,"源码集合超过16MiB输入上限");snapshot.Add(item.Key,raw);hashes.Add(item.Key,PackCore.Hash(raw));}
  string[] identity=Identity(Utf8.GetString(snapshot["main.lua"]).TrimStart('\ufeff'));
  string nativeModules="adc airlink audio audio_v2 bit32 bit64 camera can cc codec coroutine crypto debug eink errDump fastlz fatfs fft fonts fota fs fskv ftp gmssl gpio gtfont hmeta ht1621 http httpsrv i2c i2s icmp iconv io ioqueue iotauth iperf json lcd lf libgnss log lora2 math mcu miniz mobile mqtt ndk netdrv onewire os otp pack package pins pm protobuf pwm rsa rtc rtos sensor sfud sms socket spi string table timer tp u8g2 uart utf8 voip wdt websocket wlan ws2812 xxtea yhm27xx ymodem zbuff sys sysplus";
  foreach(var item in snapshot)if(item.Key.EndsWith(".lua"))foreach(Match match in Regex.Matches(WithoutComments(Utf8.GetString(item.Value)),@"\brequire\s*(?:\(\s*)?[""']([A-Za-z_][A-Za-z_0-9.]*)[""']")){
   string module=match.Groups[1].Value;Need(snapshot.ContainsKey(module+".lua")||Array.IndexOf(nativeModules.Split(' '),module)>=0,"缺少Lua依赖："+module+"（来自"+item.Key+"）；请放入源码目录后重试");}
  Directory.CreateDirectory(output);string work=Path.Combine(output,"work_"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(work);string log=Path.Combine(work,"vendor.log");
  var compiled=new SortedDictionary<string,byte[]>(StringComparer.Ordinal);int index=0;
  foreach(var item in snapshot){
   if(item.Key.EndsWith(".lua",StringComparison.OrdinalIgnoreCase)){
    string input="src"+index+".lua",dest="out"+index+".luac";File.WriteAllBytes(Path.Combine(work,input),item.Value);
    Run(compiler,"-s -o "+dest+" "+input,work,log);byte[] bytes=ReadBounded(Path.Combine(work,dest),ScriptCapacity);
    Need(bytes.Length>32&&Equal(Slice(bytes,0,6),new byte[]{27,76,117,97,83,0}),"编译器输出不是Lua5.3字节码");compiled.Add(Path.ChangeExtension(item.Key,".luac"),bytes);index++;
   }else compiled.Add(item.Key,item.Value);
  }
  byte[] script=LuaDb(compiled);ReadLuaDb(script);File.WriteAllBytes(Path.Combine(work,"script.bin"),script);File.WriteAllBytes(Path.Combine(work,"dummy.bin"),new byte[0]);
  Run(vendor,"zip_file eac37218 56E000 script.bin script_fota.bin 40000 1",work,log);Need(File.Exists(Path.Combine(work,"script_fota.bin")),"厂商工具未生成脚本压缩包");
  Run(vendor,"make_ota_file eac37218 0 0 0 0 0 script_fota.bin dummy.bin output.sota",work,log);
  byte[] ota=ReadBounded(Path.Combine(work,"output.sota"),FotaRegion-BackupBytes);byte[] readback=Decode(ota,luatools,Path.Combine(work,"readback"));Need(Equal(script,readback),"OTA解压结果与输入脚本不一致");
  foreach(var p in paths)Need(FileHash(p.Value)==hashes[p.Key],"生成期间源码变化："+p.Key+"；请重试");Need(FileHash(soc)==SocHash,"生成期间SOC变化");
  Need(Directory.GetFiles(source,"*.lua").Length==sourceLuaCount,"生成期间源码文件集合变化");
  if(omittedLegacy)Need(File.ReadAllText(Path.Combine(source,"libfota2.lua"),Utf8)==sourceText["libfota2.lua"],"生成期间旧FOTA源码变化");
  string hash=PackCore.Hash(ota),file=Path.Combine(output,"CAT1_"+identity[0]+"_"+identity[1]+"_"+hash.Substring(0,12)+"_"+Guid.NewGuid().ToString("N").Substring(0,6)+".sota");
  var report=new {schema="YP001_CAT1_SCRIPT_SOTA_V1",project=identity[0],version=identity[1],sha256=hash,script_sha256=PackCore.Hash(script),soc_file=SocName,soc_sha256=SocHash,
   package_bytes=ota.Length,script_bytes=script.Length,script_limit=ScriptCapacity,script_address=ScriptAddress,script_end=(long)ScriptAddress+script.Length,
   fota_region_bytes=FotaRegion,fota_backup_reserve=BackupBytes,fota_budget=FotaRegion-BackupBytes,user_fs_start=0x754000,user_fs_bytes=0x80000,
   file_count=compiled.Count,source_sha256=hashes,compiled_sha256=Hashes(compiled),excluded_unused_sources=omittedLegacy?new[]{"libfota2.lua"}:new string[0],native_structure_verified=true,decompressed_readback_verified=true,
   user_data_ranges_in_payload=false,signature_verified=false,device_installation_verified=false,version_changed_by_tool=false,build_kind="SCRIPT_ONLY_SAME_CORE",vendor_log=Path.GetFileName(work)+"/vendor.log"};
  using(FileStream fs=new FileStream(file,FileMode.CreateNew,FileAccess.Write))fs.Write(ota,0,ota.Length);File.WriteAllText(file+".json",PackCore.Json.Serialize(report),Utf8);
  return new Cat1Image{File=file,Project=identity[0],Version=identity[1],Hash=hash,ScriptHash=PackCore.Hash(script),ScriptBytes=script.Length,PackageBytes=ota.Length,FileCount=compiled.Count};
 }
 static int CountExternal(SortedDictionary<string,string> paths,string root){int count=0;foreach(var p in paths)if(!Path.GetDirectoryName(p.Value).Equals(root,StringComparison.OrdinalIgnoreCase))count++;return count;}
 static Dictionary<string,string> Hashes(SortedDictionary<string,byte[]> files){var result=new Dictionary<string,string>();foreach(var p in files)result.Add(p.Key,PackCore.Hash(p.Value));return result;}
}
}
