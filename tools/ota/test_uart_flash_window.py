"""SAM | 2026-10-25 +08:00 | Exercise the real CAT UART writer with delayed device callbacks; no device access."""
from pathlib import Path
import sys,os
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'logs/cat1_antenna_20261010/python_deps'))
from lupa.lua53 import LuaRuntime

def runtime():
    l=LuaRuntime(unpack_returned_tuples=True)
    l.execute("package.path=.....'/Air780EGH/?.lua;'..package.path",ROOT.as_posix())
    l.execute('''
tasks={};incoming={};written={};callbacks={};events={};clock=0;idle=true
log={info=function()end,warn=function()end,error=function()end}
mcu={ticks=function()return clock end}
sys={taskInit=function(f)tasks[#tasks+1]=coroutine.create(f)end,wait=function()coroutine.yield()end,
 subscribe=function()end,publish=function(e,f)events[#events+1]={e,f}end}
uart={setup=function()end,on=function(_,e,f)callbacks[e]=f end,
 read=function()return table.remove(incoming,1)end,
 write=function(_,s)written[#written+1]=s;if partial then return #s-1 end;return #s end}
package.preload.exgnss=function()return{}end
package.preload.dfu_transfer=function()return{is_binary_mode=function()return false end}end
at_cmd_handlers={};ota_uart_idle=function()return idle end
function pump()for _,t in ipairs(tasks)do assert(coroutine.resume(t))end end
function sent()assert(callbacks.sent,'sent callback missing');callbacks.sent(1);pump()end
function feed(s)incoming[#incoming+1]=s;callbacks.receive()end
w=require('ota_wire');nonce=string.rep('n',16)
function quiet(k,seq,offset,n)return w.encode(k,1,seq or 1,offset or 0,n or nonce)end
frame=w.encode(4,2,7,3584,string.rep('x',512))
ack=w.encode(128,2,7,3584,string.pack('<BBI2I4I4I4',4,0,1,4096,4096,8192))
''')
    source=ROOT/'Air780EGH'
    # SAM | 2026-10-26 +08:00 | Verify the exact frozen maintenance source, not only the active workspace module.
    if os.environ.get('OTA_SOURCE_DIR'):
        source=Path(os.environ['OTA_SOURCE_DIR'])
        l.execute("package.path=.....'/?.lua;'..package.path",source.as_posix())
    if os.environ.get('OTA_RELEASE_VARIANT'):
        source=ROOT/'logs/uart_window_20261025/capacity_preview'/os.environ['OTA_RELEASE_VARIANT']/'source'
        l.execute("package.path=.....'/?.lua;'..package.path",source.as_posix())
        l.execute("package.loaded.ota_wire=nil;w=require('ota_wire')")
    l.execute((source/'uart_app.lua').read_text(encoding='utf-8-sig'))
    return l

def test_window():
    runtime().execute('''
assert(ota_uart_send(frame));assert(uart_send_raw('BUS_EVT=test'));pump()
assert(#written==1,'business bytes appended after DATA before ACK')
sent();assert(#written==1)
feed(quiet(240));pump();assert(#written==2 and w.decode(written[2]).type==241)
sent();feed(ack);pump();assert(#written==2,'payload ACK released quiet hold')
feed(quiet(242,2));pump();assert(#written==2,'wrong token released hold')
feed(quiet(242));pump();assert(#written==3 and #written[3]==88 and written[3]:sub(1,44)==written[3]:sub(45) and w.decode(written[3]:sub(1,44)).type==243)
sent();assert(#written==4 and written[4]=='BUS_EVT=test\\r\\n')
''')

def test_physical_accounting():
    runtime().execute("""
local now,sends=0,0
local t=require('ota_gr_transfer').new({track_tx=true,now=function()return now end,
 idle=function()return true end,send=function()sends=sends+1;return true end})
assert(t:start({id=string.rep('a',64),hash=string.rep('b',64),size=5000,target='GR5526',version='1.5.0'},'/candidate',2))
t:step();assert(t:status().attempts==0,'enqueue consumed physical attempt')
now=1999;t:step();assert(sends==1)
assert(t:on_tx_sent({session=2,sequence=0,offset=0,type=1}))
assert(t:status().attempts==1)
now=2100;t:step();assert(sends==1,'queue time became reply timeout')
""")

def test_granted_silence_does_not_spend_reply_deadline():
    # SAM | 2026-10-26 +08:00 | A permitted <3s Flash hold must not trip the ordinary 2s reply timer; after release a fresh reply deadline still applies.
    runtime().execute("""
assert(ota_uart_send(frame));pump();sent();feed(quiet(240));pump();sent()
clock=2500;pump();assert(not ota_uart_faulted(),'valid quiet lease tripped reply timer')
feed(ack);feed(quiet(242));pump();sent();assert(not ota_uart_faulted())
""")
    runtime().execute("""
assert(ota_uart_send(frame));pump();sent();feed(quiet(240));pump();sent()
clock=2500;feed(quiet(242));pump();sent();assert(not ota_uart_faulted())
-- SAM | 2026-10-26 13:08 +08:00 | Binary reply loss returns ownership to the separately tested bounded sender; it must not permanently latch the writer.
clock=4501;pump();assert(not ota_uart_faulted() and not ota_uart_owned(),'binary ACK loss did not yield to bounded sender retry')
""")
    runtime().execute("""
local ctl=require('ota_uart_window').new({now=function()return clock end,write=function(s)return #s end,event=function()end,idle=function()return true end})
-- SAM | 2026-10-29 06:06 +08:00 | Read-only QUERY no longer latches (GR may drop it during its result lease); a mutating control still must.
assert(ctl:write('q',{op='QUERY',job='a',hash='b',target='GR5526',epoch=2}));ctl:sent();clock=2001;ctl:pump();assert(not ctl:blocked() and ctl:available(),'unanswered QUERY latched');clock=0
assert(ctl:write('ctl',{op='PREPARED',job='a',hash='b',target='GR5526',epoch=2}));ctl:sent()
clock=2001;ctl:pump();assert(ctl:blocked(),'control reply loss must still stop')
""")

def test_real_sender_waits_for_real_quiet_window():
    # SAM | 2026-10-26 +08:00 | Couple both production state machines; a retransmit during owned silence must not create a phantom physical-TX wait.
    runtime().execute("""
local sender
local publish=sys.publish
sys.publish=function(e,f)
 publish(e,f)
 if e=='OTA2_TX_SENT' then sender:on_tx_sent(f)
 elseif e=='OTA2_FRAME' then sender:on_frame(f)
 elseif e=='OTA2_TX_FAILED' then sender:on_tx_failed(f)end
end
sender=require('ota_gr_transfer').new({track_tx=true,now=function()return clock end,idle=function()return true end,
 owns=function()return ota_uart_owned()end,read=function(_,_,n)return string.rep('x',n)end,send=ota_uart_send})
local job={id=string.rep('a',64),hash=string.rep('b',64),size=5000,version='1.5.0',target='GR5526'}
assert(sender:start(job,'/candidate',2));sender:step();pump();sent()
local hello=assert(w.decode(written[1]));feed(quiet(240));pump();sent()
clock=2500;sender:step();pump();assert(not ota_uart_faulted())
feed(w.encode(2,hello.session,hello.sequence,hello.offset,string.pack('<I2I2I4I4I4',512,4096,442368,0,1)))
feed(quiet(242));pump();sent();sender:step()
assert(sender:status().phase=='BEGIN','sender is stuck waiting for a retransmit that UART never sent')
sender:step();pump();assert(w.decode(written[#written]).type==3)
""")

def test_denied_release():
    runtime().execute("""
assert(ota_uart_send(frame));assert(uart_send_raw('BUS_EVT=alarm'));pump();sent()
idle=false;feed(quiet(240));pump();assert(w.decode(written[2]).offset==1);sent()
feed(quiet(242));pump();sent()
assert(written[#written]=='BUS_EVT=alarm\\r\\n','denied operation retained reply wait and blocked urgent business')
""")

def test_transport_edges():
    runtime().execute("""
assert(ota_uart_send(frame));assert(ota_uart_send(w.encode(4,2,8,4096,'next')))
assert(uart_send_raw('BUS_EVT=retained'));pump();sent()
feed(quiet(240));pump();sent();clock=8001;pump()
-- SAM | 2026-11-07 +08:00 | The accepted quiet lease is 90s; verify both its protected interval and expiry.
assert(not ota_uart_faulted(),'valid 90-second Flash lease faulted at the old 8-second boundary')
clock=90001;pump();assert(ota_uart_faulted(),'expired quiet lease did not latch a UART fault')
feed(quiet(242));pump();sent()
assert(#written==4 and written[4]=='BUS_EVT=retained\\r\\n','faulted queued OTA escaped before asynchronous cancellation')
assert(not ota_uart_send(frame),'fault latch reopened OTA')
""")
    runtime().execute("""
assert(ota_uart_send(frame));pump();sent();ota_uart_cancel();feed(quiet(240));pump()
assert(w.decode(written[2]).offset==1,'cancelled request still received Flash consent')
""")
    runtime().execute("""
-- SAM | 2026-10-26 13:08 +08:00 | Neither cancellation nor a missing physical sent callback may become a retryable binary reply timeout.
assert(ota_uart_send(frame));pump();sent();ota_uart_cancel();clock=2001;pump();assert(ota_uart_faulted())
""")
    runtime().execute("""
assert(ota_uart_send(frame));pump();clock=2001;pump();assert(ota_uart_faulted(),'missing physical sent callback was retried unsafely')
""")
    runtime().execute("""
assert(ota_uart_send(frame));pump();feed(ack);pump();assert(#written==1)
assert(uart_send_raw('BUS_EVT=late'));pump();assert(#written==1,'early ACK bypassed sent callback')
sent();assert(#written==2)
""")
    runtime().execute("""
partial=true;assert(ota_uart_send(frame));pump();assert(ota_uart_owned());assert(not ota_uart_send(frame))
local seen=false;for _,e in ipairs(events)do if e[1]=='OTA_UART_FAULT' then seen=true end end;assert(seen)
""")
    runtime().execute("""
feed(quiet(240));pump();sent();local n=#written
feed(quiet(240));pump();assert(#written==n,'duplicate grant could add bytes during Flash')
assert(dfu_uart_write('binary')==0)
""")

def test_legacy_dfu_closed():
    l=runtime()
    source=ROOT/'Air780EGH/dfu_transfer.lua'
    l.execute("package.preload.dfu_transfer=nil;package.loaded.dfu_transfer=nil;dfu_transfer=require('dfu_transfer')")
    l.execute("""
local before=#tasks
for _,name in ipairs({'DFU_DL','DFU_START','DFU_ERASE','DFU_ABORT'})do
 local reply;at_cmd_handlers[name](name,function(s)reply=s end)
 assert(reply=='+DFU: REJECTED REQUIRE_VERIFIED_OTA_TRANSACTION')
end
dfu_transfer.on_sent(1)
assert(#tasks==before and #written==0 and not dfu_transfer_active)
assert(dfu_transfer.get_state()=='idle' and not dfu_transfer.is_binary_mode())
""")

def test_release_recovery_edges():
    runtime().execute("""
feed(quiet(240));pump();sent();assert(uart_send_raw('BUS_EVT=held'))
json={decode=function()return {op='hello'}end};package.loaded.business_runtime={command=function()end}
clock=90001;pump();feed('BUS_CMD={"op":"hello"}\\r\\n');pump()
assert(#written==1,'hello opened UART while Flash release was still unknown')
feed(quiet(242));pump();sent()
assert(written[3]=='BUS_EVT=held\\r\\n');sent()
assert(not ota_uart_send(frame),'late release reset the OTA fault latch')
""")
    runtime().execute("""
feed(quiet(240));pump();sent();feed(quiet(242));pump();sent()
feed(quiet(240,2,0,string.rep('z',16)));pump();sent()
local n=#written;feed(quiet(242));pump()
assert(#written==n,'old DONE released a newer quiet window')
assert(uart_send_raw('BUS_EVT=new'));pump();assert(#written==n)
feed(quiet(242,2,0,string.rep('z',16)));pump();sent()
assert(written[#written]=='BUS_EVT=new\\r\\n')
""")
    l=runtime()
    # Production control matching: wrong epoch/phase must not release an outstanding request.
    l.execute("""
local window=require('ota_uart_window').new({now=function()return clock end,
 write=function(s)return #s end,event=function()end,idle=function()return true end})
-- SAM | 2026-10-28 22:09 +08:00 | ACTIVATE no longer holds the writer (GR validates before its lease); keep the matching check on PREPARED, which still awaits STATUS.
assert(window:write('ctl',{op='PREPARED',job='a',hash='b',target='GR5526',epoch=2}));window:sent()
window:on_control({op='STATUS',job='a',hash='b',target='GR5526',epoch=3,phase='PREPARED'});assert(window:busy())
window:on_control({op='STATUS',job='a',hash='b',target='GR5526',epoch=2,phase='DOWNLOADING'});assert(window:busy())
window:on_control({op='STATUS',job='a',hash='b',target='GR5526',epoch=2,phase='PREPARED'});assert(window:available())
assert(window:write('act',{op='ACTIVATE',job='a',hash='b',target='GR5526',epoch=2}));window:sent();assert(window:available(),'ACTIVATE held the writer')
""")

if __name__=='__main__':
    test_granted_silence_does_not_spend_reply_deadline()
    test_real_sender_waits_for_real_quiet_window()
    # SAM | 2026-10-26 +08:00 | Readback distinguishes a true writer fault latch from a historical quiet denial.
    runtime().execute('assert(ota_uart_faulted()==false);partial=true;assert(ota_uart_send(frame));pump();assert(ota_uart_faulted()==true)')
    test_window()
    test_physical_accounting()
    test_denied_release()
    test_transport_edges()
    test_legacy_dfu_closed()
    test_release_recovery_edges()
    print('PASS real UART window and physical send accounting')
