"""SAM | 2026-10-29 11:49 +08:00 | GR-port OTA monitor (Python; PowerShell unavailable): optionally send one start command, then append every
non-noise line with a timestamp to the log and poll CAT1 FOTA_STATUS at a fixed interval. Read-only apart from the optional start command.
Usage: python ota_monitor.py --log file [--start "cat_at ..."] [--minutes 5] [--poll-sec 60] [--port COMx]"""
import argparse
import re
import time
from datetime import datetime
import serial

NOISE = re.compile(r'^\[BAT\]|^\[CHG\]|EPD|^\s*>?\s*$')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--log', required=True)
    ap.add_argument('--start')
    ap.add_argument('--minutes', type=float, default=5)
    ap.add_argument('--poll-sec', type=float, default=60)
    ap.add_argument('--port', default=None, help='GR serial port; default: YP_GR_PORT or auto-detect')
    a = ap.parse_args()
    from gr_port import pick  # SAM | 2026-11-09 | the COM number changes: never hard-coded
    a.port = pick(a.port)
    with serial.Serial(a.port, 115200, timeout=0.1) as s, open(a.log, 'a', encoding='utf-8', buffering=1) as w:
        note = lambda t: w.write(datetime.now().strftime('%H:%M:%S.%f')[:-3] + ' ' + t + '\n')
        time.sleep(0.3); s.read(65536)
        if a.start:
            note('>>> ' + a.start); s.write((a.start + '\r\n').encode())
        end = time.time() + a.minutes * 60; nxt = time.time() + a.poll_sec; buf = ''
        while time.time() < end:
            buf += s.read(4096).decode('utf-8', 'replace')
            while '\n' in buf:
                line, buf = buf.split('\n', 1); line = line.rstrip('\r')
                if not NOISE.search(line):
                    note(line)
            if time.time() >= nxt:
                note('>>> cat_at FOTA_STATUS'); s.write(b'cat_at FOTA_STATUS\r\n'); nxt = time.time() + a.poll_sec


if __name__ == '__main__':
    main()
