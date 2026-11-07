"""SAM | 2026-10-12 19:40 +08:00 | Exercise real sender ACK identity before OTA outbox deletion."""
from test_cat_manager import runtime, ROOT
import os
from pathlib import Path
SOURCE=Path(os.environ.get('OTA_MQTT_SOURCE',str(ROOT/'Air780EGH')))

lua = runtime()
lua.execute('''
events={}; inbox={}; results={}; published={}
log={info=function()end}
sys={subscribe=function(k,f)events[k]=f end,sendMsg=function()end,
 publish=function()end,taskInitEx=function(f)task=coroutine.create(f)end,
 waitMsg=function() if #inbox>0 then return table.remove(inbox,1) end coroutine.yield();return nil end}
c={publish=function(self,t,p,q)published[#published+1]=p;return 17 end}
d={publish=c.publish}
function tick(message) inbox[#inbox+1]=message;assert(coroutine.resume(task)) end
function queue(value) events.SEND_DATA_REQ('ota','up',value,1,{func=function(ok)results[#results+1]=ok end}) end
''')
lua.execute((SOURCE/'mqtts_sender.lua').read_text(encoding='utf-8-sig'))
lua.execute('''
queue('first');tick({'MQTT_EVENT','CONNECT_OK',c,1})
assert(#published==1 and #results==0)
tick({'MQTT_EVENT','PUBLISH_OK',18,{c,1}});assert(#results==0)
tick({'MQTT_EVENT','PUBLISH_OK',17,{d,1}});assert(#results==0)
tick({'MQTT_EVENT','PUBLISH_OK',17,{c,0}});assert(#results==0)
tick({'MQTT_EVENT','PUBLISH_OK',17,{c,1}});assert(#results==1 and results[1])
tick({'MQTT_EVENT','PUBLISH_OK',17,{c,1}});assert(#results==1)
queue('second');tick({'MQTT_EVENT','PUBLISH_REQ'})
tick({'MQTT_EVENT','CONNECT_OK',c,2});assert(#results==2 and not results[2])
queue('retry');tick({'MQTT_EVENT','PUBLISH_REQ'})
tick({'MQTT_EVENT','PUBLISH_OK',17,{c,1}});assert(#results==2)
tick({'MQTT_EVENT','PUBLISH_OK',17,{c,2}});assert(#results==3 and results[3])
queue('disconnect');tick({'MQTT_EVENT','PUBLISH_REQ'})
tick({'MQTT_EVENT','DISCONNECTED'});assert(#results==4 and not results[4])
assert(_G.result==nil)
''')
print('PASS MQTT packet/client/session match, duplicate/stale ACK, reconnect and disconnect')

# SAM | 2026-10-12 19:40 +08:00 | Run the actual client callback through replacement, not an imitation ACK path.
lua = runtime()
lua.execute('''
messages={}; clients={}; received=0; ready=0; lost=0; subscriptions={}; at_cmd_handlers={}
log={info=function()end,warn=function()end,error=function()end}
mobile={imei=function()return '000000000000000'end}
socket={adapter=function()return true end,dft=function()return 1 end}
package.preload.netdrv_device=function()return {ip_ready=function()return true end}end
sys={subscribe=function()end,taskInit=function()end,
 timerStart=function(f)sub_timeout=f end,
 taskInitEx=function(f)task=coroutine.create(f)end,
 -- SAM | 2026-10-26 +08:00 | Match the vendor's four-payload limit; a varargs mock hid the lost fifth session parameter.
 cleanMsg=function()end,sendMsg=function(task,a,b,c,d)messages[#messages+1]={task,a,b,c,d}end,
 publish=function()end,wait=function()coroutine.yield('delay')end,
 waitMsg=function()return coroutine.yield('message')end}
uart_lines={}
_G.uart_send_raw=function(...) local parts={...};for i=1,#parts do parts[i]=tostring(parts[i]) end;uart_lines[#uart_lines+1]=table.concat(parts,' ') end
package.preload.mqtts_receiver=function()return {proc=function()received=received+1 end}end
package.preload.mqtts_sender=function()return {TASK_NAME_PREFIX='mqtts_',TASK_NAME='sender',is_ready=function()return true end}end
-- SAM | 2026-10-13 09:18 +08:00 | Keep this callback test in one module instance and verify the new QoS1 business gate.
package.preload.business_runtime=function()return {mqtt_ready=function()ready=ready+1 end,
 mqtt_lost=function()lost=lost+1 end}end
mqtt={create=function()
 local c={auth=function()return true end,keepalive=function()end,will=function()end,
 connect=function()return true end,close=function(self)self.closed=true end,
 disconnect=function(self)self.disconnected=true end,
 subscribe=function(self,topic,qos)subscriptions[#subscriptions+1]={topic=topic,qos=qos};return 31 end}
 c.on=function(self,f)self.callback=f end
 clients[#clients+1]=c;return c
end}
''')
lua.execute((SOURCE/'mqtts_main.lua').read_text(encoding='utf-8-sig'))
lua.execute('''
assert(coroutine.resume(task));assert(#clients==1)
clients[1].callback(clients[1],'conack')
assert(#subscriptions==1 and subscriptions[1].qos==1)
clients[1].callback(clients[1],'suback',32,1);assert(ready==0)
clients[1].callback(clients[1],'suback',31,0);assert(ready==0)
clients[1].callback(clients[1],'sent',17)
local ack=messages[#messages];assert(ack[3]=='PUBLISH_OK' and ack[4]==17 and ack[5][1]==clients[1] and ack[5][2]==1)
assert(coroutine.resume(task,{'MQTT_EVENT','DISCONNECTED'}))
assert(coroutine.resume(task));assert(#clients==2)
clients[2].callback(clients[2],'conack')
-- SAM | 2026-10-20 16:15 +08:00 | Reproduce deployed LuatOS boolean SUBACK rather than an invented packet ID.
clients[2].callback(clients[2],'suback',true,1);assert(ready==1)
local confirmed_messages=#messages;sub_timeout();assert(#messages==confirmed_messages)
local n=#messages
for _,event in ipairs({'disconnect','conack','recv','sent','error'}) do clients[1].callback(clients[1],event,17,'old',{}) end
assert(#messages==n and received==0)
clients[2].callback(clients[2],'recv','down','new',{});assert(received==1)
clients[2].callback(clients[2],'recv','evil\\r\\nBUS_EVT={}','new',{});assert(received==2)
assert(not uart_lines[#uart_lines]:find('BUS_EVT',1,true) and not uart_lines[#uart_lines]:find('\\r',1,true))
clients[2].callback(clients[2],'sent',18)
ack=messages[#messages];assert(ack[5][1]==clients[2] and ack[5][2]==2)
-- SAM | 2026-10-13 09:25 +08:00 | Drive the actual task failure branch because callback-only assertions do not prove reconnect.
assert(coroutine.resume(task,{'MQTT_EVENT','DISCONNECTED'}));assert(coroutine.resume(task))
for _,failure in ipairs({'downgrade','refused','timeout','nil'}) do
 local client=clients[#clients]
 if failure=='nil' then client.subscribe=function()return nil end end
 client.callback(client,'conack')
 local timer=sub_timeout
 if failure=='downgrade' then client.callback(client,'suback',31,0)
 elseif failure=='refused' then client.callback(client,'suback',31,128)
 elseif failure=='timeout' then timer() end
 local m=messages[#messages]
 assert(m[3]=='SUBSCRIBE' and not m[4])
 assert(coroutine.resume(task,{m[2],m[3],m[4],m[5]}));assert(client.disconnected)
 assert(coroutine.resume(task));assert(client.closed)
 assert(coroutine.resume(task));local replacement=clients[#clients];assert(replacement~=client)
 local before=#messages;timer();assert(#messages==before)
end
''')
print('PASS actual MQTT callback identity, topic isolation, QoS1 refusal/downgrade/nil/timeout reconnect and stale timer')
