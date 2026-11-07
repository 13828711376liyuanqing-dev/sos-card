// SAM | 2026-10-24 +08:00 | Unknown device space can produce only an explicitly offline signed candidate; strict packaging remains fail-closed.
using System;using System.IO;using System.IO.Compression;using System.Collections.Generic;using System.Text;
namespace YpOta {class OfflineCandidateTests {
 static void Need(bool ok,string why){if(!ok)throw new Exception(why);}
 static void Reject(Action action,string why){bool rejected=false;try{action();}catch{rejected=true;}Need(rejected,why);}
 static int Main(string[] a){try{
  Need(a.Length==8,"Expected GR CAT OUTPUT FROM TO LUATOOLS KEYS CONTRACTS");
  string gr=a[0],cat=a[1],output=a[2],from=a[3],to=a[4],tools=a[5],keys=a[6],contracts=a[7];
  string privateFile=Path.Combine(keys,BundleSigning.PrivateName);string before=Cat1Native.FileHash(privateFile);
  Reject(()=>PackCore.Package(gr,cat,output,from,to,"YP001","STRICT_TEST",0,tools,keys,contracts),"Strict mode accepted unknown space");
  Reject(()=>PackCore.PackageOfflineCandidate(gr,cat,output,to,to,"YP001","OFFLINE_TEST",tools,keys,contracts),"Offline mode accepted same version");
  // An oversized file must fail capacity before native decoding; it is not an OTA fixture to be installed.
  string negative=Path.Combine(Environment.CurrentDirectory,"logs","ota_offline_package_20261024","negative_inputs_"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(negative);
  string oversized=Path.Combine(negative,"oversized.sota");File.WriteAllBytes(oversized,new byte[PackCore.CatFsTotal]);
  Reject(()=>PackCore.PackageOfflineCandidate(gr,oversized,output,from,to,"YP001","OFFLINE_TEST",tools,keys,contracts),"Offline mode bypassed CAT capacity");
  string archive=PackCore.PackageOfflineCandidate(gr,cat,output,from,to,"YP001","LOCAL_TEST_OFFLINE",tools,keys,contracts);
  using(var zip=ZipFile.OpenRead(archive)){
   var doc=PackCore.Json.Deserialize<Dictionary<string,object>>(Encoding.UTF8.GetString(BundleSigning.ReadEntry(zip,"bundle.json",65536)));
   Need(doc.ContainsKey("cat_free_operator_input")&&doc["cat_free_operator_input"]==null,"Unknown free space was fabricated");
   Need(Convert.ToString(doc["space_evidence_mode"])=="LAYOUT_PROFILE_ONLY","Offline mode not explicit");
   Need((bool)doc["requires_device_space_check"],"Runtime device space check not required");
   Need(!(bool)doc["device_installable"]&&Convert.ToString(doc["signature_purpose"])=="LOCAL_TEST_ONLY","Offline candidate claimed installation authority");
   Need(Convert.ToString(doc["source_version"])==from&&Convert.ToString(doc["target_version"])==to,"Version transition changed");
   Need(zip.Entries.Count==6,"ZIP profile changed");
  }
  string id=BundleSigning.VerifyArchive(archive,Path.Combine(keys,BundleSigning.PublicName));
  Need(Cat1Native.FileHash(privateFile)==before,"Existing private key changed");
  Console.WriteLine("PASS offline candidate capacity, unknown-space semantics, exact versions, pinned signature and key preservation");
  Console.WriteLine("OFFLINE_ARCHIVE="+archive);Console.WriteLine("KEY_ID="+id);return 0;
 }catch(Exception e){Console.Error.WriteLine("FAIL offline candidate: "+e.Message);return 1;}}
}}
