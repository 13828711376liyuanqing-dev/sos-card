"""SAM | 2026-11-05 +08:00 | Native HTTP waits must run in a task, not the MQTT callback."""
from test_http_range import HttpRangeTests

fixture = HttpRangeTests()
fixture.setUp()
fixture.lua.execute(r'''
-- Exercise the real HTTP client: the same yielding wait used by sys.wait.
deps.wait=function(ms)clock=clock+ms;coroutine.yield(ms)end
local r,e=get();assert(r==nil and e=='HTTP_PORT_ERROR','reproduce callback context failure')
cursor=1;tasks={};events={};diag={};calls=0
sys={publish=function(n)events[#events+1]=n end,
 taskInit=function(f)tasks[#tasks+1]=coroutine.create(f)end}
log={info=function()end,warn=function()end}
package.loaded.resident_name={}
package.loaded.ota_runtime={instance=function()return {receive=function()
 calls=calls+1
 local response,why=get()
 return response~=nil,why
end}end}
_G.ota_diag=function(s)diag[#diag+1]=s end
local receiver=require('mqtts_receiver')
receiver.proc('test/down',json.encode(command),{retain=false})
assert(calls==0 and #tasks==1,'MQTT callback must enqueue and return before native HTTP waits')
-- A second push while metadata is being accepted must not create unbounded tasks.
receiver.proc('test/down',json.encode(command),{retain=false})
assert(#tasks==1 and diag[1]=='[OTA_RX] REJECTED BUSY')
local turns=0
repeat
 local ok,why=coroutine.resume(tasks[1]);assert(ok,tostring(why));turns=turns+1
 assert(turns<500)
until coroutine.status(tasks[1])=='dead'
assert(calls==1 and turns>1 and diag[2]=='[OTA_RX] ACCEPTED')
receiver.proc('test/down',json.encode(command),{retain=false})
assert(#tasks==2,'pending flag must clear after completion')
''')
print('PASS real HTTP: callback reproduces HTTP_PORT_ERROR; task succeeds; pending queue stays bounded')
