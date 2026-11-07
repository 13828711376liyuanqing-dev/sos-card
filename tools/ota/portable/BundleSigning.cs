// SAM | 2026-10-22 +08:00 | Local-test RSA signing covers exact manifest bytes and all payload hashes; trust is pinned outside the ZIP.
using System;using System.IO;using System.IO.Compression;using System.Text;using System.Security.Cryptography;using System.Collections.Generic;
namespace YpOta {
public static class BundleSigning {
 public const string Domain="YP001_BUNDLE_LOCAL_TEST_RSA_V1",Algorithm="RSA-2048-SHA256-PKCS1v1.5";
 public const string PrivateName="OTA_TEST_PRIVATE.key",PublicName="OTA_TEST_PUBLIC.xml";
 static readonly UTF8Encoding Utf8=new UTF8Encoding(false,true);
 static RSACryptoServiceProvider Rsa(){return new RSACryptoServiceProvider(2048,new CspParameters(24)){PersistKeyInCsp=false};}
 static void Need(bool value,string message){if(!value)throw new Exception(message);}
 static string ReadKey(string file){Need(File.Exists(file),"签名KEY不存在："+file+"；不会自动替换现有密钥");Need(new FileInfo(file).Length<=16384,"签名KEY文件超限");return File.ReadAllText(file,Utf8);}
 static void WriteNew(string file,string text){using(FileStream f=new FileStream(file,FileMode.CreateNew,FileAccess.Write)){byte[] b=Utf8.GetBytes(text);f.Write(b,0,b.Length);}}
 // SAM | 2026-10-30 14:36 +08:00 | Windows pick only the private key file; its public half is derived from it (same RSA2048 pair by construction).
 public static string PublicFromPrivateFile(string privateFile){var key=Rsa();try{key.FromXmlString(ReadKey(privateFile));Need(key.KeySize==2048&&!key.PublicOnly,"需要RSA2048私钥文件（.key）");return key.ToXmlString(false);}finally{key.Dispose();}}
 public static string DefaultDirectory {get{return Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"keys");}}
 public static string Initialize(string directory){
  Directory.CreateDirectory(directory);string privateFile=Path.Combine(directory,PrivateName),publicFile=Path.Combine(directory,PublicName);
  if(File.Exists(privateFile)||File.Exists(publicFile)){using(var key=LoadPrivate(directory))return Fingerprint(key.ToXmlString(false));}
  using(var key=Rsa()){string publicXml=key.ToXmlString(false);WriteNew(privateFile,key.ToXmlString(true));WriteNew(publicFile,publicXml);
   WriteNew(Path.Combine(directory,"public_key_sha256.txt"),Fingerprint(publicXml)+Environment.NewLine);return Fingerprint(publicXml);}
 }
 public static RSACryptoServiceProvider LoadPrivate(string directory){
  var key=Rsa();try{key.FromXmlString(ReadKey(Path.Combine(directory,PrivateName)));Need(key.KeySize==2048&&!key.PublicOnly,"需要RSA2048私钥");
   string trusted=ReadKey(Path.Combine(directory,PublicName));Need(Fingerprint(trusted)==Fingerprint(key.ToXmlString(false)),"私钥与固定公钥不匹配，拒绝签名");return key;
  }catch{key.Dispose();throw;}
 }
 public static string Fingerprint(string publicXml){using(var key=Rsa()){key.FromXmlString(publicXml);Need(key.KeySize==2048,"公钥必须RSA2048");return PackCore.Hash(Utf8.GetBytes(key.ToXmlString(false)));}}
 static byte[] Message(byte[] manifest){byte[] prefix=Utf8.GetBytes(Domain+"\0"),message=new byte[prefix.Length+manifest.Length];Buffer.BlockCopy(prefix,0,message,0,prefix.Length);Buffer.BlockCopy(manifest,0,message,prefix.Length,manifest.Length);return message;}
 public static byte[] Sign(byte[] manifest,string directory){using(var key=LoadPrivate(directory)){
  byte[] signature=key.SignData(Message(manifest),CryptoConfig.MapNameToOID("SHA256"));Need(key.VerifyData(Message(manifest),CryptoConfig.MapNameToOID("SHA256"),signature),"签名自检失败");
  return Utf8.GetBytes(PackCore.Json.Serialize(new{schema=1,domain=Domain,algorithm=Algorithm,key_id=Fingerprint(key.ToXmlString(false)),signature_base64=Convert.ToBase64String(signature)}));}}
 public static string VerifyManifest(byte[] manifest,byte[] descriptor,string trustedPublicXml){
  var info=PackCore.Json.Deserialize<Dictionary<string,object>>(Utf8.GetString(descriptor));
  Need(info.Count==5&&Convert.ToInt32(info["schema"])==1&&Convert.ToString(info["domain"])==Domain&&Convert.ToString(info["algorithm"])==Algorithm,"签名格式/域/算法错误");
  string id=Fingerprint(trustedPublicXml);Need(Convert.ToString(info["key_id"])==id,"签名公钥不是本地固定可信公钥");
  byte[] signature=Convert.FromBase64String(Convert.ToString(info["signature_base64"]));Need(signature.Length==256,"签名长度错误");
  using(var key=Rsa()){key.FromXmlString(trustedPublicXml);Need(key.VerifyData(Message(manifest),CryptoConfig.MapNameToOID("SHA256"),signature),"RSA签名验证失败，清单被修改或KEY不匹配");}return id;
 }
 public static byte[] ReadEntry(ZipArchive z,string name,int limit){ZipArchiveEntry e=z.GetEntry(name);Need(e!=null&&e.Length<=limit,"归档缺少必要文件或文件超限："+name);
  using(Stream s=e.Open())using(MemoryStream m=new MemoryStream()){byte[] b=new byte[8192];int n;while((n=s.Read(b,0,b.Length))>0){Need(m.Length+n<=limit,"归档解压超限");m.Write(b,0,n);}Need(m.Length==e.Length,"归档长度不一致");return m.ToArray();}}
 public static string VerifyArchive(string file,string trustedPublicFile){
  string trusted=ReadKey(trustedPublicFile);using(ZipArchive z=ZipFile.OpenRead(file)){
   var names=new HashSet<string>(StringComparer.Ordinal){"bundle.json","signature.json","signing_public.xml","GR5526/payload.bin","CAT1/payload.sota","CAT1/build.json"};
   Need(z.Entries.Count==names.Count,"签名归档文件数错误");foreach(var entry in z.Entries)Need(names.Remove(entry.FullName),"归档含重复或未签名的额外文件");
   byte[] manifest=ReadEntry(z,"bundle.json",65536);string id=VerifyManifest(manifest,ReadEntry(z,"signature.json",8192),trusted);
   Need(Fingerprint(Utf8.GetString(ReadEntry(z,"signing_public.xml",16384)))==id,"归档公钥与固定可信公钥不匹配");
   var doc=PackCore.Json.Deserialize<Dictionary<string,object>>(Utf8.GetString(manifest));Need(Convert.ToInt32(doc["schema"])==6&&Convert.ToString(doc["signing_key_id"])==id&&Convert.ToString(doc["signing_domain"])==Domain,"清单签名配置不一致");
   ValidateInstallationMode(doc);
   var items=doc["components"] as System.Collections.ArrayList;Need(items!=null&&items.Count==2,"组件数量错误");
   var targets=new HashSet<string>();foreach(var value in items){var item=(Dictionary<string,object>)value;string target=Convert.ToString(item["target"]);Need(targets.Add(target),"重复组件");string path=target=="GR5526"?"GR5526/payload.bin":target=="CAT1"?"CAT1/payload.sota":null;Need(path!=null&&Convert.ToString(item["path"])==path,"未知组件或路径");
    byte[] payload=ReadEntry(z,path,524288);Need(payload.Length==Convert.ToInt32(item["bytes"])&&PackCore.Hash(payload)==Convert.ToString(item["sha256"]),"签名清单与组件内容不一致："+target);
    // SAM | 2026-10-22 +08:00 | Authenticated version labels must still match the compiled GR identity and the controlled target.
    Need(FirmwareIdentity.Normalize(Convert.ToString(item["version"]))==FirmwareIdentity.Normalize(Convert.ToString(doc["target_version"])),"组件版本与目标不符");
    if(target=="GR5526"){GrIdentity gr=FirmwareIdentity.ReadGr(payload);Need(gr.Version==Convert.ToString(item["version"])&&gr.Build==Convert.ToInt32(doc["gr_compiled_build"]),"GR编译版本与签名清单不符");}
   }
   Need(PackCore.Hash(ReadEntry(z,"CAT1/build.json",1048576))==Convert.ToString(doc["cat_build_record_sha256"]),"CAT1生成记录与签名清单不符");return id;
  }
 }
 // SAM | 2026-10-24 20:00 +08:00 | Admit only the signed, explicitly unaccepted first-trial scope; ordinary local packages remain non-installable.
 internal static void ValidateInstallationMode(Dictionary<string,object> doc){
  Need(Convert.ToString(doc["product"])=="YP001"&&Convert.ToString(doc["signature_purpose"])=="LOCAL_TEST_ONLY","本地签名用途错误");
  if(!(bool)doc["device_installable"])return;
  Need(Convert.ToString(doc["installation_mode"])=="FIRST_CONTROLLED_TRIAL","本地验证包不能宣称正式安装权限");
  foreach(string k in new[]{"installation_accepted","raw_kv_accepted","cat_native_fota_partition_verified"})Need(doc.ContainsKey(k)&&doc[k] is bool&&!(bool)doc[k],"首次试验不能伪造验收："+k);
  foreach(string k in new[]{"preserve_user_data","cat_native_activation_reviewed","gr_layout_approved","component_versions_verified","cat_package_partition_profile_verified","requires_device_space_check"})Need(doc.ContainsKey(k)&&doc[k] is bool&&(bool)doc[k],"首次试验安全条件缺失："+k);
  // SAM | 2026-10-29 07:07 +08:00 | The signed range must be one of the fixed first-trial whitelist entries and match its upgrade label exactly.
  string trialFrom=Convert.ToString(doc["source_version"]),trialTo=Convert.ToString(doc["target_version"]);
  Need(PackCore.IsFirstTrialRange(trialFrom,trialTo)&&Convert.ToString(doc["upgrade"])==trialFrom+"---"+trialTo,"首次试验版本范围错误");
  Need(Convert.ToString(doc["data_acceptance_scope"])=="READABLE_DATA_ONLY"&&Convert.ToString(doc["cat_core_required"])==Cat1Native.SocName&&Convert.ToString(doc["distribution"])=="CAT1_RANGE_ZIP_STORED_SERIAL","首次试验范围或底包错误");
  foreach(string k in new[]{"trial_review_sha256","installation_admission_sha256"})Need(doc.ContainsKey(k)&&System.Text.RegularExpressions.Regex.IsMatch(Convert.ToString(doc[k]),"^[0-9a-f]{64}$")&&Convert.ToString(doc[k])!=new string('0',64),"首次试验审查绑定缺失："+k);
 }
}
}
