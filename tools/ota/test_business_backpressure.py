"""SAM | 2026-10-25 +08:00 | Execute the production emitter with a full UART queue."""
from pathlib import Path
import sys,os
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'logs/cat1_antenna_20261010/python_deps'))
from lupa.lua53 import LuaRuntime
source=R/'Air780EGH'
if os.environ.get('OTA_RELEASE_VARIANT'):source=R/'logs/uart_window_20261025/capacity_preview'/os.environ['OTA_RELEASE_VARIANT']/'source'
s=(source/'business_runtime.lua').read_text(encoding='utf-8-sig')
a=s.index('local uart_pending,');b=s.index('local service',a)
l=LuaRuntime();l.execute("sent={};blocked=true;json={encode=function(v)return v.op..':'..v.id end};sys={publish=function()end};uart_send_raw=function(s)if blocked then return false end;sent[#sent+1]=s;return true end")
l.execute(s[a:b]+"\n_G.test_emit=emit;_G.test_flush=flush_uart;_G.pending_count=function()return #uart_pending end")
l.execute("test_emit({op='alarm_ack',id=1});assert(business_uart_backlog());blocked=false;test_flush();assert(sent[1]=='BUS_EVT=alarm_ack:1' and not business_uart_backlog())")
l.execute("""
blocked=true;sent={}
for i=1,5000 do
 test_emit({op='signal',id=i});test_emit({op='network',id=i})
 test_emit({op='notice',id=i});test_emit({op='time',id=i})
end
test_emit({op='alarm_state',id=42});test_emit({op='alarm_ack',id=42})
test_emit({op='call',id=7});test_emit({op='hello',id=42})
assert(pending_count()==8,'telemetry pressure exhausted storage reserved for current critical states')
blocked=false;for i=1,8 do test_flush()end
assert(not business_uart_backlog(),'bounded snapshots did not drain')
local got={};for _,v in ipairs(sent)do got[v]=true end
assert(got['BUS_EVT=network:5000'] and got['BUS_EVT=alarm_state:42'] and got['BUS_EVT=alarm_ack:42'] and got['BUS_EVT=call:7'])
""")
print('PASS production business emitter retains and retries rejected UART event')
