"""SAM | 2026-10-23 +08:00 | Cross-check production UART codecs against independent wire vectors."""
import binascii
import os
from pathlib import Path
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'logs/cat1_antenna_20261010/python_deps'))
from lupa.lua53 import LuaRuntime

def wire(data=b'', kind=4, session=1, sequence=2, offset=0):
    head = struct.pack('<4sBBHIIIH', b'OTA2', 2, kind, 0, session, sequence, offset, len(data))
    head += struct.pack('<H', binascii.crc_hqx(head, 0xffff))
    body = head + data
    return body + struct.pack('<I', binascii.crc32(body))

class CodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = ROOT / 'logs/uart2_tests'
        out.mkdir(parents=True, exist_ok=True)
        gcc = Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
        env = dict(os.environ, PATH=str(gcc.parent)+os.pathsep+os.environ.get('PATH',''))
        subprocess.run([str(gcc), '-std=c99', '-Wall', '-Wextra', '-Werror',
                        str(ROOT/'ble_app_uart_c/Src/user/ota/yp001_ota_wire.c'),
                        str(ROOT/'tools/ota/test_uart2_runner.c'),
                        '-o', str(out/'wire.exe')], check=True, env=env)
        cls.runner = out/'wire.exe'
        cls.mux_runner = out/'mux2.exe'
        subprocess.run([str(gcc), '-std=c99', '-Wall', '-Wextra', '-Werror',
                        str(ROOT/'ble_app_uart_c/Src/user/ota/yp001_ota_wire.c'),
                        str(ROOT/'tools/ota/test_uart_mux.c'),
                        '-o', str(cls.mux_runner)], check=True, env=env)

    def test_multiplexer(self):
        subprocess.run([str(self.mux_runner)], check=True, capture_output=True)

    def c_check(self, packets):
        result=subprocess.run([str(self.runner)],input=''.join(p.hex()+'\n' for p in packets),
                              text=True,capture_output=True,check=True)
        return [tuple(map(int,line.split())) for line in result.stdout.splitlines()]

    def setUp(self):
        self.lua = LuaRuntime(encoding=None, unpack_returned_tuples=True)
        self.lua.execute(b"package.path=.....'/Air780EGH/?.lua;'..package.path; w=require('ota_wire')", ROOT.as_posix().encode())
        self.w = self.lua.globals().w

    def test_cross_language_vectors(self):
        for n in (0, 1, 255, 512):
            payload = bytes(i % 256 for i in range(n))
            expected = wire(payload, session=0xffffffff, sequence=0xffffffff, offset=123)
            actual = self.w.encode(4, 0xffffffff, 0xffffffff, 123, payload)
            self.assertEqual(actual, expected)
            self.assertEqual(self.c_check([actual]), [(1,1,1)])
            decoded = self.w.decode(actual)
            self.assertEqual(decoded[b'payload'], payload)

    def test_corruption_and_bounds(self):
        good = wire(bytes(range(256)))
        packets=[]
        for index in range(len(good)):
            bad = good[:index] + bytes([good[index]^1]) + good[index+1:]
            packets.append(bad)
            self.assertIsNone(self.w.decode(bad))
        for bad in (good[:-1],good+b'x',wire(b'x'*513)):
            packets.append(bad)
            self.assertIsNone(self.w.decode(bad))
        self.assertIsNone(self.w.encode(4,1,-1,0,b''))
        self.assertTrue(all(row[0]==0 for row in self.c_check(packets)))

    def test_all_splits_noise_and_resync(self):
        frame = wire(bytes(range(256))*2)
        for split in range(len(frame)+1):
            self.lua.execute(b"frames={}; p=w.parser(function(f) frames[#frames+1]=f end)")
            p = self.lua.globals().p
            p.feed(p,b'noiseOTA'+frame[:split])
            p.feed(p,frame[split:]+frame)
            self.assertEqual(len(self.lua.globals().frames),2)
            self.assertLessEqual(p.buffered(p),540)
        bad = bytearray(frame); bad[-1] ^= 1
        p.feed(p,bytes(bad)+frame)
        self.assertEqual(len(self.lua.globals().frames),3)
        p.feed(p,b'x'*100000)
        self.assertLessEqual(p.buffered(p),3)
        self.assertEqual(self.c_check([b'noiseOTA'+frame+frame]),[(0,2,0)])
        self.assertEqual(self.c_check([bytes(bad)+frame]),[(0,1,0)])

if __name__ == '__main__':
    unittest.main()
