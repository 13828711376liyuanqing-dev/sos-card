"""SAM | 2026-10-29 11:47 +08:00 | Python twin of .claude/skills/yp001-gr-jlink-deploy/scripts/gr_cli.ps1 (PowerShell is unavailable in this session):
send each GR CLI command on the GR port (auto-detected) (115200 8N1, CRLF) and print everything received within the wait window. CAT1 passthrough needs ~8 s.
Usage: python gr_cli.py [--wait-ms 3000] [--port COMx] [--log file] "cmd1" "cmd2" ..."""
import argparse
import time
import serial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('commands', nargs='+')
    ap.add_argument('--wait-ms', type=int, default=3000)
    ap.add_argument('--port', default=None, help='GR serial port; default: YP_GR_PORT or auto-detect')
    ap.add_argument('--log')
    a = ap.parse_args()
    from gr_port import pick  # SAM | 2026-11-09 | the COM number changes: never hard-coded
    a.port = pick(a.port)
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
