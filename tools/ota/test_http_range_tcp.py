"""SAM | 2026-10-23 +08:00 | Actual loopback TCP through the Lua bounded receiver and signed ZIP reader; not modem acceptance."""
import hashlib
import socket
import threading
import time
import unittest
import test_zip_bundle
from sim_backend.package_http import PackageServer


class TcpBundleTests(unittest.TestCase):
    def test_signed_zip_preflight_and_serial_components(self):
        fixture = test_zip_bundle.BundleTests()
        fixture.setUp()
        lua = fixture.lua
        server = PackageServer(fixture.data)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = None
        connections = releases = largest = 0
        start = time.monotonic()

        def connect(host, port):
            nonlocal connection, connections
            connection = socket.create_connection((host.decode(), port), timeout=2)
            connection.setblocking(False)
            connections += 1
            return True, True

        def send(data):
            connection.setblocking(True)
            connection.settimeout(2)
            connection.sendall(data)
            connection.setblocking(False)
            return True, False, True

        def read(limit):
            nonlocal largest
            largest = max(largest, limit)
            assert 1 <= limit <= 512
            try:
                data = connection.recv(limit)
            except BlockingIOError:
                return True, b''
            return bool(data), data

        def close():
            nonlocal connection, releases
            if connection is not None:
                connection.close()
                connection = None
            releases += 1

        g = lua.globals()
        g.tcp_connect, g.tcp_send, g.tcp_read, g.tcp_close = connect, send, read, close
        g.tcp_clock = lambda: int((time.monotonic()-start)*1000)
        g.tcp_wait = lambda ms: time.sleep(ms/1000)
        lua.execute(b'''
          local net={ON_LINE=1,TX_OK=2,EVENT=3,CLOSED=4,
            create=function()return {}end,config=function()return true end,
            connect=function(_,h,p)return tcp_connect(h,p)end,
            tx=function(_,data)return tcp_send(data)end,
            rx=function(_,b,flag,limit)
              assert(flag==0 and #b.data==0);local ok,data=tcp_read(limit);b.data=b.data..data;return ok,#data
            end,
            close=function()tcp_close()end,release=function()end}
          local buffers={create=function()return {data='',clear=function(self)self.data=string.rep('\0',#self.data)end,del=function(self)self.data=''end,
            query=function(self,offset,n)return self.data:sub(offset+1,offset+n)end}end}
          local receiver=assert(require('ota_http_range').new({socket=net,zbuff=buffers,
            native_rx_limit_verified=true,now_ms=function()return tcp_clock()end,
            wait=function(n)tcp_wait(n)end,can_read=p.can_read}))
          p.http_get=receiver.http_get
        ''')
        g.input[b'url'] = f'http://127.0.0.1:{server.server_port}/packages/{server.digest}'.encode()
        try:
            fixture.opened()
            self.assertIs(lua.eval(b'scan()'), True)
            for target in (b'GR5526', b'CAT1'):
                fixture.owner = target
                g.target = target
                lua.execute(b'cp=assert(r:component_port(target,1,{}));c=r:component(target)')
                component = g.c
                sha, md5 = hashlib.sha256(), hashlib.md5()
                for offset in range(0, component[b'size'], 4096):
                    count = min(4096, component[b'size']-offset)
                    g.requested_range = f'bytes={offset}-{offset+count-1}'.encode()
                    g.requested_count = count
                    body = lua.eval(b'cp.http_get(input.url,{Range=requested_range},requested_count).body')
                    sha.update(body)
                    md5.update(body)
                self.assertEqual(sha.hexdigest().encode(), component[b'sha256'])
                self.assertEqual(md5.hexdigest().encode(), component[b'md5'])
                fixture.done = True  # Host sequencing fixture, never a device installation claim.
            self.assertGreater(connections, 300)
            self.assertEqual(connections, releases)
            self.assertLessEqual(largest, 512)
            print(f'PASS TCP requests={connections}, closed={releases}, max_native_read={largest}, both component digests matched')
        finally:
            if connection is not None:
                connection.close()
            server.shutdown()
            server.server_close()
            thread.join(2)


if __name__ == '__main__':
    unittest.main()
