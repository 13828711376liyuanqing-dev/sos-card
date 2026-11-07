"""SAM | 2026-11-04 +08:00 | Bench command cat_at OTA_GR_CANCEL_EMPTY (update.lua): only while this CAT1 is IDLE; QUERY GR, and
only for a GR5526 DOWNLOADING owner echo GR's exact identity in CANCEL_EMPTY; GR's reply is reported, other GR states
send nothing more. GR alone proves emptiness (not simulated here). Real update.lua with stubbed services; host only."""
import json
from test_ota_log_space import ROOT, PRELUDE
from lupa.lua53 import LuaRuntime

GR = PRELUDE.replace("require('update')", r'''
frames={}
gr_state={op='STATUS',reason='ok',job=string.rep('a',64),hash=string.rep('b',64),target='GR5526',version='1.5.10',
  outcome='',epoch=3,phase='DOWNLOADING'}
gr_cancel={op='CANCELLED',reason='cancelled_before_install',phase='COMPLETE'}
pending={}
_G.uart_send_raw=function(s)
  frames[#frames+1]=s
  if s:sub(1,8)=='OTA_CTL=' then
    local m=json.decode(s:sub(9))
    if m.op=='QUERY' and gr_state then pending[#pending+1]='OTA_GR='..json.encode(gr_state) end
    if m.op=='CANCEL_EMPTY' and gr_cancel then pending[#pending+1]='OTA_GR='..json.encode(gr_cancel) end
  end
  return true
end
require('update')''').replace("function beacon()", r'''
function run_cmd()
  replies={}
  _G.at_cmd_handlers.OTA_GR_CANCEL_EMPTY('OTA_GR_CANCEL_EMPTY',function(s) replies[#replies+1]=s end)
  for _=1,200 do
    for _,line in ipairs(pending) do _G.at_cmd_handlers.OTA_GR(line) end
    pending={}
    for i=#tasks,1,-1 do if coroutine.status(tasks[i])~='dead' then coroutine.resume(tasks[i]) end end
    if #replies>0 then break end
  end
  return replies[1]
end
function ctl()local out={} for _,s in ipairs(frames) do if s:sub(1,8)=='OTA_CTL=' then out[#out+1]=json.decode(s:sub(9)) end end return out end
function beacon()''')


def run(name, body):
    lua = LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()
    g.root = ROOT.as_posix()
    g.py_encode = lambda t: json.dumps({k: t[k] for k in t}, separators=(',', ':'))
    g.py_decode = lambda s: lua.table_from(json.loads(s))
    lua.execute("json={encode=function(t)return py_encode(t)end,decode=function(s)return py_decode(s)end}\n" + GR + body)
    print('PASS', name)


if __name__ == '__main__':
    run('IDLE CAT1 + GR5526 DOWNLOADING owner: exact identity echoed in CANCEL_EMPTY, GR receipt reported', r'''
local r=run_cmd()
assert(r=='OTA_GR_CANCEL_EMPTY=CANCELLED cancelled_before_install COMPLETE',tostring(r))
local c=ctl();assert(#c==2 and c[1].op=='QUERY' and c[2].op=='CANCEL_EMPTY')
assert(c[2].job==string.rep('a',64) and c[2].hash==string.rep('b',64) and c[2].target=='GR5526' and c[2].version=='1.5.10' and c[2].epoch==3)
''')
    run('GR denial is reported as is', r'''
gr_cancel={op='DENY',reason='cancel_not_empty_or_safe',phase='DOWNLOADING'}
assert(run_cmd()=='OTA_GR_CANCEL_EMPTY=DENY cancel_not_empty_or_safe DOWNLOADING')
''')
    run('nothing to cancel: GR COMPLETE or a CAT1 owner -> only QUERY is sent', r'''
gr_state.phase='COMPLETE'
assert(run_cmd()=='OTA_GR_CANCEL_EMPTY=NOT_NEEDED COMPLETE GR5526');assert(#ctl()==1)
gr_state.phase='DOWNLOADING';gr_state.target='CAT1'
assert(run_cmd()=='OTA_GR_CANCEL_EMPTY=NOT_NEEDED DOWNLOADING CAT1');assert(#ctl()==2)
''')
    run('CAT1 with a job in flight refuses and sends nothing; no GR reply -> NO_STATUS', r'''
phase='PAUSED'
assert(run_cmd()=='OTA_GR_CANCEL_EMPTY=REFUSED PAUSED');assert(#frames==0 or #ctl()==0)
phase='IDLE';gr_state=nil
assert(run_cmd()=='OTA_GR_CANCEL_EMPTY=NO_STATUS')
''')
