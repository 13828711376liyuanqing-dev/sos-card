"""SAM | 2026-10-24 +08:00 | A download carrier must preserve the complete signed payload and exclude every other flash region."""
import tempfile
import unittest
from pathlib import Path
from gr_signed_carrier import build, make_download_project
import hashlib
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
class CarrierTests(unittest.TestCase):
    def test_real_signed_baseline_carrier(self):
        source=ROOT/'firmware_releases/gr_first_deploy_20261024_NOT_FLASHABLE/GR_BASELINE_1.0.2_signed.bin'
        with tempfile.TemporaryDirectory(dir=ROOT/'logs') as tmp:
            result=build(source,Path(tmp))
            self.assertEqual(result['payload_bytes'],427208)
            self.assertEqual(result['start'],0x202000)
            self.assertEqual(result['end_exclusive'],0x26a4c8)
            self.assertTrue(result['roundtrip_equal'])
            self.assertFalse(result['link_warning'])
            self.assertFalse(result['full_deployment_ready'])
            project=make_download_project(Path(tmp))
            tree=ET.parse(project)
            self.assertEqual(tree.find('.//OutputName').text,'STAGE1_SIGNED_BASELINE_ONLY')
            self.assertEqual(len(tree.findall('.//FilePath')),0)
            self.assertEqual(project.with_suffix('.uvoptx').read_bytes(),
                (ROOT/'ble_app_uart_c/Keil_6/YP001_GR5526.uvoptx').read_bytes())
            with self.assertRaises(ValueError):make_download_project(Path(tmp))
    def test_unsigned_payload_rejected_before_build(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'logs') as tmp:
            source=Path(tmp)/'unsigned.bin';source.write_bytes(bytes(1000))
            with self.assertRaises(ValueError):build(source,Path(tmp)/'out')

if __name__=='__main__':unittest.main()
