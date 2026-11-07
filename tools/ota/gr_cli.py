"""SAM | 2026-10-29 11:47 +08:00 | Python twin of .claude/skills/yp001-gr-jlink-deploy/scripts/gr_cli.ps1 (PowerShell is unavailable in this session):
send each GR CLI command on COM26 (115200 8N1, CRLF) and print everything received within the wait window. CAT1 passthrough needs ~8 s.
Usage: python gr_cli.py [--wait-ms 3000] [--port COM26] [--log file] "cmd1" "cmd2" ..."""
import argparse
import time
import serial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('commands', nargs='+')
    ap.add_argument('--wait-ms', type=int, default=3000)
    ap.add_argument('--port', default='COM26')
    ap.add_argument('--log')
    a = ap.parse_args()
    out = []
    with serial.Serial(a.port, 115200, timeout=0.1) as s:
        time.sleep(0.3); s.read(65536)
        for c in a.commands:
            out.append(f'\n>>> {c}\n'); s.write((c + '\r\n').encode())
            end = time.time() + a.wait_ms / 1000
            while time.time() < end:
                out.append(s.read(4096).decode('utf-8', 'replace'))
    text = ''.join(out)
    if a.log:
        open(a.log, 'w', encoding='utf-8').write(text)
    print(text)


if __name__ == '__main__':
    main()
