"""SAM | 2026-10-24 +08:00 | Reproduce the device loader without standard package.loaded, then bind existing service instances."""
from test_cat_manager import runtime

lua=runtime()
lua.execute('''
local platform=require('ota_platform')
local inventory=require('ota_data_inventory')
local original=package
package=nil
local p=platform.default()
assert(p.idle()==false and p.accept_topic('anything')==false)
local idle=true;local state={known=true,idle=true,alarm=false,network='mqtt',call='idle'}
local business={ota_status=function()state.idle=idle;return state end}
local mqtt={business_identity=function()return 'DEVICE_TEST'end}
assert(platform.bind_services(mqtt,business))
assert(p.idle()==true and p.business_status()==state)
-- SAM | 2026-10-24 +08:00 | Exercise the real inventory guard, not only a direct idle call, with read-only empty-FS/KV fixtures.
local audit=inventory.capture({can_read=p.idle,
 io={lsdir=function()return true,{}end},
 kv={status=function()return 0,4096,0 end,iter=function()return {}end,next=function()return nil end},
 hash={hash_begin=function()return {}end,hash_update=function()return true end,
 hash_finish=function()return string.rep('a',64)end}})
assert(audit.complete==true and audit.data_ok==false and #audit.files==0 and #audit.kv==0)
assert(p.accept_topic('/iotplat/render3/WARNCARD3/DEVICE_TEST/down_raw'))
idle=false;assert(p.idle()==false)
assert(p.safe()~=true and p.activate()~=true)
platform.bind_services(nil,nil)
assert(p.idle()==false and p.business_status()==nil)
package={}
assert(p.idle()==false and p.accept_topic('anything')==false)
package=original
''')
print('PASS no package/package.loaded: early deny, existing service binding, live idle checks, no install authority')
