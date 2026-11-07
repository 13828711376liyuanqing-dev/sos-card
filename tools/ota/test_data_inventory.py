"""SAM | 2026-10-23 +08:00 | Verify read-only evidence capture, never device preservation acceptance."""
from test_cat_manager import runtime
import hashlib

SETUP = r'''
local mod=require('ota_data_inventory')
local values={['/settings']='abc'}
local keys={a='secret',b={x=2,y=true}}
local writes=0;local closes=0;local calls=0
local api={}
api.lsdir=function(path,n,offset)
 if offset>0 then return true,{} end
 return true,{{name='settings',type=0,size=3}}
end
api.open=function(path,mode)
 assert(mode=='rb');local pos=0
 return {seek=function(_,how,n)if how=='end' then return #values[path] end;pos=n;return pos end,
 read=function(_,n)local s=values[path]:sub(pos+1,pos+n);pos=pos+#s;return s end,
 close=function()closes=closes+1;return true end}
end
local kv={status=function()return 100,4096,2 end,
 iter=function()return {n=0}end,next=function(it)it.n=it.n+1;return ({'a','b'})[it.n]end,
 get=function(k)return keys[k]end,
 init=function()writes=writes+1;error('must not initialize')end,
 set=function()writes=writes+1;error('must not write')end}
-- Test-only deterministic digest adapter; native SHA256 is a separate device gate.
local hash={hash_begin=function()return {s=''}end,
 hash_update=function(h,s)h.s=h.s..s;return true end,
 hash_finish=function(h)local n=0;for i=1,#h.s do n=(n*31+h.s:byte(i))%4294967296 end;return string.format('%064x',n)end}
local p={io=api,kv=kv,hash=hash,can_read=function()return true end,yield=function()calls=calls+1 end}
'''

def check(name, body):
    lua=runtime();lua.execute(SETUP+body);print('PASS',name)

check('complete stable inventory never asserts preservation', '''
local r=mod.capture(p);assert(r.complete and not r.data_ok and #r.files==1 and #r.kv==2)
assert(not json.encode(r):find('secret',1,true));assert(writes==0 and closes==2)
''')
check('uninitialized KV is unknown, not empty or auto initialized', '''
kv.status=function()return nil end
local r=mod.capture(p);assert(not r.complete and r.error=='KV_UNAVAILABLE' and writes==0)
''')
# SAM | 2026-10-24 +08:00 | Approved first OTA may compare readable files while explicitly leaving inaccessible KV unaccepted.
check('approved policy preserves file evidence and marks unavailable KV', '''
p.allow_unavailable_kv=true;kv.status=function()return nil end
local r=mod.capture(p)
assert(r.complete and r.scope=='root_files_kv_unverified' and r.kv_unverified==true)
assert(#r.files==1 and writes==0 and not r.data_ok)
''')
check('approved policy still validates readable KV and rejects failed file reads', '''
p.allow_unavailable_kv=true
local r=mod.capture(p);assert(r.complete and r.scope=='root_files_and_initialized_kv')
kv.get=function()return nil end
assert(not mod.capture(p).complete)
kv.status=function()return nil end
api.open=function()return nil end
assert(not mod.capture(p).complete and writes==0)
''')
# SAM | 2026-10-24 +08:00 | Native failures must identify a bounded operation, never expose exception text or user content.
check('native exceptions identify the failed read stage without leaking content', '''
api.lsdir=function()error('private file name and user content')end
local r=mod.capture(p)
assert(not r.complete and r.error=='READ_FAILED' and r.stage=='FILE_LIST')
assert(not json.encode(r):find('private',1,true) and writes==0)
''')
# SAM | 2026-10-24 +08:00 | Preserve an allowlisted reason even when the device runtime decorates Lua errors.
check('decorated idle denial is distinguishable from a native missing function', '''
local original=error
error=function(message,level)original('runtime:1: '..message,0)end
p.can_read=function()return false end
local r=mod.capture(p)
assert(r.error=='BUSY' and r.stage=='IDLE_CHECK' and not r.complete)
error=original
p.can_read=function()return missing_audit_guard()end
r=mod.capture(p)
assert(r.error=='READ_FAILED' and r.exception_kind=='CALL_FAILED' and r.stage=='IDLE_CHECK')
''')
check('file mutation between scans is rejected', '''
p.yield=function()values['/settings']='xyz' end
local r=mod.capture(p);assert(not r.complete and r.error=='SCAN_CHANGED')
''')
check('short reads and close failures fail closed', '''
api.open=function()return {seek=function(_,h,n)return h=='end' and 3 or n end,
 read=function()return '' end,close=function()closes=closes+1;return true end}end
local r=mod.capture(p);assert(not r.complete and r.error=='FILE_READ_FAILED' and closes==1)
''')
check('unsafe names, unknown directories and duplicate entries are rejected', '''
for _,e in ipairs({{name='../escape',type=0,size=3},{name='user',type=1,size=0}})do
 api.lsdir=function()return true,{e}end
 assert(not mod.capture(p).complete)
end
api.lsdir=function()return true,{{name='settings',type=0,size=3},{name='settings',type=0,size=3}}end
assert(not mod.capture(p).complete)
''')
check('KV count mismatch and non-finite values rejected', '''
kv.status=function()return 100,4096,3 end
assert(mod.capture(p).error=='KV_COUNT_CHANGED')
kv.status=function()return 100,4096,2 end;keys.a=0/0
assert(mod.capture(p).error=='KV_VALUE_UNSUPPORTED')
''')
check('activity interrupts without opening a file', '''
p.can_read=function()return false end
local r=mod.capture(p);assert(r.error=='BUSY' and closes==0 and writes==0)
''')
check('diagnostic command is explicit and cannot confirm an OTA', '''
local tasks,replies={},{}
sys={subscribe=function()end,taskInit=function(f)tasks[#tasks+1]=f end,wait=function()end}
local phase='IDLE'
package.loaded.ota_runtime={start=function()return {status=function()return {phase=phase}end}end}
package.loaded.ota_platform={default=function()return {idle=function()return true end}end}
mod.device_port=function(guard)p.can_read=guard;return p end
_G.at_cmd_handlers={};require('update');assert(#tasks==0)
local handler=_G.at_cmd_handlers.OTA_DATA_AUDIT;assert(type(handler)=='function')
handler('',function(s)replies[#replies+1]=s end);assert(#tasks==1);tasks[1]()
assert(replies[#replies]:find('"complete":true',1,true))
assert(replies[#replies]:find('"data_ok":false',1,true))
-- SAM | 2026-10-24 +08:00 | The UART response must retain the precise stage while suppressing native exception text.
api.lsdir=function()error('private data')end
handler('',function(s)replies[#replies+1]=s end);tasks[2]()
assert(replies[#replies]:find('"stage":"FILE_LIST"',1,true))
assert(not replies[#replies]:find('private',1,true))
phase='COMPLETE_PENDING';handler('',function(s)replies[#replies+1]=s end);tasks[3]()
assert(replies[#replies]:find('BUSY',1,true) and writes==0)
''')
check('close failures, cyclic KV and hash failures never become complete', '''
local oldopen=api.open
api.open=function(...)local f=oldopen(...);f.close=function()return nil end;return f end
assert(mod.capture(p).error=='FILE_READ_FAILED');api.open=oldopen
keys.a={};keys.a.self=keys.a;assert(mod.capture(p).error=='KV_VALUE_UNSUPPORTED')
keys.a='secret';hash.hash_finish=function()return nil end
assert(mod.capture(p).error=='HASH_FAILED')
''')
check('transaction excludes only owned OTA files and never yields during prebusiness scan', '''
local j={hash=string.rep('a',64)};local candidate=require('ota_candidates').path(j.hash)
local original_list=api.lsdir
api.lsdir=function(path,n,off)
 local ok,list=original_list(path,n,off)
 if off==0 then
  list[#list+1]={name='yp001_cat_fota_0',type=0,size=200}
  list[#list+1]={name=candidate:sub(2),type=0,size=200}
 end
 return ok,list
end
mod.device_port=function(guard)p.can_read=guard;return p end
local r=mod.transaction_snapshot(j,candidate,function()return true end,true)
assert(r and r.files==1 and calls==0)
assert(not mod.transaction_snapshot(j,'/settings',function()return true end,true))
''')

# Real host SHA256 checks the native-wrapper calling convention (update returns nil).
lua=runtime()
contexts={}
def begin(kind):
    assert kind=='SHA256'
    n=len(contexts)+1;contexts[n]=hashlib.sha256();return n
def update(n,s):
    contexts[n].update(s.encode('utf-8'))
lua.globals().hash_begin=begin
lua.globals().hash_update=update
lua.globals().hash_finish=lambda n:contexts[n].hexdigest()
lua.globals().expected=hashlib.sha256(b'abc').hexdigest()
lua.execute('''
crypto={hash_init=function(k)return hash_begin(k)end,
 hash_update=function(c,s)hash_update(c,s)end,hash_finish=function(c)return hash_finish(c)end}
local p=require('ota_data_inventory').device_port(function()return true end)
local c=p.hash.hash_begin('SHA256');assert(p.hash.hash_update(c,'abc'))
assert(p.hash.hash_finish(c)==expected)
''')
print('PASS native adapter uses SHA256 and supports nil-returning update')
