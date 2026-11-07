"""SAM | 2026-10-23 +08:00 | Reject malformed native candidates without reading release private keys or touching devices."""
import base64
import hashlib
import struct
import unittest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from gr_native_inspect import inspect_image


class NativeInspectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        p = cls.key.public_key().public_numbers()
        enc = lambda n, size: base64.b64encode(n.to_bytes(size, 'big')).decode()
        cls.xml = ('<RSAKeyValue><Modulus>' + enc(p.n, 256) +
                   '</Modulus><Exponent>AQAB</Exponent></RSAKeyValue>').encode()
        cls.pin = hashlib.sha256(cls.xml).hexdigest()
        cls.payload = b'YP001 test payload; not executable' * 8
        blob = (p.n.to_bytes(256, 'little') + struct.pack('<I', p.e) +
                pow(2, 4096, p.n).to_bytes(256, 'little') +
                struct.pack('<I', (-pow(p.n, -1, 1 << 32)) & 0xffffffff))
        cls.span = cls.payload + bytes(128) + blob
        cls.image = cls.sign(cls.span)

    @classmethod
    def sign(cls, span):
        return span + cls.key.sign(span, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())[::-1]

    def check(self, image=None, xml=None, pin=None):
        return inspect_image(self.image if image is None else image,
                             self.xml if xml is None else xml,
                             self.pin if pin is None else pin)

    def test_crypto_success_never_install_authority(self):
        result = self.check()
        self.assertTrue(result['signature_verified'])
        self.assertFalse(result['device_installable'])
        self.assertEqual(result['payload_bytes'], len(self.payload))
        self.assertEqual(result['header_semantics'], 'UNVERIFIED')
        self.assertEqual(len(result['observed_header_words']), 14)

    def test_pin_required_and_exact(self):
        for pin in ['', '0' * 64, self.pin.upper()]:
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                self.check(pin=pin)

    def test_raw_truncated_and_oversized(self):
        for image in [self.payload, self.image[:-1], b'\0' * 479233]:
            with self.subTest(size=len(image)), self.assertRaises(ValueError):
                self.check(image=image)

    def test_every_region_tamper(self):
        for offset in [0, len(self.payload), len(self.payload)+128,
                       len(self.payload)+388, len(self.payload)+644, len(self.image)-1]:
            changed = bytearray(self.image)
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.check(image=bytes(changed))

    def test_signed_bad_montgomery_fields(self):
        for offset in [len(self.payload)+388, len(self.payload)+644]:
            changed = bytearray(self.span)
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, 'MONTGOMERY'):
                self.check(image=self.sign(bytes(changed)))

    def test_signed_wrong_exponent(self):
        changed = bytearray(self.span)
        changed[len(self.payload)+384:len(self.payload)+388] = struct.pack('<I', 3)
        with self.assertRaises(ValueError):
            self.check(image=self.sign(bytes(changed)))

    def test_v15_rejected(self):
        image = self.span + self.key.sign(self.span, padding.PKCS1v15(), hashes.SHA256())[::-1]
        with self.assertRaises(ValueError):
            self.check(image=image)

    def test_private_xml_rejected_even_with_matching_pin(self):
        xml = self.xml.replace(b'</RSAKeyValue>', b'<D>AA==</D></RSAKeyValue>')
        with self.assertRaises(ValueError):
            self.check(xml=xml, pin=hashlib.sha256(xml).hexdigest())


if __name__ == '__main__':
    unittest.main()
