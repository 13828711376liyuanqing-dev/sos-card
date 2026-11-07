# SAM | 2026-10-24 +08:00 | Fixtures use explicit installation evidence; legacy pending flags are rejected separately.
"""SAM | 2026-10-23 +08:00 | Test independent postboot health evidence; vendor/data fixtures are not module acceptance."""
from test_runtime import check
from test_default_native_path import SETUP as NATIVE_SETUP

SETUP = '''
local ms=0;local version='001.000.002';local busy=false;local code='VERIFIED';local phase='RECOVERY_HOLD'
local data=true;local stale=false;local badowner=false
local job={target='CAT1',id=string.rep('a',64),hash=string.rep('b',64),version='1.0.2',source='1.0.1',size=1234}
local function evidence(kind)
 local e={job=badowner and 'wrong' or job.id,hash=job.hash,epoch=1,version=job.version,observed_ms=stale and ms-3001 or ms}
 e[kind]=true;return e
end
local h=require('ota_health').new({now=function()return ms end,
 version=function()return version,'1.0.2',3 end,
 business=function()return {known=true,idle=not busy,alarm=busy,network='mqtt',call='idle'}end,
 code_identity=function()return code end,
 native_status=function()return {phase=phase,recovery_phase='REBOOTING',job=job,epoch=1,code_identity_required=true}end,
 data_evidence=function()if data then return evidence('data_ok')end end})
local function observe(first,last)for i=first,last,1000 do ms=i;h:check(job,1)end end
'''

check('health requires full observation and independent fresh data/vendor evidence', SETUP + '''
local v,why=h:check(job,1);assert(v==nil and why=='HEALTH_OBSERVING')
observe(1000,119000);assert(h:status().observed_ms==119000)
ms=120000;v=h:check(job,1);assert(v and v.healthy and v.installation_verified and v.data_ok and v.version=='1.0.2')
data=false;local _,why=h:check(job,1);assert(why=='DATA_EVIDENCE_UNAVAILABLE')
data=true;stale=true;local _,why=h:check(job,1);assert(why=='DATA_EVIDENCE_STALE')
stale=false;badowner=true;assert(h:check(job,1)==nil)
''')
check('health resets on activity, missing code, version mismatch and clock gaps', SETUP + '''
observe(0,120000);assert(h:check(job,1))
busy=true;assert(h:check(job,1)==nil);busy=false
assert(h:check(job,1)==nil and h:status().observed_ms==0)
observe(121000,240000);assert(h:check(job,1))
ms=244000;assert(h:check(job,1)==nil and h:status().observed_ms==0)
code='NOT_CHECKED';assert(h:check(job,1)==nil);code='VERIFIED'
version='001.000.003';local _,why=h:check(job,1);assert(why=='RUNNING_VERSION_MISMATCH')
version='001.000.002';phase='WRITING';local _,why=h:check(job,1);assert(why=='REBOOT_EVIDENCE_REQUIRED')
phase='RECOVERY_HOLD';ms=0;assert(h:check(job,1)==nil)
''')

check('default runtime recovers, observes health, then requires both evidence providers', NATIVE_SETUP + '''
assert(r:tick());assert(r:tick());assert(r:tick());assert(native_disk.phase=='COMMITTED')
native_disk.job.bundle={manifest_sha256=string.rep('d',64)}
native_disk.code_identity_required=true
native_disk.expected_identity={file_count=1,files={['main.luac']=string.rep('e',64)},version=j.version,
 package_sha256=j.hash,manifest_sha256=string.rep('d',64),build_record_sha256=string.rep('f',64),cat_proof=string.rep('ab',904)}
-- IO/identity responses are fixtures; production health, recovery and persistence execute unchanged.
np.code_identity=function()return true end
local data_ok=false
local function evidence(job,epoch,key)
 local v={job=job.id,hash=job.hash,epoch=epoch,version=job.version,observed_ms=clock};v[key]=true;return v
end
np.data_evidence=function(job,epoch)if data_ok then return evidence(job,epoch,'data_ok')end end
port.health_default=true
package.loaded.business_runtime={ota_status=function()return {known=true,idle=true,alarm=false,network='mqtt',call='idle'}end}
-- SAM | 2026-10-24 +08:00 | Explicit board-port fixture mirrors the production service binding, independent of Lua's optional package table.
port.business_status=package.loaded.business_runtime.ota_status
_G.VERSION='001.001.000';_G.PRODUCT_VERSION='1.1.0';_G.FW_RELEASE_BUILD=3
r=make();local _,why=r:tick();assert(why=='HEALTH_OBSERVING')
for i=1,120 do clock=clock+1000;r:tick()end
assert(r:status().native_health.reason=='DATA_EVIDENCE_UNAVAILABLE')
assert(native_disk.phase=='COMMITTED' and r:status().phase~='COMPLETE_PENDING')
r:pause();clock=clock+1000;local _,why=r:tick();assert(why=='HEALTH_OBSERVING','pause reused old observation')
for i=1,120 do clock=clock+1000;r:tick()end
local _,why=r:tick();assert(why=='DATA_EVIDENCE_UNAVAILABLE')
data_ok=true;assert(r:tick());assert(native_disk.phase=='CONFIRMED')
assert(r:status().phase=='COMPLETE_PENDING')
assert(initialized==1 and finished==1 and reboots==0)
-- SAM | 2026-10-23 +08:00 | Continue the same recovered transaction through proof/challenge/report/release/retirement; no second native init.
r=make()
local function result_frame(op,extra)
 local v={op=op,job=j.id,hash=j.hash,target='CAT1',version=j.version,epoch=1,reason='ok',phase='INSTALL_PENDING'}
 for k,x in pairs(extra or {})do v[k]=x end
 return 'OTA_GR='..json.encode(v)
end
for i=1,4 do
 r:tick();local frame=sent[#sent];assert(frame.op=='CAT_PROOF')
 assert(r:on_gr_line(result_frame('PROOF_ACK',{offset=frame.offset+#frame.data/2})))
end
assert(r:tick());assert(sent[#sent].op=='RESULT_QUERY')
assert(not r:on_gr_line(result_frame('RESULT_CHALLENGE',{nonce=string.rep('a',32),epoch=2})))
assert(r:on_gr_line(result_frame('RESULT_CHALLENGE',{nonce=string.rep('a',32)})))
local report=sent[#sent];assert(report.op=='CAT_RESULT' and report.proof==nil and report.durable_result and report.health_ms>=120000)
assert(#json.encode(report)<=1000)
assert(not r:on_gr_line(result_frame('RESULT_CHALLENGE',{nonce=string.rep('a',32)})))
assert(r:on_gr_line(result_frame('RESULT_ACK')));assert(sent[#sent].op=='COMPLETE')
assert(r:on_gr_line(result_frame('RELEASED',{phase='COMPLETE',outcome='success'})))
assert(r:status().phase=='IDLE');r:tick();assert(native_disk.phase=='IDLE')
assert(initialized==1 and finished==1 and reboots==0)
''')
