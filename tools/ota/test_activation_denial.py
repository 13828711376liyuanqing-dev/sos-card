"""SAM | 2026-10-27 +08:00 | Preserve matching GR activation refusals without retrying or installing; source tests only."""
from test_cat_manager import runtime

SETUP="""
m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED')));assert(m:request_activation())
d=reply(m,'DENY','INSTALL_PENDING');d.reason='boot_commit_failed'
"""

def check():
    l=runtime();l.execute(SETUP+"""
assert(m:on_gr(d),'ACTIVATION_DENIAL_NOT_PERSISTED')
assert(m:status().phase=='RECOVERY_HOLD' and m:status().reason==d.reason)
assert(activation==0 and not m:request_activation())
m=newmanager();assert(m:status().phase=='RECOVERY_HOLD' and m:status().reason==d.reason)
assert(not m:request_activation() and activation==0)
""")
    for change in ("d.epoch=2","d.hash=string.rep('d',64)","d.version='9.9.9'","d.reason=''","d.phase='COMPLETE'"):
        l=runtime();l.execute(SETUP+change+";assert(not m:on_gr(d));assert(m:status().phase=='WAIT_ACTIVATE' and activation==0)")
    l=runtime();l.execute(SETUP+"fail_write=true;assert(not m:on_gr(d));assert(m.error and activation==0)")
    l=runtime();l.execute(SETUP+"""
local s=newstore():load();s.trial={id=s.job.id,hash=s.job.hash,epoch=s.epoch,md5=s.job.md5,status='RUNNING'}
assert(newstore():save(s));m=newmanager()
assert(m:on_gr(d));assert(m:status().trial.status=='SPENT')
""")
    print('PASS matching refusal, exact scope, restart, write failure, no activation and spent trial')

if __name__=='__main__':check()
