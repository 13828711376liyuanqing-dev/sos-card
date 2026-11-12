"""SAM | 2026-10-24 +08:00 | First trial admission is a narrow reviewed policy, never installation acceptance.
SAM | 2026-11-10 | Production gate: the source is the running version, the target only has to be higher (no written-in range or MD5)."""
from test_cat_manager import runtime

SETUP = '''
local mod=require('ota_trial')
local core='29a3f2dc4eb07badc1093bf8b48f04fa54b40a6d537d1c0814dcfadf53693eec'
local profile={core_sha256=core,evidence_sha256=string.rep('a',64)}   -- SAM | 2026-11-10 | no version range in the profile any more
local observed={model='Air780EGH',core='V2052',bits=64,fs_bytes=524288,version='1.0.2'}
local job={target='CAT1',source='1.0.2',version='1.5.0',hash=string.rep('b',64),size=250544,bundle={manifest_sha256=string.rep('c',64)}}
local id={package_sha256=job.hash,manifest_sha256=job.bundle.manifest_sha256,core_sha256=core,build_kind='SCRIPT_ONLY_SAME_CORE',user_data_ranges_in_payload=false}
local p=mod.new(profile,function()return observed end)
'''
def check(name,body):
    runtime().execute(SETUP+body)
    print('PASS',name)

check('exact reviewed first trial is accepted without native side effects', '''assert(p:network());assert(p:install(job,id))''')
check('no profile or missing live identity rejects', '''
assert(not mod.new(nil,function()return observed end):network())
observed=nil;assert(not p:network() and not p:install(job,id))
''')
check('different live core model width filesystem or source rejects', '''
for k,v in pairs({core='V2053',model='Air780EPM',bits=32,fs_bytes=1048576,version='1.0.1'})do
 local old=observed[k];observed[k]=v;assert(not p:install(job,id));observed[k]=old
end
''')
check('signed build must bind same core script-only and no user payload', '''
for k,v in pairs({core_sha256=string.rep('d',64),build_kind='CORE_AND_SCRIPT',user_data_ranges_in_payload=true,package_sha256=string.rep('d',64),manifest_sha256=string.rep('d',64)})do
 local old=id[k];id[k]=v;assert(not p:install(job,id));id[k]=old
end
id.user_data_ranges_in_payload=nil;assert(not p:install(job,id))
''')
check('any higher target is accepted; same, lower, malformed or foreign source targets reject', '''
for _,v in ipairs({'1.6.0','1.0.3','2.3.4','1.5.24'})do job.version=v;assert(p:install(job,id) and p:eligible(job),v)end
for _,v in ipairs({'1.0.2','1.0.1','0.9.9','1.5','x','1.5.0.1','1.5.1000',1})do job.version=v;assert(not p:install(job,id) and not p:eligible(job),tostring(v))end
job.version='1.5.0';job.source='1.0.1';assert(not p:install(job,id) and not p:eligible(job));job.source='1.0.2'
''')
check('data scope holds before and after the install reboot but not for a foreign running version', '''
-- before the reboot the device runs the source, after it the target (11-10 board: eligible() here left the install in RECOVERY_HOLD)
assert(p:scoped(job) and p:eligible(job))
observed.version=job.version;assert(p:scoped(job) and not p:eligible(job) and not p:install(job,id))
observed.version='9.9.9';assert(not p:scoped(job))
observed.version=job.source;job.version=job.source;assert(not p:scoped(job))
job.version='1.0.1';assert(not p:scoped(job))
observed.core='V2053';job.version='1.5.0';assert(not p:scoped(job))
''')
check('absent review record rejects', '''
profile.evidence_sha256=nil;assert(not mod.new(profile,function()return observed end):install(job,id))
''')
check('a later device keeps working without any profile edit (version follows the running firmware)', '''
observed.version='1.5.24';job.source='1.5.24';job.version='1.5.26';assert(p:install(job,id))
observed.version='1.5.26';job.source='1.5.26';job.version='1.5.27';assert(p:install(job,id))
job.version='1.5.26';assert(not p:install(job,id))
''')

# SAM | 2026-10-24 +08:00 | Exercise device option wiring; missing explicit profile must preserve closed production defaults.
check('device options wire an explicit matching profile only', '''
package.loaded.ota_platform={default=function()return {idle=function()return true end}end}
io.fsstat=function()return true,128,10,4096 end
hmeta={model=function()return 'Air780EGH'end};rtos={version=function()return 'V2052'end}
PRODUCT_VERSION='1.0.2'
local options=require('ota_device_options')
assert(not options.new().http_native.native_rx_limit_verified)
local opts=options.new(profile)
assert(opts.http_native.native_rx_limit_verified and opts.native_fota_port.first_trial:install(job,id))
assert(not opts.native_fota_port.native_contract_verified(job))
hmeta.model=function()return 'Air780EPM'end
assert(not opts.native_fota_port.first_trial:install(job,id))
''')
