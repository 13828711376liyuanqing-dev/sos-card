"""SAM | 2026-10-23 +08:00 | Exercise stop-and-wait with lost/stale replies, durable resume and explicit unbound refusal."""
from pathlib import Path
import sys
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'logs/cat1_antenna_20261010/python_deps'))
from lupa.lua53 import LuaRuntime
lua=LuaRuntime(unpack_returned_tuples=True)
lua.execute("package.path=.....'/Air780EGH/?.lua;'..package.path",R.as_posix())
lua.execute('''
local wire=require('ota_wire')
local module=require('ota_gr_transfer')
local clock,reads,writes,drop,closed,busy=0,0,0,false,false,false
local accepted,durable=0,0
local job={target='GR5526',id=string.rep('a',64),hash=string.rep('b',64),size=5000,version='1.5.0'}
local s
local function reply(f)
 local payload,kind
 if f.type==1 then
  kind=2;payload=string.pack('<I2I2I4I4I4',512,4096,442368,0,closed and 0 or 1)
 else
  kind=128
  if f.type==3 then accepted,durable=4096,4096
  elseif f.type==4 then
   assert(f.offset==accepted,'skipped or duplicate DATA delivered unexpectedly')
   assert(#f.payload==math.min(512,job.size-f.offset));accepted=accepted+#f.payload
   if accepted==job.size or accepted%4096==0 then durable=accepted end
  elseif f.type==6 then assert(durable==job.size) end
  payload=string.pack('<BBI2I4I4I4',f.type,0,f.type==6 and 3 or 1,accepted,durable,job.size)
 end
 return wire.decode(wire.encode(kind,f.session,f.sequence,f.offset,payload))
end
s=module.new({now=function()return clock end,idle=function()return not busy end,
 read=function(path,at,n)assert(path=='/ota_test');reads=reads+1;return string.rep('x',n)end,
 send=function(raw)
  writes=writes+1
  local f=assert(wire.decode(raw))
  if drop then return true end
  -- A matching reply may arrive synchronously before send returns.
  assert(s:on_frame(reply(f)));return true
 end})
assert(s:start(job,'/ota_test',7))
busy=true;assert(not s:step());assert(writes==0);busy=false
drop=true;s:step();assert(writes==1)
clock=1000;s:step();assert(writes==1)
clock=2000;s:step();assert(writes==2)
local fake=wire.decode(wire.encode(2,99,0,0,string.rep('x',16)));assert(not s:on_frame(fake))
drop=false;clock=4000;s:step();assert(writes==3)
for i=1,20 do s:step() end
assert(s:ready(job,7));assert(reads==2,'resume must use durable 4096 and read only remaining blocks')
assert(not s:ready(job,8));assert(not s:on_frame(fake))
local t=module.new({now=function()return clock end,idle=function()return true end,read=function()error('unexpected file read')end,
 send=function()return true end})
assert(t:start(job,'/ota_test',7))
clock=0;t:step();clock=2000;t:step();clock=4000;t:step();clock=6000
local ok,why=t:step();assert(not ok and why=='GR_UART_TIMEOUT');assert(t:status().attempts==3)
closed=true;assert(s:start(job,'/ota_test',8));s:step()
local ok,why=s:step();assert(not ok and why=='GR_PORT_UNBOUND');assert(not s:ready(job,8))
''')
print('PASS GR sender: early reply, loss/retry bound, stale reply, pause, durable resume, final verification and unbound refusal')
