"""SAM | 2026-10-26 +08:00 | A peer's timely RELEASE ends Flash execution, but physical ACK completion still owns UART; no device retries."""
from test_uart_flash_window import runtime

def release_before_deadline():
    runtime().execute('''
assert(ota_uart_send(frame));pump();sent()
feed(quiet(240));pump();sent()
clock=2999;feed(quiet(242))
clock=3001;pump()
assert(not ota_uart_faulted(),'TIMELY_RELEASE_MISCLASSIFIED_AS_FLASH_TIMEOUT')
assert(ota_uart_owned(),'RELEASE_ACK_MUST_STILL_OWN_UART')
sent();assert(not ota_uart_faulted())
''')

def callback_crosses_deadline():
    runtime().execute('''
assert(ota_uart_send(frame));pump();sent()
feed(quiet(240));pump();sent()
clock=2999;feed(quiet(242));pump()
clock=3002;pump()
assert(not ota_uart_faulted(),'PHYSICAL_RELEASE_ACK_CROSSED_OLD_FLASH_DEADLINE')
sent();assert(not ota_uart_faulted())
''')

def fail_closed():
    for received in ('', 'feed(quiet(242,2))', "feed(quiet(242,1,0,string.rep('z',16)))"):
        runtime().execute('''
assert(ota_uart_send(frame));pump();sent();feed(quiet(240));pump();sent()
clock=2999;'''+received+'''
clock=3001;pump();assert(ota_uart_faulted(),'MISSING_OR_UNMATCHED_RELEASE_BYPASSED_TIMEOUT')
''')
    runtime().execute('''
assert(ota_uart_send(frame));pump();sent();feed(quiet(240));pump();sent()
clock=2999;feed(quiet(242));pump()
clock=5000;pump();assert(ota_uart_faulted(),'MISSING_PHYSICAL_ACK_COMPLETION_DID_NOT_STOP')
local found=false;for _,e in ipairs(events)do if e[1]=='OTA_UART_FAULT' and e[2]=='UART_SENT_TIMEOUT' then found=true end end
assert(found,'WRONG_RELEASE_ACK_TIMEOUT')
''')
    runtime().execute('''
assert(ota_uart_send(frame));pump();sent();feed(quiet(240));pump();sent()
clock=3001;feed(quiet(242));pump();sent()
assert(ota_uart_faulted(),'LATE_RELEASE_MUST_NOT_ERASE_EXPIRED_FLASH_LEASE')
''')

if __name__=='__main__':
    release_before_deadline();callback_crosses_deadline();fail_closed()
    print('PASS timely RELEASE/late ACK callback; missing/wrong RELEASE and missing sent callback still fail closed')
