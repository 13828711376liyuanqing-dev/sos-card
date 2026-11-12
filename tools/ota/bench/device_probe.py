"""SAM | 2026-11-10 | Read the device in one go (GR command port, auto-detected): GR version, CAT1 version, OTA state, outbox, CAT1 file-system use.
Wakes CAT1 first (it is switched off by GR when idle), waits until it stays up, then asks. Read-only apart from that one CAT1 reset.
The GR port must be free (stop keep_cat1.py first).
Usage: python device_probe.py [--no-reset] [--json]      (module: device_probe.probe(reset=True) -> dict)"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import serial  # noqa: E402
from cat1wait import settle  # noqa: E402
from gr_port import pick  # noqa: E402

COMMANDS = ('fw_version', 'cat_at AT_INFO', 'cat_at FOTA_STATUS', 'cat_at OTA_FS')


def norm(v):
    """001.005.031 or 1.5.31 -> 1.5.31"""
    m = re.match(r'^(\d+)\.(\d+)\.(\d+)$', v or '')
    return '.'.join(str(int(x)) for x in m.groups()) if m else None


def parse(text):
    """Pull the facts out of the raw GR log text."""
    d = {}
    m = re.search(r'\[FW_VERSION\] YP001_FW\|GR5526\|(\d{3}\.\d{3}\.\d{3})\|(\d+)\|END product=([\d.]+)', text)
    if m:
        d['gr_version'], d['gr_build'] = norm(m.group(1)), int(m.group(2))
    m = re.search(r'\[AT_INFO\]\s+LuatOS Ver:\s+(\d{3}\.\d{3}\.\d{3})', text)
    if m:
        d['cat1_version'] = norm(m.group(1))
    m = re.search(r'\[AT_INFO\]\s+IMEI:\s+(\d+)', text)
    if m:
        d['imei'] = m.group(1)
    m = re.search(r'\[FOTA_STATUS\]\s+(IDLE|[A-Z_]+)\s*$', text, re.M)
    if m:
        d['fota_state'] = m.group(1)
    m = re.search(r'OTA_OUTBOX=(\d+)', text)
    if m:
        d['outbox'] = int(m.group(1))
    m = re.search(r'OTA_IO=(\S+) TRIAL=(\S+)', text)
    if m:
        d['ota_io'], d['trial'] = m.group(1), m.group(2)
    m = re.search(r'OTA_FS total=(\d+) used=(\d+) block=(\d+)', text)
    if m:
        total, used, block = map(int, m.groups())
        d['fs_total'], d['fs_used'], d['fs_block'], d['fs_free'] = total, used, block, (total - used) * block
    return d


def probe(reset=True, log_path=None):
    log = open(log_path, 'w', encoding='utf-8') if log_path else open(os.devnull, 'w')
    buf = ''
    with serial.Serial(pick(), 115200, timeout=0.1) as s:
        time.sleep(0.3)
        s.read(65536)
        if reset:
            s.write(b'cat1_power reset\r\n')
            ok, buf = settle(s, log)
            if not ok:
                raise RuntimeError('CAT1 没有在 180 秒内稳定上线，没有发命令（先看电池和保电）')
        for c in COMMANDS:
            log.write('\n>>> ' + c + '\n')
            s.write((c + '\r\n').encode())
            end = time.time() + 10
            while time.time() < end:
                t = s.read(4096).decode('utf-8', 'replace')
                if t:
                    log.write(t)
                    buf += t
    log.close()
    return parse(buf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-reset', action='store_true')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    d = probe(reset=not a.no_reset)
    if a.json:
        print(json.dumps(d, ensure_ascii=False))
        return
    print('GR   版本', d.get('gr_version'), 'build', d.get('gr_build'))
    print('CAT1 版本', d.get('cat1_version'), '  IMEI', d.get('imei'))
    print('OTA  状态', d.get('fota_state'), ' OUTBOX', d.get('outbox'), ' IO', d.get('ota_io'), ' TRIAL', d.get('trial'))
    if 'fs_free' in d:
        print('CAT1 文件区 已用', d['fs_used'], '块 / 共', d['fs_total'], '块，可用', d['fs_free'], '字节')


if __name__ == '__main__':
    main()
