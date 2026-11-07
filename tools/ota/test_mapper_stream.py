"""SAM | 2026-10-24 +08:00 | Real signed sequential stream must survive mapper validation between committed chunks."""
import os,unittest
from pathlib import Path
import test_seq_zip
ROOT=Path(__file__).resolve().parents[2]
class MapperStreamTests(unittest.TestCase):
 def setUp(self):
  old=os.environ.get('YP_OTA_TEST_ARCHIVE');os.environ['YP_OTA_TEST_ARCHIVE']=str(ROOT/'OTA_Packager/output/1.0.2---1.5.0_R4.ypota.zip')
  try:self.f=test_seq_zip.SequentialTests();self.f.setUp()
  finally:
   if old is None:os.environ.pop('YP_OTA_TEST_ARCHIVE',None)
   else:os.environ['YP_OTA_TEST_ARCHIVE']=old
  self.lua=self.f.lua
  self.lua.execute(b'''
  transport_busy=false;blocked_probes=0;probes=0
  p.http_get=function()
   probes=probes+1
   if transport_busy then blocked_probes=blocked_probes+1;return nil,'HTTP_BUSY' end
   return {status=200}
  end
  local original=p.open_stream
  p.open_stream=function(url)
   if transport_busy then return nil,'HTTP_BUSY' end
   local s,e=original(url);if not s then return nil,e end
   transport_busy=true;local close=s.close
   s.close=function()transport_busy=false;return close()end
   return s
  end
  platform=require('ota_platform').bundle(p)
  command={Address=input.url,Md5=input.md5,CurrentVersion=fixture_source,TargetVersion=fixture_target}
  job=assert(platform.resolve(command))
  ''')
 def test_validation_does_not_reopen_active_component_stream(self):
  self.lua.execute(b'''
  reader=assert(S.open(p,input));assert(reader:preflight_step())
  local cp=assert(reader:component_port('GR5526',7,{size=function()return 0 end}))
  local before=probes
  for offset=0,12288,4096 do
   local reply=cp.http_get(input.url,{Range='bytes='..offset..'-'..(offset+4095)},4096)
   assert(#reply.body==4096 and transport_busy)
   local ok,why=platform.validate(job);assert(ok,why)
  end
  assert(probes==before and blocked_probes==0);reader:close()
  ''')
 def test_cached_metadata_does_not_bypass_changed_job_or_live_sequence(self):
  self.lua.execute(b'''
  local before=probes
  assert(platform.validate(job));assert(probes==before)
  job.size=job.size+1;assert(not platform.validate(job));job.size=job.size-1
  ''')
  self.f.f.done=True
  self.lua.execute(b"local ok,e=platform.validate(job);assert(not ok and e=='COMPONENT_SEQUENCE')")
 def test_business_pause_still_denies_cached_metadata(self):
  self.f.f.allowed=False
  self.lua.execute(b"local ok,e=platform.validate(job);assert(not ok and e=='BUSINESS_PAUSED')")
 def test_complete_component_across_validation_ticks_uses_one_stream(self):
  before=self.f.opens
  self.lua.execute(b'''
  reader=assert(S.open(p,input));assert(reader:preflight_step())
  cp=assert(reader:component_port('GR5526',7,{size=function()return 0 end}))
  local hash=p.hash_begin('SHA256')
  for offset=0,job.size-1,4096 do
   assert(platform.validate(job))
   local last=math.min(offset+4096,job.size)-1
   local reply=cp.http_get(input.url,{Range='bytes='..offset..'-'..last},last-offset+1)
   assert(p.hash_update(hash,reply.body))
  end
  assert(p.hash_finish(hash)==job.hash and not transport_busy and blocked_probes==0)
  reader:close()
  ''')
  self.assertEqual(self.f.opens-before,2) # one preflight and one component stream
 def test_disconnect_resumes_same_component_offset_without_parallel_stream(self):
  self.lua.execute(b'''
  reader=assert(S.open(p,input));assert(reader:preflight_step())
  cp=assert(reader:component_port('GR5526',7,{size=function()return 0 end}))
  assert(#cp.http_get(input.url,{Range='bytes=0-4095'},4096).body==4096)
  ''')
  self.f.fail=True
  self.lua.execute(b"assert(not pcall(cp.http_get,input.url,{Range='bytes=4096-8191'},4096));assert(not transport_busy)")
  self.f.fail=False
  self.lua.execute(b"assert(platform.validate(job));assert(#cp.http_get(input.url,{Range='bytes=4096-8191'},4096).body==4096);reader:close();assert(not transport_busy)")
 def test_changed_trust_key_does_not_reuse_cache(self):
  self.lua.execute(b"p.trusted_key_id=string.rep('0',64);assert(not platform.validate(job))")
 def test_restart_reauthenticates_and_current_version_cannot_be_cached(self):
  before=self.f.opens
  self.lua.execute(b"local fresh=require('ota_platform').bundle(p);assert(fresh.validate(job))")
  self.assertEqual(self.f.opens,before+1)
  self.lua.execute(b"p.current_version=function()return '1.5.0'end;local ok,e=platform.validate(job);assert(not ok and e=='SOURCE_VERSION_MISMATCH')")
if __name__=='__main__':unittest.main()

