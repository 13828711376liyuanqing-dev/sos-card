"""SAM | 2026-10-24 +08:00 | The maintenance bridge must hold S2 before any automatic network/UART/install work."""
import unittest
from test_cat_manager import runtime,ROOT

class Tests(unittest.TestCase):
 def test_only_cancellation_is_forwarded_for_the_old_bundle(self):
  lua=runtime();lua.globals().bridge_file=(ROOT/'tools/ota/storage_repair_bridge.lua').as_posix()
  lua.execute('''
   local old='d31713e0fb1af1bcb4eb026a201b2a39';local phase='PAUSED';local calls=0
   local a={status=function()return {phase=phase,job={bundle={md5=old}}}end,
    tick=function()calls=calls+1;return true end,pump_gr=function()calls=calls+1;return true end,
    on_gr_line=function()calls=calls+1;return true end,accept=function()calls=calls+1;return true end,
    request_cancel_empty=function(_,md5)assert(md5==old);phase='CANCELLING';return true end}
   package.loaded.ota_runtime={new=function()return a end}
   local b=assert(loadfile(bridge_file))().new({})
   for _,p in ipairs({'PAUSED','PREPARING','GR_GRANTED','PREPARED','INSTALLING'})do
    phase=p;assert(not b:tick());assert(not b:pump_gr());assert(not b:on_gr_line('ignored'))
    assert(not b:accept({Md5=old}));assert(not b:accept({Md5=string.rep('f',32)}));assert(calls==0)
   end
   phase='PAUSED';assert(b:request_cancel_empty(old));assert(b:tick());assert(b:on_gr_line('receipt'))
   assert(calls==2);assert(not b:accept({Md5=old}))
  ''')
if __name__=='__main__':unittest.main()
