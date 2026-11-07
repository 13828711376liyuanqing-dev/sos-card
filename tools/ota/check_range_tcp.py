# SAM | 2026-11-03 +08:00 | Range variant of check_sequential_tcp.py for the new backend (nginx, 206 + strong ETag):
# the device Lua bundle reader must take the HTTP Range path, verify the whole-archive MD5, signature and both component digests.
"""SAM | 2026-10-24 +08:00 | Feed raw HTTP TCP bytes through actual Lua chunked and sequential ZIP code; host only, never flash or activate."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys
import time
from datetime import datetime
from urllib.parse import urlsplit
import test_zip_bundle as fixture_module

ROOT = Path(__file__).resolve().parents[2]

def main():
    parser = argparse.ArgumentParser(description='Read authenticated HTTP URL from stdin; never log the URL.')
    parser.add_argument('--archive', type=Path, required=True)
    args = parser.parse_args()
    url = sys.stdin.readline().strip()
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise SystemExit('HTTP_URL_REQUIRED')
    output = ROOT / 'logs/ota_sequential_20261024' / ('live_' + datetime.now().strftime('%H%M%S_%f'))
    output.mkdir(parents=True)
    snapshot = lambda: {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / 'Air780EGH').glob('*.lua')}
    before = snapshot()
    started = time.monotonic()
    report = dict(mode='RAW_PUBLIC_TCP_TO_HOST_LUA_SEQUENTIAL', host=parsed.hostname,
                  url_sha256=hashlib.sha256(url.encode()).hexdigest(), device_actions=False,
                  cellular_tested=False, native_modem_tested=False, installation_accepted=False,
                  requests=0, closed=0, max_native_read=0, wire_bytes=0)
    connection = None
    f = fixture_module.BundleTests()
    import os
    os.environ['YP_OTA_TEST_ARCHIVE'] = str(args.archive.resolve())
    f.setUp()
    lua, g = f.lua, f.lua.globals()
    def connect(host, port):
        nonlocal connection
        assert host.decode() == parsed.hostname and port == (parsed.port or 80)
        connection = socket.create_connection((host.decode(), port), timeout=10)
        connection.setblocking(False)
        report['requests'] += 1
        return True, True
    def send(data):
        connection.setblocking(True)
        connection.settimeout(10)
        connection.sendall(data)
        connection.setblocking(False)
        return True, False, True
    def read(limit):
        assert 1 <= limit <= 512
        report['max_native_read'] = max(report['max_native_read'], limit)
        try:
            data = connection.recv(limit)
        except BlockingIOError:
            return True, b''
        report['wire_bytes'] += len(data)
        return bool(data), data
    def close():
        nonlocal connection
        if connection is not None:
            connection.close()
            connection = None
            report['closed'] += 1
    g.tcp_connect, g.tcp_send, g.tcp_read, g.tcp_close = connect, send, read, close
    g.tcp_clock = lambda: int((time.monotonic()-started)*1000)
    g.tcp_wait = lambda ms: time.sleep(ms/1000)
    g.py_begin = lambda kind: hashlib.sha256() if kind == b'SHA256' else hashlib.md5()
    g.input[b'url'] = url.encode()
    try:
        lua.execute(b'''
        local net={ON_LINE=1,TX_OK=2,EVENT=3,CLOSED=4,
          create=function()return {}end,config=function()return true end,
          connect=function(_,h,p)return tcp_connect(h,p)end,tx=function(_,data)return tcp_send(data)end,
          rx=function(_,b,flag,limit)
           assert(flag==0 and #b.data==0);local ok,data=tcp_read(limit);b.data=b.data..data;return ok,#data
          end,close=function()tcp_close()end,release=function()end}
        local buffers={create=function()return {data='',clear=function(self)self.data=string.rep('\0',#self.data)end,del=function(self)self.data=''end,
          query=function(self,offset,n)return self.data:sub(offset+1,offset+n)end}end}
        p.can_read=function()return tcp_clock()<240000 end
        local receiver=assert(require('ota_http_range').new_diagnostic({socket=net,zbuff=buffers,
          native_rx_limit_verified=false,now_ms=function()return tcp_clock()end,
          wait=function(n)tcp_wait(n)end,can_read=p.can_read}))
        p.http_get=receiver.http_get;p.open_stream=receiver.open_stream
        local function denied()error('PRODUCTION_CALLBACK_IN_DIAGNOSTIC',0)end
        p.owns=denied;p.owns_bundle=denied;p.completed=denied;p.free_bytes=denied
        p.save_archive_proof=denied;p.archive_verified=denied
        r,err=require('ota_bundle').open_diagnostic(p,input);assert(r,tostring(err))
        local v
        for n=1,400 do local ok,why=r:preflight_step();assert(ok,tostring(why));v=why;if why=='VERIFIED' then break end end
        assert(v=='VERIFIED','preflight not verified')
        local done=false
        for n=1,600 do
         local ok,info=r:diagnostic_step();assert(ok,tostring(info))
         if info.stage=='COMPLETE' then done=true;break end
        end
        assert(done);summary=r:summary();r:close()
        ''')
        summary = g.summary
        report.update(passed=True, range_used=True, whole_md5_verified=True,
                      signature_verified=True, gr_digest_verified=True, cat_digest_verified=True,
                      metadata_bytes=summary[b'metadata_bytes'], archive_bytes=summary[b'size'],
                      transport_mode=summary[b'transport_mode'].decode(),
                      restart_from_zero=summary[b'network_restart_from_zero'], etag_seen=bool(summary[b'etag']),
                      archive_md5=hashlib.md5(f.data).hexdigest(),
                      archive_sha256=hashlib.sha256(f.data).hexdigest())
        assert report['metadata_bytes'] is None or report['metadata_bytes'] <= 35000
    except Exception as exc:
        # Native/Lua exceptions can include request text; retain only the exception class.
        report.update(passed=False, error_kind=type(exc).__name__)
    finally:
        close()
        report['source_unchanged'] = before == snapshot()
        report['elapsed_seconds'] = round(time.monotonic()-started, 3)
        (output / 'results.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print('RESULT=' + str(output / 'results.json'))
        print(json.dumps(report))
    return 0 if report.get('passed') and report['source_unchanged'] else 1

if __name__ == '__main__':
    sys.exit(main())
