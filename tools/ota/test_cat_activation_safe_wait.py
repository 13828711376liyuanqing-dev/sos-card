# SAM | 2026-11-06 +08:00 | Exercise real manager safety-wait recovery without device or network effects.
"""Focused regression for bounded, durable GR activation safety waits."""
from test_cat_manager import runtime

SETUP = """
clock=100;port.now=function()return clock end
local resolve=port.resolve
port.resolve=function(c)local j=resolve(c);j.bundle={md5=c.Md5,manifest_sha256=string.rep('d',64)};return j end
OTA_TRIAL_MD5=command.Md5;OTA_TRIAL_TARGET=command.TargetVersion
m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED')));assert(m:request_activation())
function deny(reason,phase)
 local r=reply(m,'DENY',phase or 'PREPARED');r.reason=reason or 'activation_safe_wait';return r
end
function safe_status(phase)
 local r=reply(m,'STATUS',phase or 'PREPARED');r.reason='ok';r.commit_safe=true;return r
end
function activations()
 local n=0;for _,r in ipairs(sent)do if r.op=='ACTIVATE' then n=n+1 end end;return n
end
"""

CASES = {
 'explicit wait preserves candidate and trial until fresh safe query reply': """
 local before=m:status();assert(before.trial.status=='RUNNING')
 assert(m:on_gr(deny()));local s=m:status()
 assert(s.trial.status=='RUNNING','temporary safety wait must not spend trial')
 assert(s.job.hash==before.job.hash and s.prepared_ack==before.prepared_ack)
 assert(sent[#sent].op=='QUERY');assert(activations()==1)
 assert(m:on_gr(safe_status()));assert(m:status().phase=='PREPARED')
 clock=129;assert(not m:request_activation());assert(activations()==1)
 clock=130;assert(not m:request_activation());assert(sent[#sent].op=='QUERY')
 assert(m:on_gr(safe_status()));port.safe=function()return false end
 assert(not m:request_activation() and activations()==1)
 port.safe=function()return true end;assert(m:request_activation());assert(activations()==2)
 assert(m:status().activation_retry.count==1 and m:status().trial.status=='RUNNING')
 """,
 'three retry reservations survive restart and repush then stop sending': """
 for i=1,3 do
  assert(m:on_gr(deny()));local due=clock+30
  m=newmanager();assert(not m:accept(command));assert(activations()==i)
  clock=due-1;assert(m:reconcile());assert(activations()==i)
  clock=due;assert(m:reconcile());assert(sent[#sent].op=='QUERY')
  assert(m:on_gr(safe_status()));assert(m:request_activation())
  assert(m:status().activation_retry.count==i and activations()==i+1)
 end
 assert(m:on_gr(deny()));m=newmanager();local count=#sent;clock=999
 for _=1,20 do m:reconcile();m:request_activation() end
 assert(#sent==count and activations()==4,'exhausted retry must remain silent')
 assert(m:status().trial.status=='RUNNING' and m:status().phase=='WAIT_ACTIVATE')
 """,
 'unsafe stale or unmatched status cannot reauthorize retry': """
 assert(m:on_gr(deny()));clock=130;assert(m:reconcile())
 for _,field in ipairs({'epoch','hash','job','version','target'}) do
  local r=safe_status();r[field]=field=='epoch' and 2 or 'wrong';assert(not m:on_gr(r))
 end
 local r=safe_status();r.commit_safe=false;assert(m:on_gr(r));assert(not m:request_activation())
 r=safe_status();r.reason='busy';assert(m:on_gr(r));assert(not m:request_activation())
 assert(activations()==1 and m:status().phase=='WAIT_ACTIVATE')
 assert(m:on_gr(safe_status()));clock=134;assert(not m:request_activation())
 assert(activations()==1 and sent[#sent].op=='QUERY')
 """,
 'inflight reservation after restart never blindly repeats ACTIVATE': """
 assert(m:on_gr(deny()));clock=130;assert(m:reconcile());assert(m:on_gr(safe_status()));assert(m:request_activation())
 m=newmanager();assert(m:reconcile());assert(sent[#sent].op=='QUERY')
 m:on_gr(safe_status());assert(m:status().phase=='RECOVERY_HOLD')
 m:on_gr(safe_status('INSTALL_PENDING'))
 for _=1,6 do m:reconcile();m:request_activation() end
 assert(activations()==2,'uncertain activation may only reconcile')
 """,
 'install pending and actual validation failure retain recovery behavior': """
 assert(m:on_gr(deny(nil,'INSTALL_PENDING')));assert(m:status().phase=='RECOVERY_HOLD')
 assert(m:status().trial.status=='SPENT' and m:status().activation_retry==nil)
 """,
 'true validation failure never receives automatic retry': """
 assert(m:on_gr(deny('activation_validation_failed')))
 assert(m:status().phase=='RECOVERY_HOLD' and m:status().trial.status=='SPENT')
 assert(m:status().activation_retry==nil)
 """,
 'pending wait cannot downgrade install pending or replay stale prepared': """
 assert(m:on_gr(deny()));clock=130;assert(m:reconcile());assert(m:on_gr(safe_status('INSTALL_PENDING')))
 assert(m:status().phase=='RECOVERY_HOLD');assert(not m:on_gr(safe_status()))
 for _=1,6 do m:reconcile();m:request_activation() end
 assert(activations()==1)
 """,
 'unknown clock and failed persistence never send activation': """
 port.now=function()return nil end;assert(m:on_gr(deny()));m=newmanager()
 for _=1,5 do m:reconcile();m:request_activation() end
 assert(activations()==1)
 port.now=function()return clock end;clock=200;m:reconcile();clock=229;m:reconcile()
 assert(activations()==1);clock=230;assert(m:reconcile());assert(m:on_gr(safe_status()))
 fail_write=true;assert(not m:request_activation());assert(activations()==1 and m:status().error)
 """,
 'yielding safety check cannot overwrite install pending recovery': """
 assert(m:on_gr(deny()));clock=130;assert(m:reconcile());assert(m:on_gr(safe_status()))
 port.safe=function()m:on_gr(safe_status('INSTALL_PENDING'));return true end
 assert(not m:request_activation());assert(m:status().phase=='RECOVERY_HOLD')
 assert(activations()==1)
 """,
 'restart retry uses GR candidate receipt without new network preparation': """
 assert(m:on_gr(deny()));m=newmanager();clock=130;assert(m:reconcile());assert(m:on_gr(safe_status()))
 port.prepare=function()error('must retain candidate')end
 port.verify_candidate=function()error('must not restart bundle restore')end
 assert(m:request_activation());assert(activations()==2 and m:status().trial.status=='RUNNING')
 """,
 'new unsafe status revokes an earlier safe receipt': """
 assert(m:on_gr(deny()));clock=130;assert(m:reconcile());assert(m:on_gr(safe_status()))
 local r=safe_status();r.commit_safe=false;assert(m:on_gr(r))
 assert(not m:request_activation());assert(activations()==1 and sent[#sent].op=='QUERY')
 """,
 'expired safety during yielding gate must query again': """
 assert(m:on_gr(deny()));clock=130;assert(m:reconcile());assert(m:on_gr(safe_status()))
 port.safe=function()clock=134;return true end
 assert(not m:request_activation());assert(activations()==1 and sent[#sent].op=='QUERY')
 """,
 'legacy boot commit denial cannot bypass the new retry budget': """
 assert(m:on_gr(deny()));clock=130;assert(m:reconcile());assert(m:on_gr(safe_status()));assert(m:request_activation())
 assert(m:on_gr(deny('boot_commit_failed','INSTALL_PENDING')))
 for _=1,6 do m:reconcile() end
 assert(m:status().phase=='RECOVERY_HOLD' and activations()==2)
 """,
 'spent ticket cannot be revived by explicit wait': """
 local s=m:status();s.trial.status='SPENT';assert(newstore():save(s));m=newmanager()
 assert(m:on_gr(deny()));assert(m:status().phase=='RECOVERY_HOLD')
 assert(m:status().trial.status=='SPENT' and m:status().activation_retry==nil)
 """,
 'corrupt durable retry scope fails closed': """
 assert(m:on_gr(deny()));local s=m:status();s.activation_retry.epoch=2
 assert(newstore():save(s));m=newmanager();assert(m:status().error)
 assert(not m:reconcile());assert(activations()==1)
 """,
 'duplicate wait does not reset durable cooldown': """
 assert(m:on_gr(deny()));clock=120;assert(m:on_gr(deny()))
 clock=130;assert(m:reconcile());assert(m:on_gr(safe_status()));assert(m:request_activation())
 assert(activations()==2)
 """,
}

if __name__ == '__main__':
 failures=[]
 for name,script in CASES.items():
  try:
   runtime().execute(SETUP+script)
   print('PASS',name)
  except Exception as exc:
   failures.append(name);print('FAIL',name,exc)
 if failures: raise SystemExit(f'{len(failures)} focused activation checks failed')
