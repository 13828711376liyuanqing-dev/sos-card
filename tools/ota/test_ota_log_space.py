"""SAM | 2026-11-04 +08:00 | Long-term CAT1 space around an OTA: a new OTA command (accept / receive) deletes /log/app.log and
.bak first (only while IDLE; /log/ble.ini, the temporary BLE location cache, is cleared too), fs_log writes no log files while a job is in flight and resumes at IDLE.
Real update.lua and fs_log.lua with stubbed LuatOS services; host only."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'logs/cat1_antenna_20261010/python_deps'))
from lupa.lua53 import LuaRuntime

PRELUDE = r'''
package.path=root..'/Air780EGH/?.lua;'..package.path
files={['/log/app.log']=string.rep('a',9000),['/log/app.log.bak']=string.rep('b',16000),['/log/ble.ini']='keep'}
diag={};holds={};power_held=false
_G.uart_send_raw=function(s)
 holds[#holds+1]=s
 local on=s:match('^%[OTA_HOLD%] ([01])')
 if on then power_held=on=='1' end
 return true
end
phase='IDLE'
local inst={}
function inst:status() return {phase=phase} end
function inst:accept(c) accepted=c; phase='GR_GRANTED'; return true end
function inst:receive(t,c,m) received_on_hold=power_held;received=c; phase='GR_GRANTED'; return true end
package.loaded.ota_runtime={start=function() return inst end, instance=function() return inst end}
tasks={}
sys={taskInit=function(f) tasks[#tasks+1]=coroutine.create(f) end, wait=function() coroutine.yield() end,
  timerLoopStart=function(f) flush_timer=f end, subscribe=function() end}
uart={VUART_0=0,setup=function() end,write=function(_,s) diag[#diag+1]=s end}
mcu={ticks=function() return 0 end}
log={info=function() end,warn=function() end}
io.fileSize=function(p) return files[p] and #files[p] or nil end
io.dexist=function() return true end
io.open=function(p,mode) return {write=function(_,s) files[p]=(files[p] or '')..s; return true end, close=function() end} end
os.remove=function(p) local had=files[p]~=nil; files[p]=nil; return had end
os.rename=function(a,b) files[b]=files[a]; files[a]=nil; return true end
package.loaded.httpplus={}
_G.at_cmd_handlers={}
require('update')
require('fs_log')
function beacon() for _,t in ipairs(tasks) do coroutine.resume(t) end end
beacon() -- start the tasks up to their first sys.wait; each later beacon() is one 10 s beacon round
'''


def run(name, body):
    lua = LuaRuntime()
    lua.globals().root = ROOT.as_posix()
    lua.execute(PRELUDE + body)
    print('PASS', name)


if __name__ == '__main__':
    run('platform receive holds power before existing engine metadata work', r'''
require('ota_runtime').instance():receive('t',{y=2},{retain=false})
assert(received_on_hold==true,'platform metadata must start under the same hold as the active entry')
''')
    run('accept clears app logs and the BLE location cache, pauses log files during the job, resumes at IDLE', r'''
assert(not ota_log_paused())
assert(require('ota_runtime').instance():accept({x=1}) == true and accepted.x == 1)
assert(files['/log/app.log']==nil and files['/log/app.log.bak']==nil and files['/log/ble.ini']==nil)
local cleared; for _,s in ipairs(diag) do cleared = cleared or s:match('LOG_CLEARED (%d+)') end
assert(cleared == '25004', tostring(cleared))  -- app.log 9000 + .bak 16000 + ble.ini 4
assert(ota_log_paused())
log_write('I','T',string.rep('z',11000)); flush_timer()
assert(files['/log/app.log']==nil, 'no log file while OTA runs')
phase='IDLE'; beacon()
assert(not ota_log_paused())
log_write('I','T',string.rep('z',11000))
assert(files['/log/app.log'] and #files['/log/app.log']>11000, 'logging resumes')
''')
    run('platform otaMsg (receive) clears too; a command during a running job does not delete logs', r'''
assert(require('ota_runtime').instance():receive('t',{y=2},{retain=false}) == true and received.y == 2)
assert(files['/log/app.log']==nil)
files['/log/app.log']='new'
require('ota_runtime').instance():accept({x=3})
assert(files['/log/app.log']=='new', 'not IDLE: logs kept')
''')
