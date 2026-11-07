"""SAM | 2026-10-21 +08:00 | Offline single-file export without upload or overwrite."""
from pathlib import Path
import unittest
import uuid
import zipfile
import json
from local_packager.packager import package

ROOT=Path(__file__).resolve().parents[2]
class Tests(unittest.TestCase):
    def test_export_one_package(self):
        folder=ROOT/'logs/local_packager_tests'/uuid.uuid4().hex;folder.mkdir(parents=True)
        source=folder/'input.bin';source.write_bytes(b'firmware bytes')
        result=package(source,folder/'output','CAT1','001.000.000','001.000.001','LUATOS_FOTA')
        self.assertEqual(source.read_bytes(),b'firmware bytes')
        out=Path(result['file']);self.assertTrue(out.exists())
        with zipfile.ZipFile(out) as z:
            self.assertEqual(z.read('payload.bin'),b'firmware bytes')
            meta=json.loads(z.read('release.json'))
            self.assertEqual(meta['package_type'],'LUATOS_FOTA')
            self.assertFalse(meta['device_installable'])
        self.assertEqual(len(list((folder/'output').iterdir())),1)
    def test_invalid_source_no_output(self):
        folder=ROOT/'logs/local_packager_tests'/uuid.uuid4().hex
        with self.assertRaises(FileNotFoundError):package(folder/'missing',folder/'output','GR5526','1','2','BIN')
        self.assertFalse((folder/'output').exists())
if __name__=='__main__':unittest.main()
