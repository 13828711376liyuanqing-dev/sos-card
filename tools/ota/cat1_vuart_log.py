"""SAM | 2026-10-29 19:22 +08:00 | PC-side log of the CAT1 USB virtual serial (uart.VUART_0). The CAT1 receiver writes plain-text
[T151K] diagnostics and a 10 s beacon there, so the CAT1 install is visible without Luatools decoding or GR forwarding. Read-only.
Listens on every given port (VUART number not yet known: default COM21 and COM23; COM22 is the binary trace port) and appends every text
line with time and port to --log; prints only [T151K]/[OTA] lines. Reopens a port after a CAT1 reboot.
Usage: python cat1_vuart_log.py --log logs/x.txt [--ports COM21,COM23] [--min 60]"""
import argparse
import time
from datetime import datetime
import serial


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--log', required=True); ap.add_argument('--ports', default='COM21,COM23')
    ap.add_argument('--min', type=float, default=60); a = ap.parse_args()
    ports = {p: None for p in a.ports.split(',')}; bufs = {p: b'' for p in ports}; end = time.time() + a.min * 60; retry = {}
    with open(a.log, 'a', encoding='utf-8', buffering=1) as w:
        def note(p, s):
            line = datetime.now().strftime('%H:%M:%S ') + p + ' ' + s
            w.write(line + '\n')
            if '[T151K]' in s or '[OTA]' in s: print(line, flush=True)  # SAM | 2026-10-29 20:24 +08:00 | round-2 receiver tag [OTA]
        note('PC', 'VUART LOG start ports=' + a.ports)
        while time.time() < end:
            for p in ports:
                if ports[p] is None:
                    if time.time() < retry.get(p, 0): continue
                    try: ports[p] = serial.Serial(p, 115200, timeout=0); note('PC', p + ' opened')
                    except Exception: retry[p] = time.time() + 5; continue
                try: data = ports[p].read(4096)
                except Exception:
                    note('PC', p + ' lost (CAT1 reboot?)'); ports[p] = None; retry[p] = time.time() + 3; continue
                bufs[p] += data
                while b'\n' in bufs[p]:
                    raw, bufs[p] = bufs[p].split(b'\n', 1)
                    text = raw.rstrip(b'\r').decode('utf-8', 'replace')
                    if text.strip(): note(p, text[:300])
            time.sleep(0.1)
        note('PC', 'VUART LOG end')


if __name__ == '__main__':
    main()
