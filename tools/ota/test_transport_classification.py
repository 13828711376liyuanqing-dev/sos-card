"""SAM | 2026-10-26 +08:00 | Detailed transport causes stay bounded/transient; malformed content remains permanent."""
from test_cat_manager import runtime
for reason in ('network_timeout','network_idle_timeout','network_eof','network_socket','HTTP_TIMEOUT','HTTP_IDLE_TIMEOUT','HTTP_EOF','HTTP_SOCKET','HTTP_HEADER'):
    l=runtime();l.globals().reason=reason
    l.execute('''
    local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
    port.prepare=function()return false,reason end
    assert(not m:prepare());local s=m:status();local r=s.retries[s.job.hash]
    assert(r.count==1 and r.permanent==(reason=='HTTP_HEADER'))
    ''')
print('PASS detailed transport causes preserve bounded retry class; malformed response remains permanent')
