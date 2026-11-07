"""SAM | 2026-10-24 +08:00 | Observe actual SIP wrapper stop/start snapshots without networking or audio initialization."""
from test_cat_manager import runtime
lua=runtime()
lua.execute('''
local events={};local tasks=0
package.loaded.exsip={TRANSPORT_UDP=0}
package.loaded.exaudio={};package.loaded.audio_drv={}
package.loaded.tts={init=function()end,play=function()end}
package.loaded.netdrv_device={ip_ready=function()return true end}
sys={subscribe=function()end,publish=function(n)events[#events+1]=n end,
 taskInitEx=function()tasks=tasks+1 end}
log={info=function()end,warn=function()end,error=function()end}
_G.at_cmd_handlers={}
local sip=require('sip');local s=sip.ota_status()
assert(s.state=='STATE_IDLE' and s.task_running==false and tasks==0)
s.task_running=true;assert(sip.ota_status().task_running==false)
_G.at_cmd_handlers.SIP_INIT('',function()end)
s=sip.ota_status();assert(s.task_running==true and s.state=='STATE_INITING')
assert(tasks==1 and events[1]=='SIP_APP_MAIN_STARTING')
_G.at_cmd_handlers.SIP_INIT('',function()end);assert(tasks==1)
''')
print('PASS real SIP wrapper: read-only stopped snapshot, single task start, immediate permission retirement')
