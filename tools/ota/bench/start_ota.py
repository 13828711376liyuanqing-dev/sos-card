import os  # SAM | 2026-11-04 +08:00 | GR CLI port from YP_GR_PORT (bench board moved to COM30), default COM26
# Power CAT1 up, wait until it is settled (cat1wait.settle), then send OTA_TRIAL at once. Usage: start_ota.py <urlfile> <log>
# Exit 0 only if OTA_TRIAL=WAIT_GR and the mandatory [OTA] LOG_CLEARED and [OTA_HOLD] on were seen; 2 otherwise.
import re, sys, time, serial
from cat1wait import settle
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), '..'))
from gr_port import pick  # SAM | 2026-11-09 | the COM number changes: never hard-coded
url = open(sys.argv[1]).read().strip(); log = open(sys.argv[2], 'w', encoding='utf-8')
buf = ''
def pump(sec, until=None, count=1):
    global buf
    end = time.time() + sec; seen = 0
    while time.time() < end:
        t = s.read(4096).decode('utf-8', 'replace')
        if t:
            log.write(t); log.flush(); buf += t
            if until:
                seen = buf.count(until)
                if seen >= count: return True
    return False
with serial.Serial(pick(), 115200, timeout=0.1) as s:
    time.sleep(0.3); s.read(65536)
    s.write(b'cat1_power reset\r\n')
    ok, buf = settle(s, log)
    if not ok:
        print('CAT1 not settled in 180 s; not sending'); sys.exit(1)
    s.write(('cat_at OTA_TRIAL=' + url + '\r\n').encode()); log.write('\n>>> OTA_TRIAL sent\n')
    pump(40)
print('POWER events:', buf.count('[CAT1 POWER] rail_request=off'))
for l in buf.splitlines():
    if any(k in l for k in ('OTA_TRIAL', 'OTA_HOLD', '[OTA', 'PWR', 'deny', 'rail_request=off')): print(l[:200])
# SAM | 2026-11-04 +08:00 | Mandatory check (user rule): the device must delete its app logs before taking the OTA command
# ("[OTA] LOG_CLEARED <bytes>", update.lua). Missing line = check failed, exit 2; the operator stops and investigates.
after = buf[buf.find('>>> OTA_TRIAL sent'):] if '>>> OTA_TRIAL sent' in buf else buf
m = re.search(r'\[OTA\] LOG_CLEARED (\d+)', after)
started = 'OTA_TRIAL=WAIT_GR' in after
# SAM | 2026-11-04 +08:00 | Mandatory check 2: GR itself prints "[OTA_HOLD] on" when it takes the CAT1 power lock.
hold = '[OTA_HOLD] on' in after
print('MUST OTA_HOLD:', 'PASS (GR keeps CAT1 powered)' if hold else 'FAIL (GR did not print [OTA_HOLD] on)')
print('MUST LOG_CLEARED:', ('PASS ' + m.group(1) + ' B') if m else 'FAIL (no [OTA] LOG_CLEARED after OTA_TRIAL)')
print('OTA_TRIAL:', 'WAIT_GR' if started else 'NOT STARTED')
sys.exit(0 if m and started and hold else 2)
