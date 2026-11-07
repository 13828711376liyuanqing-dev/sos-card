"""SAM | 2026-10-24 +08:00 | First-stage readback gates must catch SCA/order/data loss before any Boot activation."""
import struct
import unittest
from pathlib import Path
from gr_deployment_check import baseline_readback

ROOT=Path(__file__).resolve().parents[2]
class DeploymentCheckTests(unittest.TestCase):
    def setUp(self):
        self.before=(ROOT/'logs/ota_sequential_20261024/device_readonly/gr_current_flash_1m.bin').read_bytes()
        self.app=(ROOT/'firmware_releases/gr_first_deploy_20261024_NOT_FLASHABLE/GR_BASELINE_1.0.2_signed.bin').read_bytes()
        self.after=bytearray(self.before)
        self.after[:8192]=b'\xff'*8192
        self.after[:32]=struct.pack('<8I',len(self.app),sum(self.app)&0xffffffff,0x202000,0x202000,11,836,0,0)
        end=(len(self.app)+4095)//4096*4096
        self.after[8192:8192+end]=b'\xff'*end
        self.after[8192:8192+len(self.app)]=self.app
    def test_baseline_exact_readback_still_does_not_grant_boot(self):
        r=baseline_readback(self.before,bytes(self.after),self.app)
        self.assertTrue(r['baseline_bytes_verified'])
        self.assertTrue(r['user_regions_unchanged'])
        self.assertFalse(r['boot_activation_authorized'])
    def test_wrong_sca_route_and_sparse_merged_length_rejected(self):
        for offset,value in [(0,461252),(8,0x2ec000),(12,0x2ec000),(4,0)]:
            after=bytearray(self.after);struct.pack_into('<I',after,offset,value)
            with self.assertRaisesRegex(ValueError,'SCA'):
                baseline_readback(self.before,bytes(after),self.app)
    def test_corruption_or_any_unplanned_sector_change_rejected(self):
        for offset in [8192+100,0x6e000,0x80000,0xec000,0xfe000,0xfb000]:
            after=bytearray(self.after);after[offset]^=1
            with self.assertRaises(ValueError):baseline_readback(self.before,bytes(after),self.app)
    def test_existing_sca_extra_data_cannot_be_silently_erased(self):
        before=bytearray(self.before);before[4096]=123
        with self.assertRaisesRegex(ValueError,'SCA_EXTRA_DATA'):
            baseline_readback(bytes(before),bytes(self.after),self.app)
    def test_short_snapshot_rejected(self):
        with self.assertRaises(ValueError):baseline_readback(self.before[:-1],bytes(self.after),self.app)

if __name__=='__main__':unittest.main()
