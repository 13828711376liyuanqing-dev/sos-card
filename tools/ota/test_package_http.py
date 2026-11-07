"""SAM | 2026-10-21 +08:00 | Real loopback HTTP and actual Lua downloader, no device IO."""
from pathlib import Path
import sys
import threading
import urllib.request
import urllib.error
import unittest
import hashlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'logs/cat1_antenna_20261010/python_deps'))
from lupa.lua54 import LuaRuntime
from sim_backend.package_http import PackageServer
from sim_backend.signed_manifest import new_key, create, verify

class Tests(unittest.TestCase):
    def setUp(self):
        self.image = b'YP001_TEST_FIRMWARE_'*1000
        if self._testMethodName == 'test_current_hex_transport':
            self.image = (ROOT/'ble_app_uart_c/Keil_6/Objects/YP001_GR5526.hex').read_bytes()
        self.server = PackageServer(self.image)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/packages/{self.server.digest}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def get(self, headers):
        return urllib.request.urlopen(urllib.request.Request(self.url, headers=headers), timeout=3)

    def test_range_contract(self):
        with self.get({'Range':'bytes=10-19'}) as r:
            self.assertEqual(r.status, 206)
            self.assertEqual(r.read(), self.image[10:20])
            self.assertEqual(r.headers['Content-Range'], f'bytes 10-19/{len(self.image)}')
        with self.get({'Range':'bytes=10-19', 'If-Range':'"wrong"'}) as r:
            self.assertEqual(r.status, 200)
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.get({'Range':'bytes=999999-9999999'})
        self.assertEqual(e.exception.code, 416)
        for bad in ('bytes=0-1,4-5', 'bytes=-5', 'bytes=20-10'):
            with self.assertRaises(urllib.error.HTTPError) as invalid:
                self.get({'Range':bad})
            self.assertEqual(invalid.exception.code,416)
        with self.assertRaises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(self.url+'/../../private', timeout=3)
        self.assertEqual(missing.exception.code,404)

    def test_actual_lua_resume_and_real_signature(self):
        self.run_download()

    def test_current_hex_transport(self):
        self.run_download()

    def run_download(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        key = new_key()
        manifest = create(key, self.image, 'GR5526', 'TEST_N', 'TEST_N_PLUS_1')
        seen = []
        def http(url, headers, limit):
            hdr = dict(headers.items())
            seen.append(hdr)
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=3) as r:
                body = r.read(limit+1)
                if len(body)>limit:
                    return None
                return lua.table_from({'status':r.status,'headers':lua.table_from(dict(r.headers.items())), 'body':body.decode('ascii')})
        def check(data):
            raw = data.encode('ascii')
            return lua.table_from({'size':len(raw),'md5':hashlib.md5(raw).hexdigest(),
                'sha256':hashlib.sha256(raw).hexdigest(),'signature_valid':verify(key.public_key(),raw,manifest)})
        lua.globals().root = ROOT.as_posix()
        lua.globals().http = http
        lua.globals().check = check
        lua.globals().job = lua.table_from(dict(size=len(self.image),url=self.url,
            sha256=hashlib.sha256(self.image).hexdigest(),md5=hashlib.md5(self.image).hexdigest()))
        lua.execute('''
          package.path=root..'/Air780EGH/?.lua;'..package.path
          local M=require('ota_download')
          local files={['/user.json']='latest-user-data'}
          local checkpoint
          local p={chunk_size=4096,max_size=16777216,
            size=function(n)return #(files[n] or '')end,
            truncate=function(n,k)files[n]=(files[n] or ''):sub(1,k);return true end,
            write=function(n,k,b)files[n]=(files[n] or ''):sub(1,k)..b;return true end,
            read=function(n,k,c)return files[n]:sub(k+1,k+c)end,
            http_get=function(u,h,n)return http(u,h,n)end,
            checkpoint=function(c)checkpoint=c;return true end,
            verify_file=function(n)return check(files[n])end}
          local d=M.new(p);assert(d:start(job));assert(d:step());assert(checkpoint.offset==4096)
          d:pause();assert(not d:step())
          d=M.new(p);assert(d:start(job,checkpoint))
          while d:status().state=='DOWNLOADING' do assert(d:step()) end
          assert(d:verify());assert(d:status().state=='VERIFIED')
          assert(files['/user.json']=='latest-user-data')
        ''')
        self.assertEqual(seen[1]['Range'], 'bytes=4096-8191')
        self.assertIn('If-Range',seen[1])

if __name__ == '__main__':
    unittest.main()
