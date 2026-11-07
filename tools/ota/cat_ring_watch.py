"""SAM | 2026-10-29 16:27 +08:00 | Read-only J-Link watcher for a CAT1 stage while GR refuses cat_at: every --sec it dumps GR's CAT1 RX ring
(s_cat_diag_rx, address from the GR 1.5.1 AXF) plus the GR owner (via gr_ota_probe), and prints only new OTA_CTL op/phase pairs, the CAT1
version in its hello, and owner changes. Never halts the core, never writes, never touches a serial port.
Usage: python cat_ring_watch.py [--sec 30] [--max-min 30] [--ring 0x2001CACC]"""
import argparse, json, re, subprocess, sys, tempfile, time
from datetime import datetime
from pathlib import Path

JLINK = r'C:\Program Files\SEGGER\JLink\JLink.exe'
PROBE = Path(__file__).with_name('gr_ota_probe.py')


def ring(addr):
    with tempfile.TemporaryDirectory() as t:
        f = Path(t, 'r.bin'); c = Path(t, 'c.jlink')
        c.write_text(f'savebin {f.as_posix()},{addr},0x1000\nexit\n')
        subprocess.run([JLINK, '-NoGui', '1', '-ExitOnError', '1', '-device', 'CORTEX-M4', '-if', 'SWD', '-speed', '4000', '-autoconnect', '1',
                        '-CommandFile', str(c)], capture_output=True)
        return f.read_bytes() if f.exists() else b''


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--sec', type=float, default=30); ap.add_argument('--max-min', type=float, default=30)
    ap.add_argument('--ring', default='0x2001CACC'); ap.add_argument('--counts', action='store_true'); a = ap.parse_args()
    seen, owner, end = set(), None, time.time() + a.max_min * 60
    say = lambda s: print(datetime.now().strftime('%H:%M:%S'), s, flush=True)
    while time.time() < end:
        b = ring(a.ring)
        # SAM | 2026-10-29 17:40 +08:00 | Count frames per poll too: dedup alone hid whether CAT1 kept its unarmed QUERY cadence (wrong 16:34 conclusion).
        say(f'ring QUERY={len(re.findall(rb"\"op\":\"QUERY\"", b))} CAT_PROOF={len(re.findall(rb"\"op\":\"CAT_PROOF\"", b))} T151K={len(re.findall(rb"\[T151K\]", b))}') if a.counts else None
        for m in re.finditer(rb'OTA_CTL=\{[\x20-\x7e]*?\}', b):
            j = m.group().decode()
            op = re.search(r'"op":"(\w+)"', j); ph = re.search(r'"phase":"(\w+)"', j); off = re.search(r'"offset":(\d+)', j)
            key = (op and op.group(1), ph and ph.group(1), off and off.group(1))
            if key not in seen: seen.add(key); say(f'CAT1 OTA_CTL op={key[0]} phase={key[1]} offset={key[2]}')
        # SAM | 2026-10-29 17:08 +08:00 | Receiver revision 11 reports a stuck CAT1 rebuild as a plain [T151K] line.
        for m in re.finditer(rb'\[T151K\] [ -~]{1,80}', b):
            k = ('diag', m.group().decode())
            if k not in seen: seen.add(k); say('CAT1 ' + k[1])
        for m in re.finditer(rb'"product_build_version":"([\d.]+)"', b):
            k = ('ver', m.group(1).decode())
            if k not in seen: seen.add(k); say('CAT1 hello product_build_version=' + k[1])
        try:
            r = json.loads(subprocess.run([sys.executable, str(PROBE)], capture_output=True, text=True, timeout=120).stdout)
            top = max(r['owner'], key=lambda o: o['generation'])
            o = (top['generation'], top['phase'], top['target'], top['outcome'], top['actual'], r['halted'])
        except Exception as e:
            o = ('PROBE_ERROR', type(e).__name__)
        if o != owner: owner = o; say(f'GR owner gen/phase/target/outcome/actual/halted = {o}')
        if len(o) > 2 and o[1] == 'COMPLETE' and o[2] == 'CAT1': say('END CAT1 owner COMPLETE'); return
        time.sleep(a.sec)
    say('END timeout')


if __name__ == '__main__':
    main()
