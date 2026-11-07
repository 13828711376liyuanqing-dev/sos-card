"""SAM | 2026-10-26 +08:00 | The shared idle/clock adapters must retain fail-closed sender decisions for valid, missing and invalid callbacks."""
from test_cat_manager import runtime
import os

def check():
    l=runtime()
    if os.environ.get('OTA_SOURCE_DIR'):
        l.execute("package.path=.....'/?.lua;'..package.path",os.environ['OTA_SOURCE_DIR'])
    l.execute('''
sys={};log={info=function()end};clock=0;mcu={ticks=function()return clock end}
local original=require('ota_gr_transfer')
local capture
package.loaded.ota_gr_transfer={new=function(p)capture=p;return {}end}
require('ota_runtime').new({store=newstore(),codec=json,port=port,gr_transfer_port={}})
assert(type(capture.now)=='function' and type(capture.idle)=='function')
local checks={function()return true end,function()return false end,function()return nil end,
function()return 1 end,function()return 'true' end,function()error('idle unavailable')end}
for i,f in ipairs(checks)do
 local count=0;port.idle=function()count=count+1;return f()end
 assert(capture.idle()==(i==1) and count==1,'IDLE_BINDING_OR_EVALUATION_CHANGED')
end
port.idle=nil;assert(not capture.idle())
local clocks={function()return 0 end,function()return 4294967295 end,
function()return nil end,function()return -1 end,function()return .5 end,
function()return 4294967296 end,function()return math.huge end,function()return 0/0 end,
function()return '123'end,function()error('clock unavailable')end}
local function old()return mcu and type(mcu.ticks)=='function' and mcu.ticks() or nil end
for _,f in ipairs(clocks)do
 mcu={ticks=f};local result={}
 for i,now in ipairs({old,capture.now})do
  local sender=original.new({now=now,idle=function()return true end,send=function()return true end})
  assert(sender:start({id=string.rep('a',64),hash=string.rep('b',64),size=5000,target='GR5526',version='1.5.0'},'/candidate',4))
  local ok,why=sender:step();result[i]=tostring(ok)..':'..tostring(why)..':'..sender:status().phase
 end
 assert(result[1]==result[2],'CLOCK_GATE_DECISION_CHANGED')
end
''')
    print('PASS shared idle single evaluation and old/new sender clock decisions for all valid/invalid/error cases')

if __name__=='__main__':check()
