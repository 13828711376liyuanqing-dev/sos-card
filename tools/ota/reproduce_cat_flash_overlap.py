"""SAM | 2026-10-25 +08:00 | Demonstrate actual CAT queue sends business bytes after a sector-ending DATA frame without awaiting its ACK; host scheduling evidence only."""
from pathlib import Path
import sys,json
r=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(r/'logs/cat1_antenna_20261010/python_deps'))
from lupa.lua53 import LuaRuntime
l=LuaRuntime(unpack_returned_tuples=True)
l.execute("package.path=.....'/Air780EGH/?.lua;'..package.path",r.as_posix())
l.execute('''
tasks={};written={};clock=0;after_sector_frame=0;sector_queued=false
log={info=function()end,warn=function()end,error=function()end}
mcu={ticks=function()return clock end}
sys={taskInit=function(f)tasks[#tasks+1]=coroutine.create(f)end,wait=function()coroutine.yield()end,
 subscribe=function()end,publish=function()end}
uart={setup=function()end,on=function()end,read=function()return nil end,
 write=function(_,s)
  local f=require('ota_wire').decode(s)
  if sector_queued then after_sector_frame=after_sector_frame+#s end
  if f and f.type==4 and f.offset==3584 then sector_queued=true end
  written[#written+1]=s;return #s
 end}
package.preload.exgnss=function()return{}end
package.preload.dfu_transfer=function()return{is_binary_mode=function()return false end}end
at_cmd_handlers={}
''')
l.execute((r/'Air780EGH/uart_app.lua').read_text(encoding='utf-8-sig'))
l.execute('''
local w=require('ota_wire')
assert(ota_uart_send(w.encode(4,2,7,3584,string.rep('x',512))))
assert(uart_send_raw('BUS_EVT={"op":"signal","value":20}'))
for _,t in ipairs(tasks)do assert(coroutine.resume(t))end
assert(sector_queued and #written==2 and after_sector_frame>0)
''')
report=dict(production_queue_overlap_reproduced=True,
 business_bytes_queued_after_sector_frame_without_ack=int(l.globals().after_sector_frame),
 physical_flash_duration_simulated=False,seventh_collision_proven=False,device_written=False)
d=r/'logs/uart_completed_abort_fix_20261025';d.mkdir(exist_ok=True)
(d/'cat_flash_overlap.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
