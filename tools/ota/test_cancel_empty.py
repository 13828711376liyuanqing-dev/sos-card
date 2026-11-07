"""SAM | 2026-10-24 +08:00 | Empty cancellation must survive reset without clearing failure history or user data."""
import unittest
from test_cat_manager import runtime

SETUP="""
local resolve=port.resolve
port.resolve=function(c)local j=resolve(c);j.size=5000;j.bundle={md5=c.Md5,manifest_sha256=string.rep('d',64)};return j end
port.prepare=function()return false,'write_readback_failed'end
m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
assert(not m:prepare());assert(m:status().phase=='PAUSED')
function cancelled()
 local r=reply(m,'CANCELLED','COMPLETE');r.version=m:status().job.source;r.outcome='fail'
 r.reason='cancelled_before_install';r.cancelled_before_install=true;return r
end
"""
class Tests(unittest.TestCase):
 def test_history_and_owner_wait_for_exact_receipt(self):
  runtime().execute(SETUP+"""
   local old=m:status();assert(m:request_cancel_empty(command.Md5))
   assert(m:status().phase=='CANCELLING' and sent[#sent].op=='CANCEL_EMPTY')
   local r=cancelled();r.epoch=r.epoch+1;assert(not m:on_gr(r));assert(m:status().job)
   r=cancelled();r.cancelled_before_install=false;assert(not m:on_gr(r));assert(m:status().job)
   m=newmanager();assert(m:status().phase=='CANCELLING');assert(m:reconcile());assert(sent[#sent].op=='CANCEL_EMPTY')
   assert(m:on_gr(cancelled()));local s=m:status();assert(s.phase=='IDLE' and not s.job and not s.release)
   assert(s.cancelled.hash==old.job.hash and s.retries[old.job.hash].permanent)
   assert(s.retries[old.job.hash].count==old.retries[old.job.hash].count and s.failures[old.job.hash]==1)
   assert(activation==0);assert(not m:on_gr({op='CANCELLED'}))
  """)
 def test_wrong_bundle_or_reason_cannot_cancel(self):
  runtime().execute(SETUP+"""
   assert(not m:request_cancel_empty(string.rep('f',32)));assert(m:status().phase=='PAUSED')
   local s=m:status();s.reason='DOWNLOAD_PENDING';assert(newstore():save(s));m=newmanager()
   assert(not m:request_cancel_empty(command.Md5));assert(m:status().phase=='PAUSED')
  """)
if __name__=='__main__':unittest.main()
