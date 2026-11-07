"""SAM | 2026-11-05 +08:00 | Platform push dispatch reports real acceptance without changing the OTA engine."""
from test_cat_manager import runtime

lua = runtime()
lua.execute(r'''
package.loaded.resident_name={}
log={info=function()end,warn=function()end}
events={};diag={};calls=0;tasks={}
sys={publish=function(n)events[#events+1]=n end,taskInit=function(f)tasks[#tasks+1]=f end}
local engine={receive=function(_,topic,c,metas)
 calls=calls+1;assert(topic=='test/down' and c.MsgType=='otaMsg' and metas.retain==false)
 if mode=='exception' then error('private URL must not be echoed') end
 return mode=='accepted',mode=='secret' and 'http://private.invalid/token' or 'VERSION_FORMAT'
end}
package.loaded.ota_runtime={instance=function()return engine end}
_G.ota_diag=function(s)diag[#diag+1]=s end
local recv=require('mqtts_receiver')
local payload=json.encode(command)
function push(m)
 mode=m;recv.proc('test/down',payload,{retain=false});tasks[#tasks]()
end
push('rejected')
assert(calls==1 and diag[1]=='[OTA_RX] REJECTED VERSION_FORMAT')
assert(#events==1 and events[1]=='FEED_NETWORK_WATCHDOG','must not echo OTA into legacy handling')
push('accepted')
assert(diag[2]=='[OTA_RX] ACCEPTED')
push('secret')
assert(diag[3]=='[OTA_RX] REJECTED UNKNOWN')
push('exception')
assert(diag[4]=='[OTA_RX] REJECTED EXCEPTION' and calls==4)
assert(#events==4 and activation==0,'dispatch is not permission to install')
''')
print('PASS platform dispatch: one engine call; real accept/reject; no legacy echo, secret leakage or install')
