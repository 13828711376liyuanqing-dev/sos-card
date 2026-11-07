"""SAM | 2026-10-22 +08:00 | One upload must contain both components with independent identities."""
from pathlib import Path
import json
import unittest
import uuid
import zipfile
from local_packager.bundle import bundle, verify_bundle

ROOT=Path(__file__).resolve().parents[2]
class Tests(unittest.TestCase):
    def setUp(self):
        self.folder=ROOT/'logs/bundle_packager_tests'/uuid.uuid4().hex
        self.folder.mkdir(parents=True)
        self.gr=self.folder/'gr.bin';self.cat=self.folder/'cat.bin'
        self.gr.write_bytes(b'GR firmware');self.cat.write_bytes(b'CAT firmware')

    def test_two_components_one_archive(self):
        result=bundle(self.gr,self.cat,self.folder/'out','1.0','1.3')
        out=Path(result['file']);self.assertTrue(verify_bundle(out))
        with zipfile.ZipFile(out) as z:
            self.assertEqual(z.read('GR5526/payload.bin'),b'GR firmware')
            self.assertEqual(z.read('CAT1/payload.bin'),b'CAT firmware')
            meta=json.loads(z.read('bundle.json'))
            self.assertEqual([x['target'] for x in meta['components']],['GR5526','CAT1'])
            self.assertEqual(meta['distribution'],'SPLIT_THEN_SERIAL')
            self.assertFalse(meta['device_installable'])
            self.assertEqual(meta['upgrade'],'1.0---1.3')
        self.assertEqual(len(list((self.folder/'out').iterdir())),1)

    def test_names_do_not_control_versions(self):
        result=bundle(self.gr,self.cat,self.folder/'out','1.0','1.3',prefix='客户A',suffix='测试')
        self.assertIn('客户A_1.0---1.3_测试',Path(result['file']).name)
        self.assertTrue(verify_bundle(Path(result['file'])))

    def test_missing_component_no_output(self):
        with self.assertRaises(FileNotFoundError):bundle(self.gr,self.folder/'missing',self.folder/'out','1.0','1.3')
        self.assertFalse((self.folder/'out').exists())

    def test_tampered_payload_rejected(self):
        result=bundle(self.gr,self.cat,self.folder/'out','1.0','1.3')
        source=Path(result['file']);(self.folder/'bad').mkdir();bad=self.folder/'bad'/source.name
        with zipfile.ZipFile(source) as a,zipfile.ZipFile(bad,'w') as b:
            for name in a.namelist():b.writestr(name,b'changed' if name=='CAT1/payload.bin' else a.read(name))
        self.assertFalse(verify_bundle(bad))

    def test_non_newer_component_rejected(self):
        for before,after in [('1.3','1.3'),('1.10','1.3'),('1.0','01.1'),('1.0','1.0.0'),('v1.0','1.3'),('1.0---1.3','2.0')]:
            with self.assertRaises(ValueError):bundle(self.gr,self.cat,self.folder/'out',before,after)

    def test_numeric_compare_and_filename_version_tamper(self):
        result=bundle(self.gr,self.cat,self.folder/'out','1.9','1.10')
        original=Path(result['file']);changed=original.with_name(original.name.replace('1.9---1.10','1.9---1.11'))
        changed.write_bytes(original.read_bytes())
        self.assertFalse(verify_bundle(changed))

if __name__=='__main__':unittest.main()
