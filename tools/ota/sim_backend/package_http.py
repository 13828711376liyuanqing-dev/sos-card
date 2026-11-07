"""SAM | 2026-10-21 +08:00 | Immutable loopback test artifact service; no arbitrary filesystem access."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re

LIMIT = 16*1024*1024

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path != '/packages/'+self.server.digest:
            self.send_error(404)
            return
        data = self.server.image
        total = len(data)
        tag = '"'+self.server.digest+'"'
        start, end, status = 0, total-1, 200
        requested = self.headers.get('Range')
        if requested and self.headers.get('If-Range', tag) == tag:
            match = re.fullmatch(r'bytes=(\d{1,10})-(\d{1,10})', requested)
            if not match:
                self.send_error(416)
                return
            start, end = map(int, match.groups())
            if start>end or start>=total or end>=total:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{total}')
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header('Content-Type','application/octet-stream')
        self.send_header('Content-Length', str(end-start+1))
        self.send_header('ETag',tag)
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Cache-Control','no-transform')
        if status==206:
            self.send_header('Content-Range',f'bytes {start}-{end}/{total}')
        self.end_headers()
        self.wfile.write(data[start:end+1])

class PackageServer(ThreadingHTTPServer):
    def __init__(self, image, port=0):
        if not isinstance(image, bytes) or not 0<len(image)<=LIMIT:
            raise ValueError('empty/oversized test artifact')
        self.image = image
        self.digest = hashlib.sha256(image).hexdigest()
        super().__init__(('127.0.0.1',port), Handler)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file',required=True,type=Path)
    parser.add_argument('--port',type=int,default=8766)
    args = parser.parse_args()
    # Bound reads before allocation; snapshot bytes remain immutable if source changes.
    with args.file.open('rb') as stream:
        image = stream.read(LIMIT+1)
    server = PackageServer(image,args.port)
    print(f'http://127.0.0.1:{server.server_port}/packages/{server.digest}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
