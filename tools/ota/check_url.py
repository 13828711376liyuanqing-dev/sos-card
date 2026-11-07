"""SAM | 2026-11-04 +08:00 | One-shot platform URL check for a whole-device OTA bundle; host only, never touches the board.
Downloads the bundle (MD5 vs the URL's md5= and the local package), probes Range / ETag / transfer mode / redirect /
idle close, then feeds the live server bytes through the device Lua reader: check_range_tcp.py when the server
honours Range, else check_sequential_tcp.py (streaming servers). The URL itself is never logged.
Usage: python check_url.py <url.txt> [--package <local zip>] [--out <dir>]"""
import argparse
import hashlib
import http.client
import json
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def request(parts, headers=None, limit=None):
    conn = http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=30)
    path = parts.path + ('?' + parts.query if parts.query else '')
    conn.request('GET', path, headers=headers or {})
    r = conn.getresponse()
    body = r.read() if limit is None else r.read(limit)
    hdr = {k.lower(): v for k, v in r.getheaders()}
    conn.close()
    return r.status, hdr, body


def idle_close_seconds(parts, wait_max=20):
    """Seconds an idle keep-alive connection stays open after a complete response ('>N' = still open after N s)."""
    s = socket.create_connection((parts.hostname, parts.port or 80), timeout=10)
    path = parts.path + ('?' + parts.query if parts.query else '')
    s.sendall(f'GET {path} HTTP/1.1\r\nHost: {parts.hostname}\r\nRange: bytes=0-0\r\n\r\n'.encode())
    s.settimeout(1)
    t0 = None
    try:
        while True:
            try:
                d = s.recv(65536)
            except socket.timeout:
                if t0 is None:
                    t0 = time.monotonic()
                if time.monotonic() - t0 > wait_max:
                    return f'>{wait_max}'
                continue
            if not d:
                return round(time.monotonic() - (t0 or time.monotonic()), 1)
            t0 = time.monotonic()
    finally:
        s.close()


def run_checker(name, url, archive, log):
    p = subprocess.run([sys.executable, str(HERE / name), '--archive', str(archive.resolve())], input=url + '\n',
                       capture_output=True, text=True, cwd=HERE, timeout=900)
    log.write_text(p.stdout + '\n--- stderr ---\n' + p.stderr, encoding='utf-8')
    tail = [l for l in p.stdout.splitlines() if l.strip()][-1:] or ['']
    result = None
    try:
        result = json.loads(tail[0])
    except ValueError:
        pass
    return p.returncode, result, tail[0][:300]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('url_file', type=Path)
    ap.add_argument('--package', type=Path, help='local bundle zip that was uploaded')
    ap.add_argument('--out', type=Path)
    a = ap.parse_args()
    url = a.url_file.read_text(encoding='utf-8').strip().splitlines()[0].strip()
    parts = urlsplit(url)
    if parts.scheme != 'http' or not parts.hostname:
        raise SystemExit('HTTP_URL_REQUIRED (the device does not follow https or redirects)')
    out = a.out or a.url_file.parent / ('url_check_' + datetime.now().strftime('%H%M%S'))
    out.mkdir(parents=True, exist_ok=True)
    rep = {}
    want = (parse_qs(parts.query).get('md5') or [''])[0].lower()
    rep['url_md5_param'] = want or 'MISSING'

    t = time.monotonic()
    status, hdr, body = request(parts)
    rep['full'] = {'status': status, 'bytes': len(body), 'seconds': round(time.monotonic() - t, 1),
                   'content_length': hdr.get('content-length'), 'transfer_encoding': hdr.get('transfer-encoding'),
                   'etag': hdr.get('etag'), 'last_modified': hdr.get('last-modified'), 'location': hdr.get('location'),
                   'keep_alive': hdr.get('keep-alive'), 'server': hdr.get('server')}
    md5 = hashlib.md5(body).hexdigest()
    rep['md5'] = md5
    rep['md5_matches_url'] = md5 == want
    archive = out / 'dl.zip'
    archive.write_bytes(body)
    if a.package:
        local = a.package.read_bytes()
        rep['matches_local_package'] = local == body
    ok_basic = status == 200 and rep['md5_matches_url'] and rep.get('matches_local_package', True)

    st2, h2, b2 = request(parts, {'Range': 'bytes=1000-1999'})
    rep['range'] = {'status': st2, 'content_range': h2.get('content-range'), 'bytes': len(b2),
                    'exact': st2 == 206 and b2 == body[1000:2000] and h2.get('content-range') == f'bytes 1000-1999/{len(body)}'}
    st3, h3, _ = request(parts, {'Range': 'bytes=0-0'})
    rep['etag_stable'] = bool(hdr.get('etag')) and h3.get('etag') == hdr.get('etag')
    try:
        rep['idle_close_s'] = idle_close_seconds(parts)
    except OSError as e:
        rep['idle_close_s'] = 'error ' + type(e).__name__

    range_ok = rep['range']['exact'] and rep['etag_stable']
    rep['server_mode'] = 'HTTP_RANGE' if range_ok else 'SEQUENTIAL_STREAM'
    rep['device_checks'] = {}
    if ok_basic:
        # check_sequential_tcp.py requires the server to refuse Range, so each server mode has exactly one checker.
        for name in ['check_range_tcp.py' if range_ok else 'check_sequential_tcp.py']:
            code, result, tail = run_checker(name, url, archive, out / (name[:-3] + '.log'))
            rep['device_checks'][name] = {'exit': code, 'result': result if result is not None else tail}
    passed = ok_basic and rep['device_checks'] and all(
        v['exit'] == 0 and isinstance(v['result'], dict) and v['result'].get('passed') is True
        for v in rep['device_checks'].values())
    rep['PASSED'] = bool(passed)
    (out / 'report.json').write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    print('REPORT', out / 'report.json')
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
