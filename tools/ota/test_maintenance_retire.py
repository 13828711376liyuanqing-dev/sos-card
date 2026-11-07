# SAM | 2026-11-07 +08:00 | Offline maintenance retirement checks use the actual CRC journal and manager schema.
"""Narrow wired-maintenance retirement; no hardware, network, or user-file effects."""
from pathlib import Path
from test_cat_manager import ROOT, runtime

SETUP = """
package.path=root..'/tools/ota/maintenance/?.lua;'..package.path
retire=require('ota_maintenance_retire')
profile={tag='YP001_WIRED_RETIRE_E6_20261107',job_id=string.rep('b',64),hash=string.rep('c',64),
 epoch=6,source_version='1.5.12',target_version='1.5.13',reason='activation_validation_failed',baseline_version='1.5.13'}
command.CurrentVersion=profile.source_version;command.TargetVersion=profile.target_version
local resolve=port.resolve
port.resolve=function(c)local j=resolve(c);j.bundle={md5=c.Md5,manifest_sha256=string.rep('d',64)};return j end
OTA_TRIAL_MD5=command.Md5;OTA_TRIAL_TARGET=command.TargetVersion
m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING',6)))
assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED',6)));assert(m:request_activation())
local r=reply(m,'DENY','PREPARED',6);r.reason=profile.reason;assert(m:on_gr(r))
local state=m:status();state.io=nil;state.io_n=nil
state.failures[profile.hash]=2;state.failures[string.rep('f',64)]=1
state.retries[string.rep('e',64)]={count=2,next_retry=1234,permanent=true}
state.outbox[#state.outbox+1]={id=state.next_id,payload={MsgType='otaResultMsg',Status='fail',Version='1.5.0',Time=100}}
state.next_id=state.next_id+1;state.business_marker='preserve';assert(newstore():save(state))
fs['/resident_names.json']='resident sentinel';fs['/user_settings.json']='settings sentinel'
candidate_path=require('ota_candidates').path(profile.hash);fs[candidate_path]='candidate sentinel'
function native()return require('ota_native_store').new(disk,json)end
function run(version,time)return retire.run(newstore(),native(),json,profile,version or '1.5.13',time or 200)end
function saved()return newstore():load()end
function replace(s)assert(newstore():save(s))end
function unchanged(body)
 local before=json.encode(fs);local ok=body();assert(not ok);assert(json.encode(fs)==before,'refusal wrote data')
end
"""

CASES={
 'unrelated historical io budget is preserved without authorizing native install': """
 local base=saved()
 for _,v in ipairs({'ARMED','RUNNING','SPENT','FINISHED'})do
  local s=clone(base);s.io2={id=string.rep('8',64),n=3,v=v};replace(s)
  local before=json.encode(s.io2);assert(run());local after=saved()
  assert(after.phase=='IDLE' and json.encode(after.io2)==before)
  assert(newmanager():status().io==nil and newmanager():next_command()==nil)
 end
 local s=clone(base);s.io2={id=string.rep('8',64),n=1,v='FINISHED'};replace(s)
 assert(native().save({schema=1,phase='COMMITTING'}));unchanged(function()return run()end)
 """,
 'retirement preserves pending results quotas and user files': """
 local old=saved();local nold=json.encode(native():load())
 assert(run());local s=saved();assert(s.phase=='IDLE' and not s.job and not s.epoch and s.release)
 assert(s.reason=='WIRED_MAINTENANCE_RETIRED')
 assert(s.release.gr_finished and not s.release.gr_done and not s.release.gr_cleaned)
 assert(not s.release.cat_hash and not s.release.cat_finished and not s.release.cat_done and not s.release.cat_cleaned)
 for _,k in ipairs({'download','result','prepared_ack','io2','native_release','activation_retry'})do assert(s[k]==nil)end
 assert(s.trial.status=='SPENT' and json.encode(s.trial)==json.encode(old.trial))
 assert(s.failures[profile.hash]==3 and s.failures[string.rep('f',64)]==1)
 assert(json.encode(s.retries)==json.encode(old.retries) and s.business_marker=='preserve')
 assert(#s.outbox==#old.outbox+1 and s.next_id==old.next_id+1)
 for i,q in ipairs(old.outbox)do assert(json.encode(q)==json.encode(s.outbox[i]))end
 local q=s.outbox[#s.outbox];assert(q.id==old.next_id)
 assert(json.encode(q.payload)==json.encode({MsgType='otaResultMsg',Status='fail',Version='1.5.13',Time=200}))
 assert(s.cancelled.tag==profile.tag and s.cancelled.job_id==profile.job_id and s.cancelled.hash==profile.hash)
 assert(s.cancelled.reason=='wired_maintenance_retired' and s.cancelled.epoch==6)
 assert(not newmanager():status().error and newmanager():status().phase=='IDLE')
 assert(fs['/resident_names.json']=='resident sentinel' and fs['/user_settings.json']=='settings sentinel')
 assert(fs[candidate_path]=='candidate sentinel' and json.encode(native():load())==nold)
 """,
 'exact audit idempotency survives unrelated later job and active native': """
 assert(run());local s=saved();local count=#s.outbox
 m=newmanager();local c=m:pending_cleanup();assert(c.target=='GR5526' and c.hash==profile.hash)
 assert(m:next_command()==nil and not m:status().release.gr_done)
 assert(m:reserve_cleanup(c.target,c.hash));fs[candidate_path]=nil;assert(m:cleanup_done(c.target,c.hash))
 command.CurrentVersion='1.5.13';command.TargetVersion='1.5.14';command.Md5=string.rep('3',32)
 OTA_TRIAL_MD5=command.Md5;OTA_TRIAL_TARGET=command.TargetVersion
 local resolve=port.resolve;port.resolve=function(c)local j=resolve(c);j.id=string.rep('1',64);j.hash=string.rep('2',64);return j end
 m=newmanager();assert(m:accept(command));assert(m:status().phase=='WAIT_GR')
 assert(native().save({schema=1,phase='COMMITTING'}));local before=json.encode(fs)
 assert(retire.run(newstore(),native(),json,profile,'1.6.0',nil))
 assert(json.encode(fs)==before and #saved().outbox==count and saved().phase=='WAIT_GR')
 """,
 'scoped cleanup permits a newly frozen eligible trial without reviving old budget': """
 assert(run());m=newmanager();local c=m:pending_cleanup()
 assert(c and c.target=='GR5526' and c.hash==profile.hash and m:next_command()==nil)
 assert(fs[candidate_path]=='candidate sentinel' and saved().cancelled.reason=='wired_maintenance_retired')
 assert(not m:reserve_cleanup(c.target,string.rep('9',64)))
 assert(m:reserve_cleanup(c.target,c.hash));assert(saved().release.cleanup_target=='GR5526')
 fs[require('ota_candidates').path(c.hash)]=nil;assert(m:cleanup_done(c.target,c.hash))
 assert(m:pending_cleanup()==nil and m:next_command()==nil and not saved().release.gr_done)
 command.CurrentVersion='1.5.13';command.TargetVersion='1.5.14';command.Md5=string.rep('3',32)
 OTA_TRIAL_MD5=command.Md5;OTA_TRIAL_TARGET=command.TargetVersion
 local resolve=port.resolve;port.resolve=function(c)local j=resolve(c);j.id=string.rep('1',64);j.hash=string.rep('2',64);return j end
 m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING',7)))
 local s=m:status();assert(s.trial.status=='ARMED' and s.trial.hash==string.rep('2',64) and s.trial.epoch==7)
 assert(s.trial_prior.status=='SPENT' and s.trial_prior.hash==profile.hash and s.failures[profile.hash]==3)
 assert(m:prepare());assert(m:status().phase=='PREPARED')
 assert(fs['/resident_names.json']=='resident sentinel' and fs['/user_settings.json']=='settings sentinel')
 """,
 'missing release and mismatched release identity refuse': """
 local base=saved()
 local s=clone(base);s.job.bundle=nil;s.release=nil;replace(s);unchanged(function()return run()end)
 for _,key in ipairs({'gr_hash','CurrentVersion','TargetVersion'})do
  s=clone(base);s.job.bundle=nil
  if key=='gr_hash' then s.release.gr_hash=string.rep('9',64) else s.release.command[key]='1.5.99' end
  replace(s);unchanged(function()return run()end)
 end
 """,
 'wrong profile identity and baseline version refuse': """
 for _,key in ipairs({'job_id','hash','epoch','source_version','target_version','reason'})do
  local old=profile[key];profile[key]=key=='epoch' and 7 or string.rep('0',64)
  unchanged(function()return run()end);profile[key]=old
 end
 unchanged(function()return run('1.5.12')end)
 """,
 'wrong phase trial or component refuses': """
 local base=saved()
 for _,change in ipairs({{phase='PREPARED'},{phase='INSTALLING'},{reason='other'},
  {job_target='CAT1'},{trial_status='RUNNING'},{trial_hash=string.rep('4',64)}})do
  local s=clone(base)
  for k,v in pairs(change)do
   if k=='job_target' then s.job.target=v elseif k=='trial_status' then s.trial.status=v
   elseif k=='trial_hash' then s.trial.hash=v else s[k]=v end
  end
  replace(s);unchanged(function()return run()end)
 end
 """,
 'native active or unverifiable journals refuse': """
 for _,phase in ipairs({'INTENT','WRITING','COMMITTING','COMMITTED','REBOOTING','HOLD','RECOVERY_HOLD','unknown'})do
  assert(native().save({schema=1,phase=phase}));unchanged(function()return run()end)
 end
 unchanged(function()return retire.run(newstore(),{load=function()return nil,false end},json,profile,'1.5.13',200)end)
 """,
 'native idle and confirmed are preserved': """
 assert(native().save({schema=1,phase='IDLE'}));local before=json.encode(native():load());assert(run())
 assert(json.encode(native():load())==before)
 """,
 'native confirmed history is preserved': """
 assert(native().save({schema=1,phase='CONFIRMED',result={installation_verified=true,data_ok=true}}))
 local before=json.encode(native():load());assert(run());assert(json.encode(native():load())==before)
 """,
 'pending native result io or component progress refuse': """
 local base=saved()
 for _,change in ipairs({{native_release={job=base.job,epoch=6,version='1.5.13'}},
  {io2={id=base.job.id,n=0,v='SPENT'}},{gr_done=true},{cat_hash=string.rep('e',64)},
  {cat_started=true},{cat_finished=true}})do
  local s=clone(base)
  for k,v in pairs(change)do if k=='native_release' or k=='io2' then s[k]=v else s.release[k]=v end end
  replace(s);unchanged(function()return run()end)
 end
 """,
 'unknown clock and full outbox refuse': """
 for _,t in ipairs({0,-1,1.5,0x100000000})do unchanged(function()return run(nil,t)end)end
 unchanged(function()return retire.run(newstore(),native(),json,profile,'1.5.13',nil)end)
 local s=saved();while #s.outbox<8 do s.outbox[#s.outbox+1]={id=s.next_id,payload=clone(s.outbox[1].payload)};s.next_id=s.next_id+1 end
 replace(s);unchanged(function()return run()end)
 """,
 'readback failure refuses without touching current generation or user files': """
 local s=saved();local baseline=clone(fs)
 local bad={read=disk.read,write=function()return false end}
 local ok,why=retire.run(require('ota_store').new(bad,json),native(),json,profile,'1.5.13',200)
 assert(not ok and why=='STORE_COMMIT_FAILED');assert(json.encode(fs)==json.encode(baseline))
 assert(saved().phase=='RECOVERY_HOLD' and saved().trial.status=='SPENT')
 """,
 'crc corruption and invalid manager schema refuse': """
 local s=saved();s.failures='bad';replace(s);unchanged(function()return run()end)
 fs['/yp001_ota_state_0']='corrupt';unchanged(function()return run()end)
 """,
 'different audit identity never skips current checks': """
 assert(run());local s=saved();s.cancelled.hash=string.rep('5',64);replace(s)
 unchanged(function()return run()end)
 """,
 'unrelated existing audit is not overwritten': """
 local s=saved();s.cancelled={tag='another-maintenance',hash=string.rep('9',64)};replace(s)
 unchanged(function()return run()end)
 """,
 'torn alternate write fails closed while retaining previous generation': """
 local st=newstore();assert(st:load());local path=st.slot==1 and '/yp001_ota_state_0' or '/yp001_ota_state_1'
 local previous=fs[path];fail_write=true;local ok,why=run()
 assert(not ok and why=='STORE_COMMIT_FAILED' and fs[path]==previous)
 assert(fs['/resident_names.json']=='resident sentinel' and fs[candidate_path]=='candidate sentinel')
 local value,err=newstore():load();assert(value==nil and err=='STORE_CORRUPT')
 """,
 'malformed inactive native records refuse': """
 for _,n in ipairs({{schema=1,phase='IDLE',job={}},{schema=1,phase='IDLE',native_activation_possible=true},
  {schema=1,phase='CONFIRMED'},{schema=1,phase='CONFIRMED',recovery_phase='COMMITTING',result={installation_verified=true,data_ok=true}}})do
  assert(native().save(n));unchanged(function()return run()end)
 end
 """,
 'already maximum old hash failure quota is retained': """
 local s=saved();s.failures[profile.hash]=3;replace(s);assert(run());assert(saved().failures[profile.hash]==3)
 """,
}

if __name__=='__main__':
 module=ROOT/'tools/ota/maintenance/ota_maintenance_retire.lua'
 assert module.is_file(), 'maintenance retirement module is missing'
 failures=[]
 for name,body in CASES.items():
  try:
   runtime().execute(SETUP+body);print('PASS',name)
  except Exception as exc:
   failures.append(name);print('FAIL',name,exc)
 if failures: raise SystemExit(f'{len(failures)} maintenance checks failed')
