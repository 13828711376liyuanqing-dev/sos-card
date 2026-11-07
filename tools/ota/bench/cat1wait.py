# Wait until CAT1 is up and stays up: an MQTT connect marker, then 12 s with no rail off (GR may reboot or double-reset CAT1).
import time
MARKS = ('[MQTT_ENV] CONNECTED', 'state=CONNECTED')
OFF = 'rail_request=off'


def settle(s, log, limit=180, quiet=12):
    buf = ''; end = time.time() + limit; up_at = None
    while time.time() < end:
        t = s.read(4096).decode('utf-8', 'replace')
        if t:
            log.write(t); log.flush(); buf += t
            for line in t.splitlines():
                if OFF in line: up_at = None
                elif any(m in line for m in MARKS) and up_at is None: up_at = time.time()
        if up_at and time.time() - up_at >= quiet:
            return True, buf
    return False, buf
