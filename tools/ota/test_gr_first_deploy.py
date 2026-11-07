"""SAM | 2026-10-24 +08:00 | First-deployment preparation must reject unknown write regions and stale inventory, without granting device writes."""
import hashlib
from pathlib import Path
import unittest
import gr_first_deploy as deploy

ROOT=Path(__file__).resolve().parents[2]
class FirstDeployTests(unittest.TestCase):
    def setUp(self):
        self.snapshot=(ROOT/'logs/ota_sequential_20261024/device_readonly/gr_current_flash_1m.bin').read_bytes()
        self.pin=hashlib.sha256(self.snapshot).hexdigest()
        self.memory=deploy.read_hex(ROOT/'firmware_releases/baseline_candidate_20261024_usbfix/GR5526/YP001_GR5526.hex')
    def test_real_snapshot_preserves_user_regions_and_refuses_flash_authority(self):
        r=deploy.inspect(self.snapshot,self.pin,self.memory)
        self.assertEqual(r['baseline_bytes'],426304)
        self.assertFalse(r['flash_ready'])
        self.assertTrue(r['compact_baseline_required'])
        self.assertEqual([x['name'] for x in r['protected']],['preserved','nvds'])
    def test_stale_or_short_snapshot_rejected(self):
        for data,pin in [(self.snapshot[:-1],self.pin),(self.snapshot,'0'*64)]:
            with self.assertRaises(ValueError):deploy.inspect(data,pin,self.memory)
    def test_nonempty_future_boot_or_upgrade_areas_rejected(self):
        for address in [0x280000,0x2ec000,0x2f6000,0x2f7000,0x2f8000,0x2f9000,0x2fa000]:
            data=bytearray(self.snapshot);data[address-0x200000]=0
            with self.assertRaisesRegex(ValueError,'AREA_NOT_ERASED'):
                deploy.inspect(bytes(data),hashlib.sha256(data).hexdigest(),self.memory)
    def test_baseline_touching_preserved_or_nvds_rejected(self):
        for address in [0x200000,0x26e000,0x280000,0x2ec000,0x2fe000]:
            memory=dict(self.memory);memory[address]=0
            with self.assertRaisesRegex(ValueError,'BASELINE_RANGE'):
                deploy.inspect(self.snapshot,self.pin,memory)
    def test_signed_span_hex_roundtrip_and_capacity(self):
        payload=bytes([i%251 for i in range(427208)])
        encoded=deploy.hex_image(payload,0x202000)
        self.assertEqual(deploy.decode_hex(encoded),{0x202000+i:b for i,b in enumerate(payload)})
        with self.assertRaisesRegex(ValueError,'SIGNED_RANGE'):
            deploy.hex_image(bytes(442369),0x202000)
    def test_generated_boot_binding_matches_payload_but_keeps_approvals_closed(self):
        payload=bytes(self.memory[a] for a in range(min(self.memory),max(self.memory)+1))
        text=deploy.provision(payload,'11'*32,'22'*32,'33'*32)
        self.assertIn('0,0,1,',text)
        self.assertIn('426304u,1000002u',text)
        self.assertNotIn('421184u',text)
    def test_hex_corruption_duplicate_and_missing_end_rejected(self):
        valid=deploy.hex_image(b'12345678',0x202000)
        lines=valid.splitlines()
        for text in [valid.replace('3132','3032'), '\n'.join(lines[:-1]),
                     '\n'.join(lines[:2]+[lines[1]]+lines[2:]),valid+lines[-1]+'\n']:
            with self.assertRaises(ValueError):deploy.decode_hex(text)

if __name__=='__main__':unittest.main()
