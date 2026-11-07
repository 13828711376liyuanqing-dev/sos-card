// SAM | 2026-10-22 +08:00 | Portable capacity-first offline packager. Native install authority remains unavailable.
using System;
using System.IO;
using System.IO.Compression;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

namespace YpOta {
public static class PackCore {
// SAM | 2026-10-23 +08:00 | Enforce selected preserved-data slot limit; deployment is not approved.
 public const int GrSlot=442368, SignatureBytes=904, CatFsTotal=524288, Reserve=16384;
 public const uint GrStart=0x00202000, NvdsStart=0x002FE000;
 public static readonly JavaScriptSerializer Json=new JavaScriptSerializer();
 public static int CompareVersion(string a,string b) {
  int[] x=Version(a),y=Version(b);for(int i=0;i<4;i++){if(x[i]!=y[i])return x[i].CompareTo(y[i]);}return 0;
 }
 static int[] Version(string text) {
  if(text==null || !Regex.IsMatch(text,@"^(0|[1-9][0-9]{0,4})(\.(0|[1-9][0-9]{0,4})){1,3}$"))throw new Exception("版本必须为2～4段数字，无前导零，例如1.0、1.3");
  int[] values=new int[4];string[] parts=text.Split('.');for(int i=0;i<parts.Length;i++){values[i]=int.Parse(parts[i]);if(values[i]>65535)throw new Exception("版本段超过65535");}return values;
 }
 static string Name(string value) {
  value=(value??"").Trim();if(value.Length>48 || value.Contains("---") || Regex.IsMatch(value,"[<>:\"/\\\\|?*\\x00-\\x1f]"))throw new Exception("名称包含非法字符或保留分隔符---");return value;
 }
 public static string Hash(byte[] bytes) {using(SHA256 sha=SHA256.Create()){return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();}}
 // SAM | 2026-10-22 +08:00 | Signed entry MD5 is distinct from the platform's whole-ZIP transport MD5.
 static string Md5(byte[] bytes){using(MD5 md=MD5.Create())return BitConverter.ToString(md.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();}
 public static byte[] ReadGr(string file) {
  if(!File.Exists(file))throw new Exception("5526固件不存在");
  if(new FileInfo(file).Length>16*1024*1024)throw new Exception("输入文件超过读取上限");
  byte[] data;
  if(Path.GetExtension(file).Equals(".hex",StringComparison.OrdinalIgnoreCase)) {
   Dictionary<uint,byte> memory=new Dictionary<uint,byte>();uint addressBase=0,highest=0;bool eof=false;
   foreach(string input in File.ReadLines(file)) {
    string line=input.Trim();if(line.Length==0)continue;
    if(eof || line[0]!=':' || line.Length%2!=1)throw new Exception("HEX结构错误或EOF后存在数据");
    byte[] record=new byte[(line.Length-1)/2];int sum=0;
    for(int i=0;i<record.Length;i++){record[i]=Convert.ToByte(line.Substring(i*2+1,2),16);sum+=record[i];}
    if(record.Length<5 || record.Length!=record[0]+5 || sum%256!=0)throw new Exception("HEX长度/校验和错误");
    int count=record[0],kind=record[3];uint offset=(uint)(record[1]*256+record[2]);
    if(kind==4 || kind==2){if(count!=2 || offset!=0)throw new Exception("HEX地址记录错误");addressBase=(uint)(record[4]*256+record[5])<<(kind==4?16:4);}
    else if(kind==1){if(count!=0 || offset!=0)throw new Exception("HEX EOF错误");eof=true;}
    else if(kind==0) {
     if(offset+(uint)count>65536)throw new Exception("HEX跨地址窗口");
     for(int i=0;i<count;i++) {
      ulong wide=(ulong)addressBase+offset+(uint)i;
      if(wide<GrStart || wide>=GrStart+GrSlot-SignatureBytes)throw new Exception("5526地址越界：保护Boot/SCA/NVDS；签名尾部必须留904字节");
      uint address=(uint)wide;byte prior;
      if(memory.TryGetValue(address,out prior)&&prior!=record[4+i])throw new Exception("HEX重叠字节冲突");
      memory[address]=record[4+i];if(address>highest)highest=address;
     }
    } else if(kind!=3 && kind!=5)throw new Exception("不支持的HEX记录");
   }
   if(!eof || !memory.ContainsKey(GrStart))throw new Exception("HEX缺少EOF或原A入口0x00202000");
   data=new byte[highest-GrStart+1];for(int i=0;i<data.Length;i++)data[i]=255;
   foreach(KeyValuePair<uint,byte> pair in memory)data[pair.Key-GrStart]=pair.Value;
  } else if(Path.GetExtension(file).Equals(".bin",StringComparison.OrdinalIgnoreCase))data=File.ReadAllBytes(file);
  else throw new Exception("5526请选择应用HEX或原始BIN；不接受AXF/ZIP/整片镜像");
  if(data.Length<8 || data.Length>GrSlot-SignatureBytes)throw new Exception("5526正文+904字节签名预算超过442368字节槽，或镜像为空");
  uint msp=BitConverter.ToUInt32(data,0),reset=BitConverter.ToUInt32(data,4),entry=reset&~1u;
  if(msp<=0x20006000 || msp>0x20040000 || (msp&7)!=0 || (reset&1)==0 || entry<GrStart+8 || entry>=GrStart+data.Length)throw new Exception("5526栈/复位向量不符合当前A槽与RAM布局");
  return data;
 }
 public static void CheckSpace(int grBytes,int catBytes,int freeBytes) {
  if(grBytes<8 || grBytes>GrSlot-SignatureBytes)throw new Exception("5526正文加签名预算越界");
  if(freeBytes<=Reserve || freeBytes>CatFsTotal)throw new Exception("CAT1空间未知或超过已知512KiB用户文件区，拒绝放行");
  if(catBytes<=0 || (long)catBytes+Reserve>freeBytes)throw new Exception("CAT1包+保留空间超过用户文件区可用空间");
  if((long)grBytes+SignatureBytes+Reserve>freeBytes)throw new Exception("5526暂存包+签名预算+保留空间超过CAT1可用文件区");
 }
 // SAM | 2026-10-22 11:30 +08:00 | Require a parsed and decompressed native script SOTA instead of trusting extensions.
 public static string Package(string gr,string cat,string output,string from,string to,string prefix,string suffix,int freeBytes,string luatools=null,string keyDirectory=null,string grContracts=null) {
  return PackageCore(gr,cat,output,from,to,prefix,suffix,freeBytes,luatools,keyDirectory,grContracts);
 }
 // SAM | 2026-10-24 +08:00 | Offline preparation has no measured free-space value; use only the fixed capacity profile and retain every device installation gate.
 public static string PackageOfflineCandidate(string gr,string cat,string output,string from,string to,string prefix,string suffix,string luatools=null,string keyDirectory=null,string grContracts=null) {
  return PackageCore(gr,cat,output,from,to,prefix,suffix,null,luatools,keyDirectory,grContracts);
 }
 // SAM | 2026-10-24 +08:00 | A separate explicit admission path fixes the
 // always-offline packager without turning incomplete device evidence into true.
 public static string PackageForDevice(string gr,string cat,string output,string from,string to,string prefix,string suffix,int freeBytes,string admissionFile,string luatools,string keyDirectory,string grContracts=null) {
  if(String.IsNullOrEmpty(admissionFile)||!File.Exists(admissionFile))throw new Exception("INSTALL_ADMISSION_REQUIRED");
  return PackageCore(gr,cat,output,from,to,prefix,suffix,freeBytes,luatools,keyDirectory,grContracts,admissionFile);
 }
 // SAM | 2026-10-24 +08:00 | A first controlled trial has reviewed safety and explicitly unaccepted installation/KV; do not fabricate production acceptance fields.
 // SAM | 2026-10-29 07:07 +08:00 | User approved a second controlled first trial 1.0.2->1.5.1; ranges come from a fixed whitelist, never from caller-chosen versions.
 // SAM | 2026-10-29 22:02 +08:00 | User approved round 2 1.5.1->1.5.2 (whitelist entry; the source is now an explicit argument, default 1.0.2 unchanged).
 internal static readonly string[][] FirstTrialRanges={new[]{"1.0.2","1.5.0"},new[]{"1.0.2","1.5.1"},new[]{"1.5.1","1.5.2"}};
 // SAM | 2026-10-30 10:46 +08:00 | Ranges authorized at run time by a signed authorization file (YpOtaPack.exe); empty unless that tool adds one, so the fixed list above is unchanged.
 public static readonly List<string[]> ExtraRanges=new List<string[]>();
 internal static bool IsFirstTrialRange(string from,string to){foreach(var r in FirstTrialRanges)if(r[0]==from&&r[1]==to)return true;foreach(var r in ExtraRanges)if(r[0]==from&&r[1]==to)return true;return false;}
 public static string PackageForFirstTrial(string signedGr,string cat,string output,int freeBytes,string trialFile,string luatools,string keys,string contracts,string target="1.5.0",string source="1.0.2"){
  if(!IsFirstTrialRange(source,target))throw new Exception("FIRST_TRIAL_RANGE");
  byte[] image=File.ReadAllBytes(signedGr);string pub=File.ReadAllText(Path.Combine(keys,BundleSigning.PublicName));
  GrProjectNative.Verify(image,pub,BundleSigning.Fingerprint(pub),GrProjectNative.ContractHash(Path.Combine(contracts,"layout_candidate.json")),GrProjectNative.ContractHash(Path.Combine(contracts,"data_contract_candidate.json")));
  byte[] payload=new byte[image.Length-SignatureBytes];Array.Copy(image,payload,payload.Length);
  string work=Path.Combine(output,"trial_work_"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(work);
  string raw=Path.Combine(work,"GR_payload.bin");File.WriteAllBytes(raw,payload);
  return PackageCore(raw,cat,output,source,target,"YP001","FIRST",freeBytes,luatools,keys,contracts,null,trialFile,signedGr);
 }
 internal static void ValidateFirstTrial(Dictionary<string,object> a,string grHash,string catHash,string from="1.0.2",string to="1.5.0"){
  if(a==null)throw new Exception("FIRST_TRIAL_REQUIRED");object v;
  if(!IsFirstTrialRange(from,to))throw new Exception("FIRST_TRIAL_RANGE");
  string[] fields={"schema","source_version","target_version","gr_payload_sha256","cat_package_sha256","cat_core_sha256"};
  string[] values={"YP001_FIRST_CONTROLLED_TRIAL_V1",from,to,grHash,catHash,Cat1Native.SocHash};
  for(int i=0;i<fields.Length;i++)if(!a.TryGetValue(fields[i],out v)||!(v is string)||(string)v!=values[i])throw new Exception("FIRST_TRIAL_BINDING_"+fields[i]);
  foreach(string k in new[]{"activation_review_completed","gr_boot_verified","readable_data_comparison_required","preserve_user_data"})
   if(!a.TryGetValue(k,out v)||!(v is bool)||!(bool)v)throw new Exception("FIRST_TRIAL_REVIEW_"+k);
  foreach(string k in new[]{"installation_accepted","raw_kv_accepted"})
   if(!a.TryGetValue(k,out v)||!(v is bool)||(bool)v)throw new Exception("FIRST_TRIAL_ACCEPTANCE_"+k);
  if(!a.TryGetValue("review_sha256",out v)||!(v is string)||!Regex.IsMatch((string)v,"^[0-9a-f]{64}$")||(string)v==new string('0',64))throw new Exception("FIRST_TRIAL_REVIEW_HASH");
 }
 internal static void ValidateInstallAdmission(Dictionary<string,object> a,string from,string to,string grHash,string catHash,string coreHash) {
  if(a==null)throw new Exception("INSTALL_ADMISSION_REQUIRED");
  object value;
  if(!a.TryGetValue("schema",out value)||Convert.ToString(value)!="1")throw new Exception("INSTALL_ADMISSION_SCHEMA");
  string[] keys={"source_version","target_version","gr_payload_sha256","cat_package_sha256","cat_core_sha256"};
  string[] expected={from,to,grHash,catHash,coreHash};
  for(int i=0;i<keys.Length;i++)if(!a.TryGetValue(keys[i],out value)||!(value is string)||(string)value!=expected[i])throw new Exception("INSTALL_BINDING_"+keys[i]);
  foreach(string key in new[]{"gr_boot_verified","gr_layout_verified","cat_native_activation_verified","cat_readonly_data_supported","preserve_user_data"})
   if(!a.TryGetValue(key,out value)||!(value is bool)||!(bool)value)throw new Exception("INSTALL_EVIDENCE_"+key);
  if(!a.TryGetValue("evidence_set_sha256",out value)||!(value is string)||!Regex.IsMatch((string)value,"^[0-9a-f]{64}$")||(string)value==new string('0',64))throw new Exception("INSTALL_EVIDENCE_IDENTITY");
 }
 static string PackageCore(string gr,string cat,string output,string from,string to,string prefix,string suffix,int? freeBytes,string luatools,string keyDirectory,string grContracts,string admissionFile=null,string trialFile=null,string frozenGr=null) {
  if(CompareVersion(to,from)<=0)throw new Exception("禁止同版本或降级");prefix=Name(prefix);suffix=Name(suffix);
  if(Path.GetFullPath(gr).Equals(Path.GetFullPath(cat),StringComparison.OrdinalIgnoreCase))throw new Exception("两端必须选择不同文件");
  byte[] grData=ReadGr(gr);
  if(!File.Exists(cat))throw new Exception("CAT1固件不存在");
  string ext=Path.GetExtension(cat).ToLowerInvariant();
  if(ext!=".sota")throw new Exception("CAT1请选择生成后的.sota文件；请先点击生成CAT1 OTA。普通BIN、SOC、Lua、ZIP不可选");
  long catSize=new FileInfo(cat).Length;
  if(catSize>int.MaxValue)throw new Exception("CAT1文件太大");
  // SAM | 2026-10-24 +08:00 | The profile maximum is a capacity bound, never a fabricated device reading. Strict mode still rejects zero/unknown space.
  CheckSpace(grData.Length,(int)catSize,freeBytes??CatFsTotal);byte[] catData=File.ReadAllBytes(cat);
  if(catData.Length!=catSize)throw new Exception("CAT1文件读取期间发生变化");
  bool installReady=false,firstTrial=false;string admissionHash=null,trialReview=null;
  if(trialFile!=null){
   if(admissionFile!=null||new FileInfo(trialFile).Length>16384)throw new Exception("FIRST_TRIAL_FILE");
   byte[] raw=File.ReadAllBytes(trialFile);var trial=Json.Deserialize<Dictionary<string,object>>(Encoding.UTF8.GetString(raw));
   ValidateFirstTrial(trial,Hash(grData),Hash(catData),from,to);
   string reviewPath=Path.Combine(Path.GetDirectoryName(Path.GetFullPath(trialFile)),"review.json");
   if(!File.Exists(reviewPath)||new FileInfo(reviewPath).Length>65536||Hash(File.ReadAllBytes(reviewPath))!=(string)trial["review_sha256"])throw new Exception("FIRST_TRIAL_REVIEW_FILE");
   var review=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(reviewPath,Encoding.UTF8));object v;
   if(!review.TryGetValue("cat_core_sha256",out v)||Convert.ToString(v)!=Cat1Native.SocHash||
    !review.TryGetValue("native_installation_accepted",out v)||!(v is bool)||(bool)v||
    !review.TryGetValue("raw_kv_accepted",out v)||!(v is bool)||(bool)v)throw new Exception("FIRST_TRIAL_REVIEW_CONTENT");
   admissionHash=Hash(raw);trialReview=(string)trial["review_sha256"];firstTrial=true;installReady=true;
  }
  if(admissionFile!=null){
   if(new FileInfo(admissionFile).Length>16384)throw new Exception("INSTALL_ADMISSION_SIZE");
   byte[] raw=File.ReadAllBytes(admissionFile);
   var admission=Json.Deserialize<Dictionary<string,object>>(Encoding.UTF8.GetString(raw));
   ValidateInstallAdmission(admission,from,to,Hash(grData),Hash(catData),Cat1Native.SocHash);
   string evidencePath=Path.Combine(Path.GetDirectoryName(Path.GetFullPath(admissionFile)),"installation_evidence.json");
   if(!File.Exists(evidencePath)||new FileInfo(evidencePath).Length>65536||Hash(File.ReadAllBytes(evidencePath))!=(string)admission["evidence_set_sha256"])throw new Exception("INSTALL_EVIDENCE_FILE");
   var records=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(evidencePath,Encoding.UTF8));
   object v;
   foreach(string key in new[]{"boot_first_entry_passed","native_fota_safe_window_verified","readonly_files_kv_verified"})
    if(!records.TryGetValue(key,out v)||!(v is bool)||!(bool)v)throw new Exception("INSTALL_RECORD_"+key);
   if(!records.TryGetValue("cat_core_sha256",out v)||Convert.ToString(v)!=Cat1Native.SocHash)throw new Exception("INSTALL_RECORD_CORE");
   admissionHash=Hash(raw);installReady=true;
  }
  Cat1Native.CheckContainer(catData);
  if(string.IsNullOrWhiteSpace(luatools))throw new Exception("请选择Luatools目录，以便解压读回验证CAT1 OTA");
  string check=Path.Combine(output,"verify_"+Guid.NewGuid().ToString("N"));
  Cat1Image catInfo=Cat1Native.Inspect(cat,luatools,check);
  if(firstTrial){
   var build=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(cat+".json",Encoding.UTF8));object v;
   if(!build.TryGetValue("build_kind",out v)||Convert.ToString(v)!="SCRIPT_ONLY_SAME_CORE"||
    !build.TryGetValue("soc_sha256",out v)||Convert.ToString(v)!=Cat1Native.SocHash||
    !build.TryGetValue("user_data_ranges_in_payload",out v)||!(v is bool)||(bool)v)throw new Exception("FIRST_TRIAL_BUILD_KIND");
   // The explicit review reference must actually be embedded in compiled main, not merely an adjacent JSON label.
   byte[] db=Cat1Native.DecodeForReview(cat,luatools,Path.Combine(check,"trial_review"));
   if(!Encoding.ASCII.GetString(Cat1Native.ReadLuaDb(db)["main.luac"]).Contains(trialReview))throw new Exception("FIRST_TRIAL_NOT_PROVISIONED");
  }
  // SAM | 2026-10-22 +08:00 | Both real firmware versions must map to the requested whole-product target.
  GrIdentity grIdentity=FirmwareIdentity.MatchTarget(grData,catInfo.Version,to);
  if(catInfo.Hash!=Hash(catData))throw new Exception("CAT1文件校验期间发生变化");
  byte[] catRecord=File.ReadAllBytes(cat+".json");
  if(Hash(catRecord)!=catInfo.RecordHash)throw new Exception("CAT1生成记录在校验后发生变化");
  // SAM | 2026-10-22 +08:00 | Require the persistent local test key; never regenerate a missing signing identity during packaging.
  keyDirectory=keyDirectory??BundleSigning.DefaultDirectory;string publicXml,keyId;
  using(var key=BundleSigning.LoadPrivate(keyDirectory)){publicXml=key.ToXmlString(false);keyId=BundleSigning.Fingerprint(publicXml);}
  // SAM | 2026-10-23 +08:00 | Generate actual GR PSS bytes inside the offline tool;
  // capacity was checked for payload+904 above. Contract hashes remain unapproved candidates.
  grContracts=grContracts??Path.Combine(Path.GetDirectoryName(Path.GetFullPath(keyDirectory)),"contracts");
  string grLayoutHash=GrProjectNative.ContractHash(Path.Combine(grContracts,"layout_candidate.json"));
  string grDataHash=GrProjectNative.ContractHash(Path.Combine(grContracts,"data_contract_candidate.json"));
  int grPayloadBytes=grData.Length;
  if(frozenGr==null)grData=GrProjectNative.Sign(grData,keyDirectory,grLayoutHash,grDataHash,to);
  else {
   byte[] fixedImage=File.ReadAllBytes(frozenGr);GrProjectNative.Verify(fixedImage,publicXml,keyId,grLayoutHash,grDataHash);
   if(fixedImage.Length!=grData.Length+SignatureBytes)throw new Exception("FIRST_TRIAL_GR_SIZE");
   for(int i=0;i<grData.Length;i++)if(fixedImage[i]!=grData[i])throw new Exception("FIRST_TRIAL_GR_CHANGED");grData=fixedImage;
  }
  // SAM | 2026-10-23 22:30 +08:00 | Carry GR-verifiable CAT approval inside the already signed build record; keep the six-member STORE ZIP format and original sidecar unchanged.
  var approvedCat=Json.Deserialize<Dictionary<string,object>>(Encoding.UTF8.GetString(catRecord));
  approvedCat["gr_cat_proof_hex"]=BitConverter.ToString(GrProjectNative.SignCatProof(catInfo,keyDirectory,grLayoutHash,grDataHash)).Replace("-","").ToLowerInvariant();
  catRecord=Encoding.UTF8.GetBytes(Json.Serialize(approvedCat));
  if(catRecord.Length>16384)throw new Exception("CAT签名生成记录超过端侧16KiB上限");
  string upgrade=from+"---"+to;
  var items=new object[]{new {target="GR5526",path="GR5526/payload.bin",bytes=grData.Length,payload_bytes=grPayloadBytes,sha256=Hash(grData),md5=Md5(grData),format=GrProjectNative.Format,native_verified=true,version=grIdentity.Version},
    new {target="CAT1",path="CAT1/payload.sota",bytes=catData.Length,sha256=Hash(catData),md5=Md5(catData),format="LUATOS_EC7XX_SCRIPT_SOTA",native_verified=true,version=catInfo.Version}};
  var manifest=new {schema=6,product="YP001",upgrade=upgrade,source_version=from,target_version=to,components=items,
   signing_key_id=keyId,signing_domain=BundleSigning.Domain,signature_purpose="LOCAL_TEST_ONLY",cat_build_record_sha256=Hash(catRecord),gr_compiled_build=grIdentity.Build,component_versions_verified=true,
   distribution="CAT1_RANGE_ZIP_STORED_SERIAL",device_installable=installReady,signature_verified=false,preserve_user_data=true,
   installation_admission_sha256=admissionHash,
   installation_mode=firstTrial?"FIRST_CONTROLLED_TRIAL":(installReady?"PRODUCTION_ADMISSION":"OFFLINE_CANDIDATE"),installation_accepted=false,
   raw_kv_accepted=false,trial_review_sha256=trialReview,data_acceptance_scope=firstTrial?"READABLE_DATA_ONLY":"REQUIRED_DATA_EVIDENCE",
   gr_slot_bytes=GrSlot,gr_signature_reserve=SignatureBytes,cat_user_fs_total=CatFsTotal,cat_free_operator_input=freeBytes,reserve_bytes=Reserve,
   space_evidence_mode=freeBytes.HasValue?"OPERATOR_PROVIDED":"LAYOUT_PROFILE_ONLY",requires_device_space_check=true,
   gr_layout_contract_sha256=grLayoutHash,gr_data_contract_sha256=grDataHash,
   gr_layout_approved=installReady,cat_native_fota_partition_verified=installReady&&!firstTrial,cat_native_activation_reviewed=firstTrial,cat_package_partition_profile_verified=true,cat_core_required=Cat1Native.SocName,cat_actual_script_version=catInfo.Version,
   reason=firstTrial?"仅限"+from+"到"+to+"首次受控试验；安装与原始KV未验收":(installReady?"已绑定本次组件与底包准入证据；允许安装测试，不代表实板升级已验收":"本地签名候选；缺少安装准入证据，不可安装")};
  byte[] manifestBytes=Encoding.UTF8.GetBytes(Json.Serialize(manifest)),signature=BundleSigning.Sign(manifestBytes,keyDirectory);
  // SAM | 2026-10-29 08:16 +08:00 | User asked for short upload names such as YP001_1.0.2---1.5.1_FIRST.zip; without the random tag an existing package is never overwritten.
  Directory.CreateDirectory(output);string file=Path.Combine(output,(prefix.Length>0?prefix+"_":"")+upgrade+(suffix.Length>0?"_"+suffix:"")+".zip");
  if(File.Exists(file)||File.Exists(file+".failed"))throw new Exception("同名升级包已存在，拒绝覆盖："+Path.GetFileName(file));
  StoredZipWriter.Write(file,new[]{"bundle.json","GR5526/payload.bin","CAT1/payload.sota","CAT1/build.json","signature.json","signing_public.xml"},
   new[]{manifestBytes,grData,catData,catRecord,signature,Encoding.UTF8.GetBytes(publicXml)});
  using(ZipArchive zip=ZipFile.OpenRead(file)){
   if(Hash(Get(zip,"GR5526/payload.bin"))!=Hash(grData)||Hash(Get(zip,"CAT1/payload.sota"))!=Hash(catData)||Hash(Get(zip,"CAT1/build.json"))!=Hash(catRecord))throw new Exception("归档读回失败，不可上传");
  }
  // SAM | 2026-10-22 +08:00 | A failed final verification must not leave an apparently ready upgrade ZIP.
  try {BundleSigning.VerifyArchive(file,Path.Combine(keyDirectory,BundleSigning.PublicName));}
  catch {File.Move(file,file+".failed");throw;}
  return file;
 }
 static void Put(ZipArchive zip,string name,byte[] data){using(Stream s=zip.CreateEntry(name,CompressionLevel.NoCompression).Open())s.Write(data,0,data.Length);}
 static byte[] Get(ZipArchive zip,string name){using(Stream s=zip.GetEntry(name).Open())using(MemoryStream m=new MemoryStream()){s.CopyTo(m);return m.ToArray();}}
}}
