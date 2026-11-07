"""SAM | 2026-10-28 10:20 +08:00 | Verify read-only rejection diagnostics because OTA send failures share one status."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'logs/cat1_antenna_20261010/python_deps'))
from lupa.lua53 import LuaRuntime
from test_uart_flash_window import runtime


def check_uart():
    for case in ('LOCKED', 'DFU', 'QUEUE'):
        lua = runtime()
        lua.globals().case = case
        lua.execute('''
logs={};log.warn=function(tag,value)logs[#logs+1]={tag,value}end
if case=='LOCKED' then partial=true;assert(ota_uart_send(frame));pump()
elseif case=='DFU' then dfu_transfer_active=true
else for i=1,64 do assert(uart_send_raw('normal')) end end
local result=uart_send_raw('OTA_CTL={}')
assert((case=='DFU' and result==nil) or (case~='DFU' and result==false),'RETURN_CHANGED')
assert(logs[#logs] and logs[#logs][1]=='OTA_DIAG' and logs[#logs][2]==case,'MISSING_CAUSE')
local count=#logs
for i=1,5 do uart_send_raw('OTA_CTL={}') end
assert(#logs==count,'REPEATED_REJECTION_LOG_FLOOD')
if case=='DFU' then
  dfu_transfer_active=false;assert(uart_send_raw('OTA_CTL={}'))
  dfu_transfer_active=true;uart_send_raw('OTA_CTL={}')
  assert(#logs==count+1 and logs[#logs][2]=='DFU','RECURRENT_REJECTION_NOT_RECORDED')
end
''')
    lua = runtime()
    lua.execute('''
logs={};log.warn=function(tag,reason) logs[#logs+1]={tag,reason} end
partial=true;assert(ota_uart_send(frame));pump()
assert(ota_uart_faulted() and #logs==1 and logs[1][1]=='OTA_DIAG' and logs[1][2]=='UART_PARTIAL_OR_FAILED','MISSING_FIRST_FAULT')
assert(not ota_uart_send(frame))
''')
    lua = runtime()
    lua.execute('''
log.warn=function()error('logger failure')end
partial=true;assert(ota_uart_send(frame));pump();assert(ota_uart_faulted())
local seen=false;for _,v in ipairs(events)do if v[1]=='OTA_UART_FAULT' and v[2]=='UART_PARTIAL_OR_FAILED' then seen=true end end
assert(seen,'LOGGER_BROKE_FAULT_PROPAGATION')
''')
    lua = runtime()
    lua.execute('''
log=nil;partial=true;assert(ota_uart_send(frame));pump();assert(ota_uart_faulted())
assert(not uart_send_raw('OTA_CTL={}'),'MISSING_LOG_CHANGED_REJECTION')
local seen=false;for _,v in ipairs(events)do if v[1]=='OTA_UART_FAULT' then seen=true end end
assert(seen,'MISSING_LOG_BROKE_FAULT_PROPAGATION')
''')


def check_platform():
    source = Path(os.environ.get('OTA_SOURCE_DIR', str(ROOT / 'Air780EGH')))
    for case in ('NO_SENDER', 'JSON_NIL', 'JSON_ERROR', 'JSON_LONG', 'SUCCESS'):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().case = case
        lua.execute('''
logs={};log={warn=function(tag,r)logs[#logs+1]={tag,r}end}
json={encode=function(m)if case=='JSON_ERROR' then error('hidden') elseif case=='JSON_NIL' then return nil elseif case=='JSON_LONG' then return string.rep('x',1001) end;return '{}' end}
uart_send_raw=case~='NO_SENDER' and function(s)assert(s=='OTA_CTL={}');return true end or nil
''')
        lua.globals().p = lua.execute((source / 'ota_platform.lua').read_text(encoding='utf-8-sig'))
        lua.execute('''
local port=p.default();local ok=port.send_gr({op='QUERY'})
if case=='SUCCESS' then assert(ok and #logs==0)
else
  assert(not ok and #logs==1 and logs[1][1]=='OTA_DIAG','MISSING_CAUSE');assert(logs[1][2]==(case=='NO_SENDER' and 'NO_SENDER' or 'JSON'))
  port.send_gr({op='QUERY'});assert(#logs==1,'PLATFORM_REJECTION_LOG_FLOOD')
end
''')


if __name__ == '__main__':
    check_uart()
    check_platform()
    print('PASS CAT1 query rejection and first-fault diagnostics; host only')
