"""SAM | 2026-10-29 18:57 +08:00 | Continuous read-only capture of GR's CAT1 RX ring (J-Link savebin, never halts/writes) into an append-only
text log: every new [T151K] line and every OTA_CTL op/phase change, with time. The 4 KiB ring is overwritten in ~20-30 s, so one-shot lines
(e.g. the boot diagnostic) are lost unless the ring is read faster than it wraps; this polls every --sec (default 4 s).
Usage: python cat_ring_capture.py --log logs/x.txt [--sec 4] [--min 6] [--ring 0x2001CACC]"""
import argparse, re, subprocess, tempfile, time
from datetime import datetime
from pathlib import Path

JLINK = r'C:\Program Files\SEGGER\JLink\JLink.exe'


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--log', required=True); ap.add_argument('--sec', type=float, default=4)
    ap.add_argument('--min', type=float, default=6); ap.add_argument('--ring', default='0x2001CACC'); a = ap.parse_args()
    seen, last, end = set(), None, time.time() + a.min * 60
    with tempfile.TemporaryDirectory() as t, open(a.log, 'a', encoding='utf-8', buffering=1) as w:
        f = Path(t, 'r.bin'); c = Path(t, 'c.jlink'); c.write_text(f'savebin {f.as_posix()},{a.ring},0x1000\nexit\n')
        note = lambda s: (w.write(datetime.now().strftime('%H:%M:%S ') + s + '\n'), print(datetime.now().strftime('%H:%M:%S ') + s, flush=True))
        note('CAPTURE start')
        while time.time() < end:
            subprocess.run([JLINK, '-NoGui', '1', '-ExitOnError', '1', '-device', 'CORTEX-M4', '-if', 'SWD', '-speed', '4000', '-autoconnect', '1',
                            '-CommandFile', str(c)], capture_output=True)
            b = f.read_bytes() if f.exists() else b''
            for m in re.finditer(rb'\[T151K\][\x20-\x7e]{0,140}', b):
                s = m.group().decode()
                if s not in seen: seen.add(s); note(s)
            ops = sorted(set((x.group(2).decode(), x.group(1).decode()) for x in re.finditer(rb'"phase":"(\w+)"[^}]*"op":"(\w+)"', b)))
            hello = re.findall(rb'"product_build_version":"([\d.]+)"', b)
            key = (tuple(ops), hello[-1].decode() if hello else None)
            if key != last: last = key; note(f'frames {list(key[0])} cat_version={key[1]}')
            time.sleep(a.sec)
        note('CAPTURE end')


if __name__ == '__main__':
    main()
