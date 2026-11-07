"""SAM | 2026-11-06 +08:00 | Bench diagnosis of the OTA HTTP request shape (needs the diag4 receiver, which has `cat_at HTTP_VAR=`).
For each variant: set it, send `cat_at OTA_TRIAL=<url>` in the SAME session (the variable lives in RAM, a reboot clears it), and print
the `[OTA_HTTP]` lines and the trial result. Stops at the first variant that really starts the OTA (WAIT_GR).
Usage: YP_GR_PORT=COM30 python http_variants.py <url.txt> [variant ...]   default order: norange close http10 bare identity default"""
import os
import re
import sys
import time
import serial

port = os.environ.get('YP_GR_PORT', 'COM30')
url = open(sys.argv[1], encoding='utf-8').read().strip()
variants = sys.argv[2:] or ['norange', 'close', 'http10', 'bare', 'identity', 'default']
s = serial.Serial(port, 115200, timeout=0.2)


def talk(cmd, seconds, stop=None):
    s.write((cmd + '\r\n').encode())
    end, out = time.time() + seconds, ''
    while time.time() < end:
        out += s.read(4096).decode('utf-8', 'replace')
        if stop and re.search(stop, out):
            break
    return out


def lines(out):
    keep = []
    for l in out.splitlines():
        if 'parse ok' in l or not l.strip():
            continue
        if any(k in l for k in ('OTA_HTTP]', 'OTA_TRIAL]', 'OTA_RX]', 'HTTP_VAR', 'rail_request=off')):
            keep.append(l.strip()[:150])
    return keep


def ensure_up():
    """GR cuts an idle CAT1 after ~60 s: make sure it answers (power it on again if not) before each variant."""
    for _ in range(3):
        if 'FOTA_STATUS]' in talk('at FOTA_STATUS', 12, r'FOTA_STATUS\]\s+OTA_IO'):
            return True
        talk('cat1_power on', 3)
        talk('cat1_power key', 3)
        talk('', 50, r'MQTT_ENV\]\s+SUBSCRIBING')
    return False


try:
    for v in variants:
        if not ensure_up():
            print('CAT1 does not answer, stopping', flush=True)
            break
        out = talk('cat_at HTTP_VAR=' + v, 6, r'HTTP_VAR=')
        print('==', v, '|', [x for x in lines(out) if 'HTTP_VAR=' in x][-1:], flush=True)
        out = talk('cat_at OTA_TRIAL=' + url, 40, r'OTA_TRIAL\]\s+OTA_TRIAL=\S+')
        for l in lines(out):
            print('  ', l, flush=True)
        if 'WAIT_GR' in out:
            print('!! OTA STARTED with variant', v, flush=True)
            break
        time.sleep(3)
finally:
    s.close()
