#!/usr/bin/env python3
"""SAM | 2026-11-06 +08:00 | Send the SAME request bytes the YP001 device sends (raw socket, only the Python standard library) and report,
per request, what the server did. Run it from any network and send the printed table back.

  python device_like_probe.py "<download url, with ?appId=...&signature=...&md5=... if you have it>" [--count 20] [--chunk 16384] [--shape device|official|plain]

shape:
  device    what the device sends today:  GET .. HTTP/1.1 | Host | Range | Connection: keep-alive | Accept-Encoding: identity
  official  the platform client's header set (tkhos_file_upload.py): Host | BusinessId | Timestamp | AppId | Request_node_ip | Accept | Range
  plain     Host | Range only
Each request uses a NEW TCP connection (like the device); --keepalive reuses one connection for all requests instead.
Result columns: n, range asked, status line, response-header bytes, body bytes received / expected, seconds, how it ended.
"""
import argparse
import socket
import sys
import time
import uuid
from urllib.parse import urlsplit


def build(shape, host, path, rng):
    if shape == 'official':
        return ('GET %s HTTP/1.1\r\nHost: %s\r\nBusinessId: %s\r\nTimestamp: %d\r\nAppId: ccrc-customer-personupload\r\n'
                'Request_node_ip: 127.0.0.1\r\nAccept: */*\r\nRange: %s\r\n\r\n'
                % (path, host, uuid.uuid4().hex, int(time.time() * 1000), rng)).encode()
    if shape == 'plain':
        return ('GET %s HTTP/1.1\r\nHost: %s\r\nRange: %s\r\n\r\n' % (path, host, rng)).encode()
    return ('GET %s HTTP/1.1\r\nHost: %s\r\nRange: %s\r\nConnection: keep-alive\r\nAccept-Encoding: identity\r\n\r\n'
            % (path, host, rng)).encode()


def read_response(sock, timeout):
    """Returns (status line, header bytes, body bytes got, body bytes expected, how it ended)."""
    sock.settimeout(timeout)
    buf = b''
    try:
        while b'\r\n\r\n' not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                return ('(none)', len(buf), 0, 0, 'closed before the response headers (got %d bytes)' % len(buf))
            buf += chunk
    except socket.timeout:
        return ('(none)', len(buf), 0, 0, 'timeout waiting for headers')
    except OSError as exc:
        return ('(none)', len(buf), 0, 0, 'error %s' % exc)
    head, _, body = buf.partition(b'\r\n\r\n')
    lines = head.decode('latin-1').split('\r\n')
    status = lines[0]
    length = 0
    for ln in lines[1:]:
        if ln.lower().startswith('content-length:'):
            length = int(ln.split(':', 1)[1].strip())
    try:
        while len(body) < length:
            chunk = sock.recv(65536)
            if not chunk:
                return (status, len(head) + 4, len(body), length, 'closed during the body')
            body += chunk
    except socket.timeout:
        return (status, len(head) + 4, len(body), length, 'timeout during the body')
    except OSError as exc:
        return (status, len(head) + 4, len(body), length, 'error %s' % exc)
    return (status, len(head) + 4, len(body), length, 'ok' if len(body) == length else 'short body')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('url')
    ap.add_argument('--count', type=int, default=20)
    ap.add_argument('--chunk', type=int, default=16384)
    ap.add_argument('--shape', choices=('device', 'official', 'plain'), default='device')
    ap.add_argument('--keepalive', action='store_true', help='reuse one TCP connection for every request')
    ap.add_argument('--timeout', type=float, default=15.0)
    a = ap.parse_args()

    u = urlsplit(a.url)
    if u.scheme != 'http':
        sys.exit('only http:// URLs (the device downloads over plain http)')
    host = u.netloc
    port = u.port or 80
    path = (u.path or '/') + ('?' + u.query if u.query else '')
    ips = sorted({i[4][0] for i in socket.getaddrinfo(u.hostname, port, socket.AF_INET)})
    print('host %s resolves to %s ; shape=%s ; %s' % (u.hostname, ','.join(ips), a.shape,
                                                       'one keep-alive connection' if a.keepalive else 'new connection per request'))
    print('%3s %-18s %-22s %6s %9s %7s  %s' % ('n', 'range', 'status', 'hdrB', 'body', 'sec', 'result'))
    sock = None
    bad = 0
    for i in range(a.count):
        start = i * a.chunk
        rng = 'bytes=%d-%d' % (start, start + a.chunk - 1)
        t0 = time.time()
        try:
            if sock is None or not a.keepalive:
                if sock:
                    sock.close()
                sock = socket.create_connection((u.hostname, port), timeout=a.timeout)
            sock.sendall(build(a.shape, host, path, rng))
            status, hdr, got, want, end = read_response(sock, a.timeout)
        except OSError as exc:
            status, hdr, got, want, end = '(connect/send failed)', 0, 0, 0, str(exc)
            sock = None
        if end != 'ok':
            bad += 1
            if a.keepalive and sock:
                sock.close()
                sock = None
        print('%3d %-18s %-22s %6d %4d/%-4d %7.2f  %s' % (i + 1, rng, status[:22], hdr, got, want, time.time() - t0, end))
        if not a.keepalive and sock:
            sock.close()
            sock = None
        time.sleep(0.05)
    print('\n%d of %d requests failed.' % (bad, a.count))


if __name__ == '__main__':
    main()
