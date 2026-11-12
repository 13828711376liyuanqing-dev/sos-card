"""SAM | 2026-10-24 +08:00 | Bind data evidence to native intent and prebusiness boot, without restoring user bytes."""
from test_native_fota import check

SETUP = '''
job.source='1.0.2';port.require_data_identity=true
-- SAM | 2026-11-10 | production gate: the unverified-KV scope follows ota_trial (device identity + a real upgrade); `running` is the version the device runs now
running='1.0.2'
port.first_trial=require('ota_trial').new({core_sha256='29a3f2dc4eb07badc1093bf8b48f04fa54b40a6d537d1c0814dcfadf53693eec',evidence_sha256=string.rep('a',64)},
 function()return {model='Air780EGH',core='V2052',bits=64,fs_bytes=524288,version=running} end)
local digest=string.rep('b',64);local snapshots=0
port.data_snapshot=function(j,path,boot)
 snapshots=snapshots+1
 return {schema=1,complete=true,digest=digest,scope='root_files_and_initialized_kv',files=1,keys=0}
end
'''
# SAM | 2026-10-24 +08:00 | Scoped approval must survive commit/reboot and cannot silently turn into full KV acceptance.
check('scoped first OTA compares files and persists KV unaccepted', SETUP+'''
port.allow_unavailable_kv=true
port.data_snapshot=function()return {schema=1,complete=true,digest=digest,scope='root_files_kv_unverified',kv_unverified=true,files=1,keys=0}end
assert(f:start(job,'candidate',7));assert(f:step());assert(f:step());assert(f:step())
running=job.version   -- the install rebooted the device into the TARGET version: the data comparison must still work (11-10 board bug)
f=module.new(port);assert(f:observe_boot_data())
local e=f:data_evidence(job,7,100)
assert(e.data_ok and e.data_scope=='root_files_kv_unverified' and e.kv_acceptance=='UNVERIFIED')
assert(f:confirm(job,7,{job=job.id,hash=job.hash,epoch=7,version=job.version,healthy=true,installation_verified=true,data_ok=true}))
assert(disk.result.kv_acceptance=='UNVERIFIED' and disk.result.data_scope=='root_files_kv_unverified')
''')
check('strict policy rejects scoped baseline and scope changes fail boot comparison', SETUP+'''
port.data_snapshot=function()return {schema=1,complete=true,digest=digest,scope='root_files_kv_unverified',kv_unverified=true,files=1,keys=0}end
assert(not f:start(job,'candidate',7) and #calls==0)
port.allow_unavailable_kv=true;assert(f:start(job,'candidate',7))
assert(f:step());assert(f:step());assert(f:step())
port.data_snapshot=function()return {schema=1,complete=true,digest=digest,scope='root_files_and_initialized_kv',files=1,keys=0}end
f=module.new(port);assert(not f:observe_boot_data())
''')
# SAM | 2026-10-24 +08:00 | First-upgrade approval must not authorize unreadable KV for unrelated future releases.
# SAM | 2026-11-10 | Production gate: the scope is no longer one written-in release pair. It needs a real upgrade (target higher than source) and the device
# running either of the two; a source that is not the running version, a non-upgrade or a foreign running version is still refused.
check('scoped approval needs a real upgrade of the running version', SETUP+'''
port.allow_unavailable_kv=true
port.data_snapshot=function()return {schema=1,complete=true,digest=digest,scope='root_files_kv_unverified',kv_unverified=true,files=1,keys=0}end
job.source='1.0.1';assert(not f:start(job,'candidate',7) and #calls==0)            -- source is not what the device runs
job.source='1.0.2';job.version='1.0.2';assert(not f:start(job,'candidate',7) and #calls==0)   -- not an upgrade
job.version='1.0.1';assert(not f:start(job,'candidate',7) and #calls==0)            -- a downgrade
job.version='1.5.0';running='9.9.9';assert(not f:start(job,'candidate',7) and #calls==0)      -- the device runs a version that is neither source nor target
running='1.0.2';job.version='1.6.0';assert(f:start(job,'candidate',7))             -- any higher target of the running version is fine
''')
check('data baseline persists before native init and boot evidence survives lawful later writes', SETUP+'''
assert(f:start(job,'candidate',7));assert(disk.data_baseline.digest==digest)
assert(f:step());assert(f:step());assert(f:step());f=module.new(port)
assert(not f:data_evidence(job,7,100))
assert(f:observe_boot_data());local e=f:data_evidence(job,7,100);assert(e and e.data_ok)
digest=string.rep('c',64);assert(f:data_evidence(job,7,200).data_ok)
local n=snapshots;f=module.new(port);assert(f:observe_boot_data());assert(snapshots==n)
local info={job=job.id,hash=job.hash,epoch=7,version=job.version,healthy=true,installation_verified=true,data_ok=true}
assert(f:confirm(job,7,info));assert(disk.result.data_digest==disk.data_baseline.digest)
local n=snapshots;f=module.new(port);assert(f:observe_boot_data());assert(snapshots==n)
assert(f:data_evidence(job,7,300).data_ok)
''')
check('missing baseline blocks init and postboot mismatch cannot be supplied as true', SETUP+'''
port.data_snapshot=function()return nil end
assert(not f:start(job,'candidate',7));assert(#calls==0)
port.data_snapshot=function()return {schema=1,complete=true,digest=digest,scope='root_files_and_initialized_kv',files=1,keys=0}end
assert(f:start(job,'candidate',7));assert(f:step());assert(f:step());assert(f:step())
f=module.new(port);digest=string.rep('c',64);assert(not f:observe_boot_data())
local info={job=job.id,hash=job.hash,epoch=7,version=job.version,healthy=true,installation_verified=true,data_ok=true}
assert(not f:confirm(job,7,info));assert(not f:data_evidence(job,7,100))
''')
check('precommit change blocks finish rather than restoring or calling it data loss', SETUP+'''
assert(f:start(job,'candidate',7));assert(f:step());assert(f:step());digest=string.rep('c',64)
local ok,why=f:step();assert(not ok and why=='DATA_CHANGED_BEFORE_COMMIT')
for _,v in ipairs(calls)do assert(v~='finish_true')end
''')
check('boot receipt write failure and signed-code mismatch prevent evidence', SETUP+'''
assert(f:start(job,'candidate',7));assert(f:step());assert(f:step());assert(f:step())
f=module.new(port);fail_save=true;local ok,why=f:observe_boot_data()
assert(not ok and why=='DATA_BOOT_RECEIPT_FAILED');assert(not f:data_evidence(job,7,100))
fail_save=false;port.require_code_identity=true;f=module.new(port)
assert(not f:observe_boot_data());assert(not f:data_evidence(job,7,100))
''')

from test_runtime import check as runtime_check
from test_default_native_path import SETUP as RUNTIME_SETUP
configured=RUNTIME_SETUP.replace('local np={', '''local scans=0
local np={require_data_identity=true,data_snapshot=function(job,path,boot)
 scans=scans+1;return {schema=1,complete=true,digest=string.rep('b',64),scope='root_files_and_initialized_kv',files=1,keys=0}end,''')
runtime_check('default runtime uses its persisted data evidence without injected data_ok provider',configured+'''
assert(native_disk.data_baseline);assert(r:tick());assert(r:tick());assert(r:tick())
native_disk.code_identity_required=true
native_disk.job.bundle={manifest_sha256=string.rep('d',64)}
native_disk.expected_identity={file_count=1,files={['main.luac']=string.rep('e',64)},version=j.version,
 package_sha256=j.hash,manifest_sha256=string.rep('d',64),build_record_sha256=string.rep('f',64),cat_proof=string.rep('ab',904)}
np.code_identity=function()return true end
port.health_default=true
_G.VERSION='001.001.000';_G.PRODUCT_VERSION='1.1.0';_G.FW_RELEASE_BUILD=3
package.loaded.business_runtime={ota_status=function()return {known=true,idle=true,alarm=false,network='mqtt',call='idle'}end}
-- SAM | 2026-10-24 +08:00 | Health receives the same explicitly bound service callback as the real board.
port.business_status=package.loaded.business_runtime.ota_status
r=make();assert(r:observe_boot_data());assert(native_disk.boot_data_receipt)
r:tick();for n=1,120 do clock=clock+1000;r:tick()end
assert(native_disk.phase=='CONFIRMED' and r:status().phase=='COMPLETE_PENDING')
assert(native_disk.result.data_digest==native_disk.data_baseline.digest and initialized==1 and finished==1)
''')
