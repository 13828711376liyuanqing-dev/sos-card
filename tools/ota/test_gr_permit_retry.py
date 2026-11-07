"""SAM | 2026-10-24 +08:00 | A GR permit NACK is bounded refusal, not a corrupt-package verdict; never reset attempts or accept installation."""
import unittest
from test_cat_manager import runtime
class PermitTests(unittest.TestCase):
 def test_sender_retries_same_frame_after_one_permit_nack(self):
  l=runtime();l.execute('''
  local wire=require('ota_wire');local sender;local clock=0;local denied=false;local total=1024;local accepted=0
  local job={target='GR5526',id=string.rep('a',64),hash=string.rep('b',64),size=total,version='1.5.0'}
  sender=require('ota_gr_transfer').new({now=function()return clock end,idle=function()return true end,
   read=function(_,_,n)return string.rep('x',n)end,send=function(raw)
    local f=wire.decode(raw);local kind,payload=128
    if f.type==1 then kind=2;payload=string.pack('<I2I2I4I4I4',512,4096,442368,0,1)
    elseif f.type==3 and not denied then denied=true;kind=129;payload=string.pack('<BBI2I4I4I4',3,7,1,0,0,total)
    else
     if f.type==4 then accepted=accepted+#f.payload end
     payload=string.pack('<BBI2I4I4I4',f.type,0,f.type==6 and 3 or 1,accepted,accepted==total and total or 0,total)
    end
    assert(sender:on_frame(wire.decode(wire.encode(kind,f.session,f.sequence,f.offset,payload))));return true
   end})
  assert(sender:start(job,'/candidate',7))
  for i=1,30 do clock=clock+1000;sender:step()end
  assert(denied and sender:ready(job,7));assert(accepted==total)
  ''')
 def test_old_permit_latch_reclassified_only_after_reconciliation_without_resetting_count(self):
  l=runtime();l.execute('''
  local clock=100;port.now=function()return clock end
  local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
  port.prepare=function()return false,'GR_NACK_7'end;assert(not m:prepare())
  local s=m:status();local hash=s.job.hash;s.retries[hash].permanent=true
  assert(newstore():save(s));m=newmanager();assert(not m:prepare())
  assert(m:on_gr(reply(m,'STATUS','DOWNLOADING')));clock=131
  local ok,e=m:prepare();assert(not ok and e=='GR_PERMISSION_RETRY_ARMED')
  assert(m:status().retries[hash].count==1 and not m:status().retries[hash].permanent)
  port.prepare=function()return true end;assert(m:prepare());assert(m:status().phase=='PREPARED')
  assert(m:status().retries[hash].count==1)
  ''')
if __name__=='__main__':unittest.main()
