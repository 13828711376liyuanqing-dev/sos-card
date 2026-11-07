"""SAM | 2026-10-23 +08:00 | Exercise production proof sender loss/pause/owner boundaries without hardware."""
from test_cat_manager import runtime

lua = runtime()
lua.execute('''
local now,allowed,sent=0,true,{}
local p=require('ota_cat_proof').new({now=function()return now end,
 can_send=function()return allowed end,send=function(m)sent[#sent+1]=m;return true end})
local j={id=string.rep('a',64),hash=string.rep('b',64),version='1.5.0',target='CAT1'}
local text=string.rep('ab',904)
assert(not p:start(j,0,text));assert(not p:start(j,1,text..'00'))
assert(not p:start(j,1,string.rep('GG',904)))
assert(p:start(j,1,text))
local function ack(m)
 return {op='PROOF_ACK',reason='ok',job=m.job,hash=m.hash,target=m.target,
 version=m.version,epoch=m.epoch,offset=m.offset+#m.data/2}
end
for i=1,4 do
 local ok,why=p:step();assert(not ok and why=='DOWNLOAD_PENDING')
 local m=sent[#sent];assert(m.offset==(i-1)*256)
 assert(#m.data==(i==4 and 272 or 512))
 local a=ack(m);a.epoch=2;assert(not p:on_reply(a));a.epoch=1
 a.offset=a.offset+1;assert(not p:on_reply(a));a.offset=a.offset-1
 assert(p:on_reply(a));assert(not p:on_reply(a))
end
assert(p:ready(j,1));assert(not p:ready(j,2));assert(p:step())
p:reset();assert(not p:ready(j,1));assert(p:start(j,1,text))
p:step();local first=sent[#sent];now=2999;p:step();assert(sent[#sent]==first)
allowed=false;now=9000;local _,why=p:step();assert(why=='BUSINESS_PAUSED')
assert(not p:on_reply(ack(first)));allowed=true;p:step();assert(sent[#sent]==first)
now=12000;p:step();assert(sent[#sent].offset==0)
now=15000;p:step();now=18000;local ok,err=p:step()
assert(not ok and err=='CAT_PROOF_TIMEOUT');assert(not p:ready(j,1))
p:step();assert(p:on_reply(ack(sent[#sent])))
assert(p:start(j,2,text));p:step();assert(sent[#sent].offset==0)
now=-1;local _,err=p:step();assert(err=='CAT_PROOF_CLOCK')
''')
print('PASS CAT proof four fragments, stale/duplicate ACK, pause, bounded retry, restart and epoch reset')
