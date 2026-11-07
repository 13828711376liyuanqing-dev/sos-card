"""SAM | 2026-10-24 +08:00 | Run actual resolver with explicit authenticated-reader observations; no network/device or crypto dependency."""
from test_cat_manager import runtime
lua=runtime()
lua.execute('''
local allowed=false;local completed=false;local completion_calls=0
package.loaded.ota_bundle={open=function()
 return {summary=function()return {device_installable=allowed,manifest_sha256=string.rep('d',64),source_version='1.0.2',target_version='1.5.0'}end,
 component=function(_,target)return {sha256=string.rep(target=='CAT1' and 'b' or 'a',64),md5=string.rep('c',32),size=100}end}
end}
local p={completed=function()completion_calls=completion_calls+1;return completed end,sha256=function()return string.rep('e',64)end}
local mapper=require('ota_platform').bundle(p,{})
local cmd={Address='http://test.invalid/update.zip',Md5=string.rep('c',32),CurrentVersion='1.0.2',TargetVersion='1.5.0'}
local job,why=mapper.resolve(cmd)
assert(job==nil and why=='BUNDLE_NOT_INSTALLABLE' and completion_calls==0)
allowed=true;job=assert(mapper.resolve(cmd));assert(job.target=='GR5526')
assert(mapper.validate(job,cmd));completed=true;job=assert(mapper.resolve(cmd));assert(job.target=='CAT1')
allowed=false;assert(mapper.resolve(cmd)==nil)
''')
print('PASS actual resolver: offline rejected before completion/ownership, eligible GR first, durable CAT second, revocation rejected')
