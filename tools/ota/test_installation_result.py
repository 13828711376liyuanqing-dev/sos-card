"""SAM | 2026-10-24 +08:00 | Official postboot version plus signed identity replaces unavailable pending API."""
from test_cat_manager import runtime

lua=runtime()
lua.execute('''
local j={target='CAT1',id=string.rep('a',64),hash=string.rep('b',64),version='1.5.0',source='1.0.2',size=123}
local ms=0;local code='VERIFIED';local version='001.005.000';local phase='REBOOTING';local data=true
local h=require('ota_health').new({now=function()return ms end,
 version=function()return version,'1.5.0',4 end,
 native_status=function()return {phase='RECOVERY_HOLD',recovery_phase=phase,epoch=7,job=j,code_identity_required=true}end,
 code_identity=function()return code end,
 business=function()return {known=true,idle=true,alarm=false,network='mqtt',call='idle'}end,
 data_evidence=function()if data then return {job=j.id,hash=j.hash,epoch=7,version=j.version,observed_ms=ms,data_ok=true}end end})
for n=0,120000,1000 do ms=n;h:check(j,7)end
local r=h:check(j,7);assert(r and r.installation_verified==true and r.pending_clear==nil)
data=false;local _,why=h:check(j,7);assert(why=='DATA_EVIDENCE_UNAVAILABLE');data=true
code='NOT_CHECKED';assert(not h:check(j,7));code='VERIFIED'
version='001.000.002';assert(not h:check(j,7));version='001.005.000'
phase='INTENT';assert(not h:check(j,7))
''')
print('PASS postboot signed target confirmation needs no vendor pending API; data/code/version/commit gates remain')

from test_native_fota import SETUP
lua=runtime()
lua.execute(SETUP+'''
job.source='1.0.2';assert(f:start(job,'candidate',7))
assert(f:step());assert(f:step());assert(f:step());f=module.new(port)
local old={job=job.id,hash=job.hash,epoch=7,version=job.version,healthy=true,pending_clear=true,data_ok=true}
local ok,why=f:confirm(job,7,old);assert(not ok and why=='NOT_CONFIRMED')
disk.phase='CONFIRMED';disk.result=old;f=module.new(port)
assert(not f:completion_report(job,7))
assert(not f:retire({job=job,epoch=7,version=job.version}))
''')
print('PASS legacy pending_clear confirmation and persisted result cannot confirm, report or retire')
