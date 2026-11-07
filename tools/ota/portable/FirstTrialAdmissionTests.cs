// SAM | 2026-10-24 +08:00 | First-trial authorization must bind artifacts without asserting production/whole-KV acceptance.
using System;using System.Collections.Generic;using YpOta;
class FirstTrialAdmissionTests {
 static Dictionary<string,object> Good(){return new Dictionary<string,object>{
  {"schema","YP001_FIRST_CONTROLLED_TRIAL_V1"},{"source_version","1.0.2"},{"target_version","1.5.0"},
  {"gr_payload_sha256",new string('a',64)},{"cat_package_sha256",new string('b',64)},{"cat_core_sha256",Cat1Native.SocHash},
  {"activation_review_completed",true},{"gr_boot_verified",true},{"readable_data_comparison_required",true},{"preserve_user_data",true},
  {"installation_accepted",false},{"raw_kv_accepted",false},{"review_sha256",new string('c',64)}};}
 static void Check(Dictionary<string,object> a){PackCore.ValidateFirstTrial(a,new string('a',64),new string('b',64));}
 static int Main(){try{
  Check(Good());int rejects=0;
  foreach(string key in new[]{"source_version","target_version","gr_payload_sha256","cat_package_sha256","cat_core_sha256","schema","review_sha256"}){
   var a=Good();a[key]="wrong";try{Check(a);}catch{rejects++;}
  }
  foreach(string key in new[]{"activation_review_completed","gr_boot_verified","readable_data_comparison_required","preserve_user_data","installation_accepted","raw_kv_accepted"}){
   var a=Good();a[key]=!(bool)a[key];try{Check(a);}catch{rejects++;}
  }
  if(rejects!=13)throw new Exception("First trial refused only "+rejects+" invalid records");
  // SAM | 2026-10-24 20:00 +08:00 | Reproduce archive-mode conflict and reject widened trial claims.
  var mode=new Dictionary<string,object>{{"product","YP001"},{"signature_purpose","LOCAL_TEST_ONLY"},{"device_installable",true},{"installation_mode","FIRST_CONTROLLED_TRIAL"},
   {"source_version","1.0.2"},{"target_version","1.5.0"},{"upgrade","1.0.2---1.5.0"},{"data_acceptance_scope","READABLE_DATA_ONLY"},
   {"cat_core_required",Cat1Native.SocName},{"distribution","CAT1_RANGE_ZIP_STORED_SERIAL"},{"trial_review_sha256",new string('c',64)},{"installation_admission_sha256",new string('d',64)}};
  foreach(string k in new[]{"installation_accepted","raw_kv_accepted","cat_native_fota_partition_verified"})mode[k]=false;
  foreach(string k in new[]{"preserve_user_data","cat_native_activation_reviewed","gr_layout_approved","component_versions_verified","cat_package_partition_profile_verified","requires_device_space_check"})mode[k]=true;
  BundleSigning.ValidateInstallationMode(mode);int modeRejects=0;
  foreach(string k in new System.Collections.Generic.List<string>(mode.Keys)){
   var bad=new Dictionary<string,object>(mode);if(k=="device_installable")continue;
   bad[k]=bad[k] is bool?(object)!(bool)bad[k]:(object)"wrong";
   try{BundleSigning.ValidateInstallationMode(bad);}catch{modeRejects++;}
  }
  if(modeRejects!=mode.Count-1)throw new Exception("Archive scope checks missing");
  // SAM | 2026-10-29 07:06 +08:00 | User-approved 1.0.2->1.5.1 joins the fixed first-trial whitelist; any other range or a cross-range record stays refused.
  var t151=Good();t151["target_version"]="1.5.1";PackCore.ValidateFirstTrial(t151,new string('a',64),new string('b',64),"1.0.2","1.5.1");int rangeRejects=0;
  try{PackCore.ValidateFirstTrial(t151,new string('a',64),new string('b',64),"1.0.2","1.5.0");}catch{rangeRejects++;}
  try{PackCore.ValidateFirstTrial(Good(),new string('a',64),new string('b',64),"1.0.2","1.5.1");}catch{rangeRejects++;}
  var t160=Good();t160["target_version"]="1.6.0";try{PackCore.ValidateFirstTrial(t160,new string('a',64),new string('b',64),"1.0.2","1.6.0");}catch{rangeRejects++;}
  var m151=new Dictionary<string,object>(mode);m151["target_version"]="1.5.1";m151["upgrade"]="1.0.2---1.5.1";BundleSigning.ValidateInstallationMode(m151);
  var m160=new Dictionary<string,object>(mode);m160["target_version"]="1.6.0";m160["upgrade"]="1.0.2---1.6.0";try{BundleSigning.ValidateInstallationMode(m160);}catch{rangeRejects++;}
  var mx=new Dictionary<string,object>(m151);mx["upgrade"]="1.0.2---1.5.0";try{BundleSigning.ValidateInstallationMode(mx);}catch{rangeRejects++;}
  // SAM | 2026-10-29 22:02 +08:00 | Round 2: 1.5.1->1.5.2 admitted; 1.0.2->1.5.2 and a 1.5.1 record bound to the wrong range stay refused.
  var t152=Good();t152["source_version"]="1.5.1";t152["target_version"]="1.5.2";PackCore.ValidateFirstTrial(t152,new string('a',64),new string('b',64),"1.5.1","1.5.2");
  try{PackCore.ValidateFirstTrial(t152,new string('a',64),new string('b',64),"1.0.2","1.5.2");}catch{rangeRejects++;}
  try{PackCore.ValidateFirstTrial(t151,new string('a',64),new string('b',64),"1.5.1","1.5.2");}catch{rangeRejects++;}
  var m152=new Dictionary<string,object>(mode);m152["source_version"]="1.5.1";m152["target_version"]="1.5.2";m152["upgrade"]="1.5.1---1.5.2";BundleSigning.ValidateInstallationMode(m152);
  var my=new Dictionary<string,object>(m152);my["upgrade"]="1.0.2---1.5.2";try{BundleSigning.ValidateInstallationMode(my);}catch{rangeRejects++;}
  if(rangeRejects!=8)throw new Exception("First trial range refused only "+rangeRejects+" of 8");
  var offline=new Dictionary<string,object>(mode);offline["device_installable"]=false;offline["installation_mode"]="OFFLINE_CANDIDATE";BundleSigning.ValidateInstallationMode(offline);
  Console.WriteLine("PASS first trial admission: 13 binding refusals, archive trial accepted, "+modeRejects+" scope refusals, 1.5.1 and 1.5.1->1.5.2 admitted, 8 range refusals, offline preserved");return 0;
 }catch(Exception e){Console.Error.WriteLine(e.Message);return 1;}}
}
