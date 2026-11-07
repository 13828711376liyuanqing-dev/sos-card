"""SAM | 2026-10-27 +08:00 | A 1.2s grant scheduling delay plus the existing 2s GR release retry must not consume a 3s Flash lease before it starts."""
from test_uart_flash_window import runtime

def valid_grant_and_release_retry():
    runtime().execute('''
assert(ota_uart_send(frame));pump();sent()
feed(quiet(240))
-- Grant ACK is actually issued within GR's 2s handshake budget, not at request reception.
clock=1200;pump();assert(w.decode(written[#written]).type==241);sent()
-- GR completes its 15ms operation, but the first RELEASE is lost. Existing GR replay arrives after 2s.
clock=1215;feed(ack)
clock=3001;pump();assert(not ota_uart_faulted(),'FLASH_DEADLINE_STARTED_BEFORE_GRANT_WRITE')
clock=3216;feed(quiet(242));pump();sent()
assert(not ota_uart_faulted(),'VALID_GR_RELEASE_RETRY_FAILED')
''')

def actual_lease_expiry():
    runtime().execute('''
assert(ota_uart_send(frame));pump();sent();feed(quiet(240))
clock=1200;pump();sent()
clock=4201;pump();assert(ota_uart_faulted(),'REAL_FLASH_LEASE_EXPIRY_BYPASSED')
''')

if __name__=='__main__':
    valid_grant_and_release_retry();actual_lease_expiry()
    print('PASS granted lease starts at grant write; delayed grant + bounded GR release retry succeeds, real 3s lease expiry still stops')
