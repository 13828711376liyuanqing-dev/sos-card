# SAM | 2026-11-07 +08:00 | Exercise a narrowly bound WAIT_GR recovery using the real CRC journal and manager.
"""Synthetic host checks only, with no device, network or real user-file access."""
from test_cat_manager import ROOT, runtime


SETUP = r'''
package.path=root..'/tools/ota/maintenance/?.lua;'..package.path
profile={tag='YP001_RESUME_21_22',job_id=string.rep('b',64),hash=string.rep('c',64),epoch=7,
 source_version='1.5.21',target_version='1.5.22',manifest_sha256=string.rep('d',64),
 package_md5='7ae230881a96cf438cdaf73f3878d0d2',size=382184}
command.CurrentVersion=profile.source_version;command.TargetVersion=profile.target_version;command.Md5=profile.package_md5
local resolve=port.resolve
port.resolve=function(c)local j=resolve(c);j.size=profile.size;j.bundle={md5=c.Md5,manifest_sha256=profile.manifest_sha256};return j end
old_trial={id=string.rep('1',64),hash=string.rep('2',64),epoch=6,md5=string.rep('3',32),status='RUNNING'}
local initial={schema=1,phase='IDLE',outbox={},next_id=1,failures={},retries={},trial=clone(old_trial)}
initial.trial_prior={id=string.rep('4',64),hash=string.rep('5',64),epoch=5,md5=string.rep('6',32),status='SPENT'}
assert(newstore():save(initial))
OTA_TRIAL_MD5=string.rep('0',32);OTA_TRIAL_TARGET=profile.target_version;OTA_TRIAL_SOURCE=profile.source_version
m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING',profile.epoch)))
-- SAM | 2026-11-10 | Production gate: the GRANT of a new job replaces the stale ticket, so the historical stuck state no longer arises by itself.
assert(m:status().trial and m:status().trial.id~=old_trial.id,'NEW_TICKET_REPLACES_STALE')
local s0=m:status();s0.trial=clone(old_trial);s0.trial.status='ARMED';assert(newstore():save(s0));m=newmanager();m:on_gr(reply(m,'STATUS','DOWNLOADING',profile.epoch))   -- recreate the old stuck ticket for the legacy resume tool
local ok,why=m:prepare();assert(not ok and why=='TRIAL_SCOPE','original mismatch must reproduce '..tostring(why)..' '..tostring(m:status().phase))
local s=m:status();s.trial=clone(old_trial);s.io=nil;s.io_n=nil;s.business_marker='keep'   -- the historical RUNNING ticket the resume tool was written for
s.failures[string.rep('7',64)]=3;s.retries[string.rep('8',64)]={count=2,next_retry=100,permanent=true}
assert(newstore():save(s))
fs['/resident_names.json']='resident sentinel';fs['/user_settings.json']='settings sentinel'
OTA_TRIAL_MD5=profile.package_md5
function native()return require('ota_native_store').new(disk,json)end
function saved()return newstore():load()end
function replace(s)assert(newstore():save(s))end
function run(version,now)return resume.run(newstore(),native(),json,profile,version or '1.5.21',now or 200)end
function unchanged(f)
 local before=json.encode(fs);local ok=f();assert(not ok,'unsafe case accepted');assert(json.encode(fs)==before,'refusal wrote filesystem')
end
'''

CASES = {
    'original GR replay creates the new ticket and preserves all unrelated state': r'''
local before=saved();local store=newstore();assert(store:load());local generation=store.generation
local native_before=json.encode(native():load());assert(run())
local s=saved();assert(s.phase=='WAIT_GR' and s.epoch==nil)
local expected=clone(before);expected.phase='WAIT_GR';expected.epoch=nil;expected.trial_scope_resume=s.trial_scope_resume
assert(json.encode(expected)==json.encode(s),'migration changed unrelated manager state')
local audit=s.trial_scope_resume;assert(audit.original_epoch==7 and audit.journal_generation==generation)
assert(json.encode(audit.original_trial)==json.encode(old_trial) and audit.applied_at==200)
assert(json.encode(audit.profile)==json.encode(profile))
assert(fs['/resident_names.json']=='resident sentinel' and fs['/user_settings.json']=='settings sentinel')
assert(json.encode(native():load())==native_before and activation==0)
m=newmanager();assert(not m:status().error and m:status().trial.status=='RUNNING')
assert(m:reconcile());assert(sent[#sent].op=='REQUEST' and sent[#sent].epoch==0 and sent[#sent].size==382184)
assert(m:on_gr(reply(m,'STATUS','DOWNLOADING',7)))
s=m:status();assert(s.phase=='GR_GRANTED' and s.epoch==7 and s.trial.status=='ARMED')
assert(s.trial.id==profile.job_id and s.trial.hash==profile.hash and s.trial.md5==profile.package_md5)
assert(json.encode(s.trial_scope_resume.original_trial)==json.encode(old_trial))
assert(s.trial_prior.status=='SPENT' and s.trial_prior.epoch==5,'older audit overwritten')
assert(m:prepare() and m:status().phase=='PREPARED' and activation==0)
''',
    'same audit stays idempotent after later unrelated progress': r'''
assert(run());local s=saved();s.phase='IDLE';s.job=nil;s.epoch=nil;s.release=nil
replace(s);assert(native().save({schema=1,phase='COMMITTING'}));local before=json.encode(fs)
assert(resume.run(newstore(),native(),json,profile,'9.9.9',nil));assert(json.encode(fs)==before)
''',
    'different or malformed profile never matches an existing audit': r'''
assert(run())
for _,key in ipairs({'tag','job_id','hash','epoch','source_version','target_version','manifest_sha256','package_md5','size'})do
 local old=profile[key]
 profile[key]=(key=='epoch' or key=='size') and old+1 or (key=='tag' and 'different' or string.rep('9',#old))
 unchanged(function()return run()end);profile[key]=old
end
profile.extra=true;unchanged(function()return run()end)
''',
    'wrong task identity or source refuses': r'''
local base=saved()
for _,key in ipairs({'id','hash','source','version','size','target','url'})do
 local s=clone(base);s.job[key]=key=='size' and 382185 or string.rep('9',32);replace(s)
 unchanged(function()return run()end)
end
replace(base);unchanged(function()return run('1.5.20')end)
''',
    'every other manager phase refuses': r'''
local base=saved()
for _,phase in ipairs({'IDLE','WAIT_GR','PREPARING','PAUSED','PREPARED','WAIT_ACTIVATE','ACTIVATION_ISSUED','INSTALLING','RECOVERY_HOLD','COMPLETE_PENDING','unknown'})do
 local s=clone(base);s.phase=phase;replace(s);unchanged(function()return run()end)
end
''',
    'spent armed matching or corrupt legacy ticket refuses': r'''
local base=saved()
for _,status in ipairs({'SPENT','ARMED','unknown'})do
 local s=clone(base);s.trial.status=status;replace(s);unchanged(function()return run()end)
end
local s=clone(base);s.trial.id=profile.job_id;s.trial.hash=profile.hash;s.trial.epoch=profile.epoch
replace(s);unchanged(function()return run()end)
s=clone(base);s.trial=nil;replace(s);unchanged(function()return run()end)
''',
    'any download result activation or install-only record refuses': r'''
local base=saved()
for _,key in ipairs({'download','result','activation_retry','prepared_ack','native_release'})do
 local s=clone(base);s[key]=key=='prepared_ack' and false or {};replace(s);unchanged(function()return run()end)
end
for _,value in ipairs({'ARMED','RUNNING','SPENT','FINISHED'})do
 local s=clone(base);s.io2={id=profile.job_id,n=0,v=value};replace(s);unchanged(function()return run()end)
end
''',
    'component progress and release mismatch refuse': r'''
local base=saved()
for _,key in ipairs({'gr_finished','gr_done','gr_cleaned','cat_finished','cat_done','cat_cleaned','cat_started','cat_hash','cleanup_target','archive_proof'})do
 local s=clone(base);s.release[key]=true;replace(s);unchanged(function()return run()end)
end
for _,key in ipairs({'manifest','gr_hash'})do
 local s=clone(base);s.release[key]=string.rep('9',64);replace(s);unchanged(function()return run()end)
end
''',
    'native installer must be provably idle': r'''
for _,phase in ipairs({'INTENT','WRITING','COMMITTING','COMMITTED','REBOOTING','CONFIRMED','HOLD','RECOVERY_HOLD'})do
 assert(native().save({schema=1,phase=phase}));unchanged(function()return run()end)
end
for _,field in ipairs({'job','path','epoch','result','recovery_phase','active','native_activation_possible'})do
 local n={schema=1,phase='IDLE'};n[field]=true;assert(native().save(n));unchanged(function()return run()end)
end
unchanged(function()return resume.run(newstore(),{load=function()return nil,false end},json,profile,'1.5.21',200)end)
''',
    'unrelated io history and proven idle native are untouched': r'''
local s=saved();s.io2={id=string.rep('9',64),n=3,v='SPENT'};replace(s)
assert(native().save({schema=1,phase='IDLE'}));local before=json.encode(s.io2);local nb=json.encode(native():load())
assert(run());assert(json.encode(saved().io2)==before and json.encode(native():load())==nb)
''',
    'clock full outbox and exhausted ids refuse': r'''
for _,now in ipairs({0,-1,1.5,0x100000000})do unchanged(function()return run(nil,now)end)end
unchanged(function()return resume.run(newstore(),native(),json,profile,'1.5.21',nil)end)
local base=saved();local s=clone(base)
while #s.outbox<8 do s.outbox[#s.outbox+1]={id=s.next_id,payload=clone(s.outbox[1].payload)};s.next_id=s.next_id+1 end
replace(s);unchanged(function()return run()end)
s=clone(base);s.next_id=0xffffffff;replace(s);unchanged(function()return run()end)
''',
    'receiver globals must be frozen to this exact range and package': r'''
for _,key in ipairs({'OTA_TRIAL_MD5','OTA_TRIAL_SOURCE','OTA_TRIAL_TARGET'})do
 local old=_G[key];_G[key]='wrong';unchanged(function()return run()end);_G[key]=old
end
''',
    'failed write leaves original journal and all user files intact': r'''
local before=json.encode(fs)
local bad={read=disk.read,write=function()return false end}
local ok,why=resume.run(require('ota_store').new(bad,json),native(),json,profile,'1.5.21',200)
assert(not ok and why=='STORE_COMMIT_FAILED' and json.encode(fs)==before)
assert(saved().phase=='GR_GRANTED' and saved().trial.status=='RUNNING')
''',
    'nested invocation refuses and outer migration commits once': r'''
local calls=0;local nested
local n={load=function()calls=calls+1;local ok,why=run();nested=why;assert(not ok);return nil,true end}
assert(resume.run(newstore(),n,json,profile,'1.5.21',200));assert(calls==1 and nested=='RESUME_BUSY')
''',
    'native read exception leaves files intact and releases the reentry guard': r'''
unchanged(function()return resume.run(newstore(),{load=function()error('read failed')end},json,profile,'1.5.21',200)end)
assert(run(),'exception left module busy')
''',
    'unexpected post-commit readback fails closed without another write': r'''
local base=newstore();local wrapped={};local reads,writes=0,0
wrapped.load=function(self)
 reads=reads+1;local value,err=base:load();self.generation=base.generation
 if reads==2 then value.business_marker='readback mismatch' end
 return value,err
end
wrapped.save=function(_,value)writes=writes+1;return base:save(value)end
local ok,why=resume.run(wrapped,native(),json,profile,'1.5.21',200)
assert(not ok and why=='RESUME_READBACK_FAILED' and writes==1)
assert(saved().phase=='WAIT_GR' and saved().business_marker=='keep')
assert(fs['/resident_names.json']=='resident sentinel' and fs['/user_settings.json']=='settings sentinel')
''',
    'torn alternate journal preserves the current record and fails closed': r'''
local store=newstore();assert(store:load())
local current=store.slot==1 and '/yp001_ota_state_0' or '/yp001_ota_state_1';local original=fs[current]
fail_write=true;local ok,why=run();assert(not ok and why=='STORE_COMMIT_FAILED')
assert(fs[current]==original and fs['/resident_names.json']=='resident sentinel')
local value,err=newstore():load();assert(value==nil and err=='STORE_CORRUPT')
''',
    'store corruption invalid schema and unrelated audit refuse': r'''
local base=saved();local s=clone(base);s.failures='bad';replace(s);unchanged(function()return run()end)
replace(base);s=saved();s.trial_scope_resume={profile={tag='unrelated'}};replace(s);unchanged(function()return run()end)
fs['/yp001_ota_state_0']='corrupt';unchanged(function()return run()end)
''',
}


if __name__ == '__main__':
    runtime().execute(SETUP)
    print('PASS original zero-MD5 legacy RUNNING ticket reproduces TRIAL_SCOPE')
    module = ROOT / 'tools/ota/maintenance/ota_trial_scope_resume.lua'
    assert module.is_file(), 'one-time WAIT_GR resume module is missing'
    failures = []
    for name, body in CASES.items():
        try:
            runtime().execute(SETUP + "resume=require('ota_trial_scope_resume')\n" + body)
            print('PASS', name)
        except Exception as exc:
            failures.append(name)
            print('FAIL', name, exc)
    if failures:
        raise SystemExit(f'{len(failures)} scope-resume checks failed')
