"""SAM | 2026-10-21 +08:00 | Real test-domain signatures, never firmware installation authority."""
import unittest
import hashlib
from sim_backend.signed_manifest import create, verify, new_key

class Tests(unittest.TestCase):
    def test_valid_and_tampering(self):
        key = new_key()
        image = b'test firmware bytes'
        doc = create(key, image, 'GR5526', '1.0.0', '1.0.1')
        self.assertTrue(verify(key.public_key(), image, doc))
        self.assertFalse(verify(key.public_key(), image+b'changed', doc))
        for field, value in [('target', 'CAT1'), ('version', '9.0.0'),
                             ('preserve_user_data', False), ('product', 'OTHER'),
                             ('source_version', '0.0.0'), ('data_schema', 'unknown')]:
            changed = dict(doc)
            changed[field] = value
            self.assertFalse(verify(key.public_key(), image, changed))
        self.assertFalse(verify(new_key().public_key(), image, doc))

    def test_domain_and_algorithm_reject(self):
        key = new_key()
        doc = create(key, b'x', 'CAT1', '1.0.0', '1.0.1')
        for field in ('domain', 'algorithm', 'signature'):
            changed = dict(doc)
            changed[field] = 'invalid'
            self.assertFalse(verify(key.public_key(), b'x', changed))

if __name__ == '__main__':
    unittest.main()
