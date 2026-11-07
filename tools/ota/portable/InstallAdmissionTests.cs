// SAM | 2026-10-24 +08:00 | Test exact release binding and refusal of missing native/data evidence before signing an installable archive.
using System;using System.Collections.Generic;using YpOta;
class InstallAdmissionTests {
 static void Need(bool b){if(!b)throw new Exception("ASSERT");}
 static Dictionary<string,object> Good(){return new Dictionary<string,object>{
  {"schema",1},{"source_version","1.0.2"},{"target_version","1.5.0"},
  {"gr_payload_sha256",new string('a',64)},{"cat_package_sha256",new string('b',64)},
  {"cat_core_sha256",new string('c',64)},{"gr_boot_verified",true},
  {"gr_layout_verified",true},{"cat_native_activation_verified",true},
  {"cat_readonly_data_supported",true},{"preserve_user_data",true},
  {"evidence_set_sha256",new string('d',64)}};}
 static void Check(Dictionary<string,object> d){PackCore.ValidateInstallAdmission(d,"1.0.2","1.5.0",new string('a',64),new string('b',64),new string('c',64));}
 static int Main(){try{
  Check(Good());int rejected=0;
  foreach(string key in new[]{"gr_boot_verified","gr_layout_verified","cat_native_activation_verified","cat_readonly_data_supported","preserve_user_data"}){
   var d=Good();d[key]=false;try{Check(d);}catch{rejected++;}
  }
  foreach(string key in new[]{"source_version","target_version","gr_payload_sha256","cat_package_sha256","cat_core_sha256","evidence_set_sha256"}){
   var d=Good();d[key]="wrong";try{Check(d);}catch{rejected++;}
  }
  try{Check(null);}catch{rejected++;}Need(rejected==12);
  Console.WriteLine("PASS installation admission: exact source/target/payload/core and all evidence mandatory (12 refusals)");return 0;
 }catch(Exception e){Console.Error.WriteLine(e);return 1;}}
}
