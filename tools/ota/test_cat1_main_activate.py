"""SAM | 2026-10-29 06:39 +08:00 | Host-test the main Air780EGH ACTIVATE timing port: during this boot's wait for GRANT/DENY the manager sends no QUERY and ignores in-flight STATUS (which previously reset WAIT_ACTIVATE to PREPARED and re-sent ACTIVATE), bounded to 180 ticks; after a reboot the original QUERY reconciliation is unchanged."""
import test_cat_manager as t

READY = '''
local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED')));assert(m:request_activation());assert(sent[#sent].op=='ACTIVATE')
'''

if __name__ == '__main__':
    t.check('in-flight STATUS during WAIT_ACTIVATE is ignored, no QUERY or second ACTIVATE, GRANT proceeds', READY + '''
local n=#sent
m:on_gr(reply(m,'STATUS','PREPARED'));assert(m:status().phase=='WAIT_ACTIVATE','STALE_PREPARED_RESET_PHASE')
for i=1,30 do m:reconcile();m:request_activation() end
for i=n+1,#sent do assert(sent[i].op~='QUERY' and sent[i].op~='ACTIVATE','SENT_DURING_GRANT_WAIT '..sent[i].op) end
assert(m:on_gr(reply(m,'GRANT','INSTALL_PENDING')));assert(m:status().phase~='WAIT_ACTIVATE')
''')
    t.check('GRANT wait is bounded: after 180 ticks QUERY reconciliation resumes', READY + '''
local n=#sent;for i=1,180 do m:reconcile() end;assert(#sent==n)
m:reconcile();assert(sent[#sent].op=='QUERY','NO_QUERY_AFTER_BOUND')
''')
    t.check('a real INSTALL_PENDING (lost GRANT) is still handled immediately', READY + '''
m:on_gr(reply(m,'STATUS','INSTALL_PENDING'));assert(m:status().phase=='RECOVERY_HOLD','LOST_GRANT_IGNORED');assert(activation==0)
''')
    t.check('a DENY while waiting is still handled', READY + '''
local d=reply(m,'DENY','PREPARED');d.reason='quiet_denied';m:on_gr(d);assert(m:status().phase=='RECOVERY_HOLD')
''')
    t.check('after a reboot in WAIT_ACTIVATE the original QUERY reconciliation is unchanged', READY + '''
m=newmanager();local n=#sent;m:reconcile();assert(sent[#sent].op=='QUERY' and #sent==n+1,'REBOOT_RECONCILE_CHANGED')
''')
    print('PASS main ACTIVATE timing: no QUERY/duplicate ACTIVATE while awaiting GRANT, stale STATUS ignored, 180-tick bound, DENY handled, reboot reconcile unchanged')
