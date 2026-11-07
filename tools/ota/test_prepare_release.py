"""SAM | 2026-10-21 +08:00 | Test firmware admission produces verified immutable test archives only."""
from pathlib import Path
import unittest
import uuid
import json
from sim_backend.prepare_release import prepare

ROOT=Path(__file__).resolve().parents[2]

class Tests(unittest.TestCase):
    def setUp(self):
        self.folder=ROOT/'logs/ota_release_tests'/uuid.uuid4().hex
        self.folder.mkdir(parents=True)
        self.source=self.folder/'firmware.bin'
        self.source.write_bytes(bytes(range(256))*4)

    def test_prepare_verifies_and_preserves_source(self):
        before=self.source.read_bytes()
        report=prepare(self.source,'GR5526','TEST_N','TEST_N_PLUS_1',self.folder/'release')
        self.assertTrue(report['test_signature_verified'])
        self.assertFalse(report['device_installable'])
        self.assertEqual(self.source.read_bytes(),before)
        out=Path(report['directory'])
        self.assertEqual((out/'payload.bin').read_bytes(),before)
        self.assertFalse(any('private' in p.name for p in out.iterdir()))
        self.assertEqual(json.loads((out/'manifest.json').read_text())['domain'],'YP001_LOCAL_TEST_ONLY_V1')

    def test_existing_archive_not_overwritten(self):
        out=self.folder/'release';out.mkdir();(out/'keep').write_bytes(b'preserve')
        with self.assertRaises(FileExistsError):prepare(self.source,'CAT1','A','B',out)
        self.assertEqual((out/'keep').read_bytes(),b'preserve')

    def test_empty_and_same_version_reject(self):
        self.source.write_bytes(b'')
        with self.assertRaises(ValueError):prepare(self.source,'GR5526','A','B',self.folder/'empty')
        self.source.write_bytes(b'x')
        with self.assertRaises(ValueError):prepare(self.source,'GR5526','A','A',self.folder/'same')

if __name__=='__main__':unittest.main()
