"""SAM | 2026-10-23 +08:00 | Verify operator-built native ZIP through independent crypto and actual Lua/TCP; no device writes."""
import hashlib
import json
import os
from pathlib import Path
import unittest
import zipfile
import base64
import xml.etree.ElementTree as ET
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
import test_zip_bundle
import test_http_range_tcp
from gr_project_image import verify_image

ARCHIVE = Path(os.environ['YP_OTA_TEST_ARCHIVE'])
DATA = ARCHIVE.read_bytes()
original_setup = test_zip_bundle.BundleTests.setUp


def native_setup(self):
    original_setup(self)
    self.data = DATA
    self.lua.globals().input[b'md5'] = hashlib.md5(DATA).hexdigest().encode()


test_zip_bundle.BundleTests.setUp = native_setup


class NativeBundleTests(unittest.TestCase):
    def test_independent_native_signature(self):
        with zipfile.ZipFile(ARCHIVE) as archive:
            manifest = json.loads(archive.read('bundle.json'))
            public = (test_zip_bundle.ROOT / 'tools/toolkit/test_keys/OTA_TEST_PUBLIC.xml').read_bytes()
            verify_image(archive.read('GR5526/payload.bin'), public,
                         hashlib.sha256(public).hexdigest(),
                         manifest['gr_layout_contract_sha256'],
                         manifest['gr_data_contract_sha256'])
            self.assertFalse(manifest['device_installable'])

    def test_independent_cat_proof_signature(self):
        # SAM | 2026-10-23 +08:00 | Independent implementation verifies CNG output, exact payload and signed contracts.
        with zipfile.ZipFile(ARCHIVE) as archive:
            manifest = json.loads(archive.read('bundle.json'))
            record = json.loads(archive.read('CAT1/build.json'))
            proof = bytes.fromhex(record['gr_cat_proof_hex'])
            self.assertEqual(len(proof), 904)
            self.assertEqual(proof[:4], b'YPCT')
            self.assertEqual(proof[32:64].hex(), manifest['gr_layout_contract_sha256'])
            self.assertEqual(proof[96:128].hex(), manifest['gr_data_contract_sha256'])
            self.assertEqual(proof[64:96], hashlib.sha256(archive.read('CAT1/payload.sota')).digest())
            xml = ET.fromstring((test_zip_bundle.ROOT / 'tools/toolkit/test_keys/OTA_TEST_PUBLIC.xml').read_bytes())
            n = int.from_bytes(base64.b64decode(xml.findtext('Modulus')), 'big')
            e = int.from_bytes(base64.b64decode(xml.findtext('Exponent')), 'big')
            self.assertEqual(int.from_bytes(proof[128:384], 'little'), n)
            key = rsa.RSAPublicNumbers(e, n).public_key()
            scheme = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)
            key.verify(proof[648:][::-1], proof[:648], scheme, hashes.SHA256())
            damaged = bytearray(proof[:648]); damaged[64] ^= 1
            from cryptography.exceptions import InvalidSignature
            with self.assertRaises(InvalidSignature):
                key.verify(proof[648:][::-1], bytes(damaged), scheme, hashes.SHA256())

    def test_native_exact_space_and_install_gate(self):
        fixture = test_zip_bundle.BundleTests()
        fixture.setUp()
        fixture.opened()
        self.assertIs(fixture.lua.eval(b'scan()'), True)
        fixture.lua.execute(b"c=r:component('GR5526');assert(c.native_gr);p.free_bytes=function()return c.size+16384 end")
        self.assertIsNotNone(fixture.lua.eval(b"r:component_port('GR5526',1,{})"))
        fixture.lua.execute(b'p.free_bytes=function()return c.size+16383 end')
        self.assertEqual(fixture.lua.eval(b"r:component_port('GR5526',1,{})"), (None, b'COMPONENT_SPACE'))
        self.assertFalse(fixture.lua.eval(b'r:summary().device_installable'))


if __name__ == '__main__':
    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(NativeBundleTests))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(test_http_range_tcp.TcpBundleTests))
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
