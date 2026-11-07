import os  # SAM | 2026-11-04 +08:00 | GR CLI port from YP_GR_PORT (bench board moved to COM30), default COM26
# Power CAT1 up on COM26, wait until it is settled (cat1wait.settle), then run GR CLI commands.
# Usage: boot_then.py <log> [--no-reset] "cmd1" "cmd2" ...   (each command gets 10 s)
import sys, time, serial
from cat1wait import settle
log = open(sys.argv[1], 'w', encoding='utf-8')
args = sys.argv[2:]
reset = True
if args and args[0] == '--no-reset':
    reset = False
    args = args[1:]
buf = ''


def pump(s, sec, until=None, count=1):
    global buf
    end = time.time() + sec
    while time.time() < end:
        t = s.read(4096).decode('utf-8', 'replace')
        if t:
            log.write(t); log.flush(); buf += t
            if until and buf.count(until) >= count:
                return True
    return False


with serial.Serial(os.environ.get('YP_GR_PORT', 'COM26'), 115200, timeout=0.1) as s:
    time.sleep(0.3); s.read(65536)
    if reset:
        s.write(b'cat1_power reset\r\n')
        ok, buf = settle(s, log)
        if not ok:
            print('CAT1 not settled in 180 s; not sending'); sys.exit(1)
    for c in args:
        log.write('\n>>> ' + c[:60] + '\n'); s.write((c + '\r\n').encode())
        pump(s, 10)
print('rail_off events:', buf.count('rail_request=off'))
keys = ('[BUSINESS]', 'FOTA_STATUS]', 'OTA_FS total', 'OTA_TRIAL', 'OTA_HOLD', 'rail_request=off', 'deny', 'Lua', 'error', 'clean')
for line in buf.splitlines():
    if any(k in line for k in keys) and 'parse ok' not in line:
        print(line[:200])
