"""SAM | 2026-10-23 +08:00 | Project header signing tests use only an ephemeral in-memory key."""
import base64
import hashlib
import struct
import unittest
from cryptography.hazmat.primitives.asymmetric import rsa
from gr_project_image import sign_image, verify_image


class ProjectImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        p = cls.key.public_key().public_numbers()
        cls.xml = (b'<RSAKeyValue><Modulus>' + base64.b64encode(p.n.to_bytes(256, 'big')) +
                   b'</Modulus><Exponent>AQAB</Exponent></RSAKeyValue>')
        cls.pin = hashlib.sha256(cls.xml).hexdigest()
        cls.layout = hashlib.sha256(b'test layout, not approved').hexdigest()
        cls.data = hashlib.sha256(b'test data contract, not approved').hexdigest()
        cls.payload = struct.pack('<II', 0x20010000, 0x00202009) + b'YP001_FW|GR5526|001.005.000|5|END' + b'\xff'*100

    def sign(self, payload=None, target='1.5.0'):
        return sign_image(self.payload if payload is None else payload, self.key, self.xml,
                          self.pin, self.layout, self.data, target)

    def verify(self, image, layout=None, data=None):
        return verify_image(image, self.xml, self.pin,
                            self.layout if layout is None else layout,
                            self.data if data is None else data)

    def test_roundtrip_and_install_gate(self):
        image = self.sign()
        result = self.verify(image)
        self.assertEqual(len(image), len(self.payload)+904)
        self.assertEqual(result['version'], '1.5.0')
        self.assertEqual(result['build'], 5)
        self.assertFalse(result['device_installable'])

    def test_no_version_relabel(self):
        with self.assertRaises(ValueError):
            self.sign(target='1.5.1')

    def test_contract_pins_are_external(self):
        image = self.sign()
        for kwargs in [{'layout': '0'*64}, {'data': '0'*64}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.verify(image, **kwargs)

    def test_identity_and_vectors(self):
        for payload in [self.payload + self.payload[8:], b'\0'*8+self.payload[8:],
                        self.payload.replace(b'|5|END', b'|0|END')]:
            with self.subTest(length=len(payload)), self.assertRaises(ValueError):
                self.sign(payload=payload)

    def test_capacity_boundary(self):
        payload = self.payload + b'\xff'*(441464-len(self.payload))
        self.assertEqual(len(self.sign(payload=payload)), 442368)
        with self.assertRaises(ValueError):
            self.sign(payload=payload+b'\xff')

    def test_signed_bad_header_rejected(self):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        image = self.sign()
        for offset in [0, 4, 8, 12, 16, 20, 24, 28, 32, 64, 96]:
            changed = bytearray(image[:-256])
            changed[len(self.payload)+offset] ^= 1
            signature = self.key.sign(bytes(changed), padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())[::-1]
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.verify(bytes(changed)+signature)


if __name__ == '__main__':
    unittest.main()
