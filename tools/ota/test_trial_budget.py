"""SAM | 2026-10-25 +08:00 | A new repair hash must not silently gain the normal three prepare attempts."""
from test_cat_manager import runtime

def check():
 runtime().execute("""
 local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
 local j=m:status().job;assert(m:arm_trial(j.id,j.hash,1,command.Md5))
 port.prepare=function()return false,'DOWNLOAD_PENDING'end;assert(not m:prepare())
 assert(m:transport_fault('UART_QUIET_TIMEOUT'));assert(m:status().trial.status=='SPENT')
 assert(m:transport_fault('UART_QUIET_DENIED'));assert(m:status().reason=='UART_QUIET_TIMEOUT','release overwrote first fault')
 m=newmanager();assert(m:status().trial.status=='SPENT');assert(not m:prepare())
 """)
 runtime().execute("""
 local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
 local j=m:status().job;assert(m:arm_trial(j.id,j.hash,1,command.Md5))
 port.prepare=function()return false,'DOWNLOAD_PENDING'end
 for i=1,4 do assert(not m:prepare());assert(m:status().trial.status=='RUNNING')end
 port.prepare=function()return false,'network_error'end
 assert(not m:prepare());assert(m:status().trial.status=='SPENT')
 port.now=function()return 9999 end;local ok,e=m:prepare();assert(not ok and e=='TRIAL_SPENT')
 m=newmanager();assert(m:status().trial.status=='SPENT');assert(not m:arm_trial(j.id,j.hash,1,command.Md5))
 """)
 runtime().execute("""
 local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
 local j=m:status().job;assert(m:arm_trial(j.id,j.hash,1,command.Md5))
 port.prepare=function()return false,'DOWNLOAD_PENDING'end;assert(not m:prepare())
 m=newmanager();assert(m:status().trial.status=='SPENT')
 """)
 print('PASS exact trial budget: pending is one attempt; failure and restart cannot replenish it')
if __name__=='__main__':check()

