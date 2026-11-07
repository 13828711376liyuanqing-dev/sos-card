"""SAM | 2026-10-24 +08:00 | Reject unsupported first-Boot approvals using recorded device evidence."""
import json
import unittest
from pathlib import Path
from prepare_gr_commissioning import validate

ROOT=Path(__file__).resolve().parents[2]
class CommissioningTests(unittest.TestCase):
    def setUp(self):
        self.base=ROOT/'firmware_releases/boot_bound_verify_cli_20261024_NOT_FLASHABLE'
        self.snapshot=(self.base/'current_before_boot.bin').read_bytes()
        self.signed=(ROOT/'firmware_releases/baseline_wdt_fix_20261024/baseline_verify_cli_signed.bin').read_bytes()
        self.binding=json.loads((self.base/'current_device_binding.json').read_text())
        self.runtime=json.loads((ROOT/'logs/ota_wdt_fix_20261024/normal_runtime_acceptance.json').read_text())
    def call(self,**kw):
        args=dict(root=ROOT,snapshot=self.snapshot,signed=self.signed,binding=self.binding,runtime=self.runtime)
        args.update(kw);return validate(**args)
    def test_actual_evidence_grants_only_compile_preparation(self):
        report=self.call()
        self.assertEqual(report['scope'],'THIS_BOARD_FIRST_BOOT_ONLY')
        self.assertTrue(report['layout_checked'])
        self.assertTrue(report['inventory_checked'])
        self.assertFalse(report['device_ota_accepted'])
        self.assertFalse(report['download_ready'])
    def test_snapshot_identity_and_baseline_mismatch_rejected(self):
        altered=bytearray(self.snapshot);altered[8192]^=1
        with self.assertRaises(ValueError):self.call(snapshot=bytes(altered))
        altered=bytearray(self.signed);altered[100]^=1
        with self.assertRaises(ValueError):self.call(signed=bytes(altered))
    def test_unknown_data_in_any_mutation_area_rejected_even_with_matching_digest(self):
        import hashlib
        for at in [0x80000,0xec000,0xf6000,0xf7000,0xf8000,0xf9000,0xfa000]:
            changed=bytearray(self.snapshot);changed[at]=0
            binding=dict(self.binding,snapshot_sha256=hashlib.sha256(changed).hexdigest())
            with self.assertRaises(ValueError):self.call(snapshot=bytes(changed),binding=binding)
    def test_runtime_rejection_and_version_mismatch_never_approve(self):
        for change in [{'signature_ok':False},{'normal_context':False},{'wdt_refresh':1},{'version':'1.5.0'},{'payload_bytes':426304}]:
            with self.assertRaises(ValueError):self.call(runtime=dict(self.runtime,**change))

if __name__=='__main__':unittest.main()
