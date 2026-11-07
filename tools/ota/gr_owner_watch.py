"""SAM | 2026-10-29 14:50 +08:00 | Token-saving J-Link-only watcher: every --sec runs gr_ota_probe (read-only, never halts) and prints only when the
GR owner (generation/phase/target/outcome/actual) or Boot journal state changes. Touches no serial port, so it cannot disturb GR health
windows or a CAT1 install. Ends when the owner reaches COMPLETE for --target, or after --max-min.
Usage: python gr_owner_watch.py [--sec 60] [--max-min 60] [--target CAT1]"""
import argparse, json, subprocess, sys, time
from datetime import datetime
from pathlib import Path

PROBE = Path(__file__).with_name('gr_ota_probe.py')


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--sec', type=float, default=60); ap.add_argument('--max-min', type=float, default=60)
    ap.add_argument('--target', default='CAT1'); a = ap.parse_args()
    last, end = None, time.time() + a.max_min * 60
    while time.time() < end:
        try:
            r = json.loads(subprocess.run([sys.executable, str(PROBE)], capture_output=True, text=True, timeout=120).stdout)
            top = max(r['owner'], key=lambda o: o['generation']) if r['owner'] else {}
            key = (top.get('generation'), top.get('phase'), top.get('target'), top.get('outcome'), top.get('actual'),
                   r['journal'][-1]['state'] if r['journal'] else None, r['halted'])
        except Exception as e:
            key = ('PROBE_ERROR', type(e).__name__)
        if key != last:
            print(datetime.now().strftime('%H:%M:%S'), 'owner gen/phase/target/outcome/actual, boot, halted =', key, flush=True); last = key
            if len(key) > 4 and key[1] == 'COMPLETE' and key[2] == a.target:
                print('END owner COMPLETE for', a.target, flush=True); return
        time.sleep(a.sec)
    print('END timeout', flush=True)


if __name__ == '__main__':
    main()
