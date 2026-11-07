"""SAM | 2026-10-21 +08:00 | Local operator upload/package boundaries and firmware identity."""
from pathlib import Path
import unittest
import uuid
import zipfile
from sim_backend.release_store import upload, releases, archive

ROOT=Path(__file__).resolve().parents[2]
class Tests(unittest.TestCase):
    def setUp(self):self.root=ROOT/'logs/ota_release_tests'/uuid.uuid4().hex
    def test_both_components_versioned(self):
        for target in ('GR5526','CAT1'):
            item=upload(b'payload',target,'001.000.000','001.000.001','BIN',self.root)
            self.assertFalse(item['device_installable'])
            with zipfile.ZipFile(archive(item['id'],self.root)) as z:
                self.assertEqual(z.read('payload.bin'),b'payload')
                self.assertIn('manifest.json',z.namelist())
        self.assertEqual(len(releases(self.root)),2)
    def test_bad_hex_rejected(self):
        with self.assertRaises(ValueError):upload(b':nothex','GR5526','1','2','HEX',self.root)
        self.assertEqual(releases(self.root),[])
    def test_invalid_version_and_path(self):
        with self.assertRaises(ValueError):upload(b'x','GR5526','../1','2','BIN',self.root)
        with self.assertRaises(ValueError):archive('../outside',self.root)
        with self.assertRaises(ValueError):upload(b'x','CAT1','1','1','BIN',self.root)
if __name__=='__main__':unittest.main()
