"""SAM | 2026-10-23 +08:00 | Exercise production CAT UART binary/text routing with host-only device stubs."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'logs/cat1_antenna_20261010/python_deps'))
from lupa.lua53 import LuaRuntime
lua=LuaRuntime(unpack_returned_tuples=True)
lua.execute("package.path=.....'/Air780EGH/?.lua;'..package.path",ROOT.as_posix())
lua.execute('''
tasks={};incoming={};written={};frames={};calls=0;clock=0
log={info=function()end,warn=function()end,error=function()end}
mcu={ticks=function()return clock end}
sys={taskInit=function(f) tasks[#tasks+1]=coroutine.create(f) end,
 wait=function() coroutine.yield() end,subscribe=function()end,
 publish=function(event,f) if event=='OTA2_FRAME' then frames[#frames+1]=f end end}
uart={setup=function()end,on=function(_,_,f)receive=f end,
 read=function()return table.remove(incoming,1)end,
 write=function(_,s)written[#written+1]=s;return #s end}
package.preload.exgnss=function()return{}end
package.preload.dfu_transfer=function()return{is_binary_mode=function()return false end}end
at_cmd_handlers={PING=function()calls=calls+1 end}
function feed(s) incoming[#incoming+1]=s;receive()end
''')
lua.execute((ROOT/'Air780EGH/uart_app.lua').read_text(encoding='utf-8-sig'))
lua.execute('''
local w=require('ota_wire')
local p=w.encode(4,7,9,0,'\\0\\r\\nPING\\r\\n')
assert(type(ota_uart_send)=='function','production binary sender absent')
assert(ota_uart_send(p));assert(uart_send_raw('PING'))
for _,t in ipairs(tasks) do assert(coroutine.resume(t)) end
assert(written[1]==p,'binary bytes changed');assert(written[2]=='PING\\r\\n')
for i=1,#p do feed(p:sub(i,i)) end
assert(#frames==1 and frames[1].payload=='\\0\\r\\nPING\\r\\n' and calls==0)
feed('PING\\r\\n'..p..'PING\\r\\n');assert(calls==2 and #frames==2)
assert(not ota_uart_send('bad'));assert(not ota_uart_send(p:sub(1,-2)..'x'))
dfu_transfer_active=true;assert(not ota_uart_send(p));dfu_transfer_active=false
-- Partial binary timeout must quarantine through a boundary, never execute payload text.
feed(p:sub(1,10));clock=3001;feed('PING\\r\\n');assert(calls==2)
feed('PING\\r\\n');assert(calls==3)
-- Prefix shared with text protocol remains text; unrelated text is not swallowed.
local ctl=0;at_cmd_handlers.OTA_CTL=function()ctl=ctl+1 end
feed('OTA_CTL={}\\r\\n');assert(ctl==1)
-- Binary queue is bounded independently so business retains queue capacity.
for i=1,4 do assert(ota_uart_send(p)) end
assert(not ota_uart_send(p));assert(uart_send_raw('PING'))
assert(ota_uart_cancel())
for _,t in ipairs(tasks) do assert(coroutine.resume(t)) end
assert(written[#written]=='PING\\r\\n' and #written==3,'pause dropped business text or retained binary queue')
''')
print('PASS production CAT UART: exact binary TX, mixed/fragmented RX, timeout quarantine, CRC, DFU exclusion, bounded queue')
