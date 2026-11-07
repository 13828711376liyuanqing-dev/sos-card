# SAM | 2026-11-05 +08:00 | Regression guard for J-Link inclusive erase endpoints next to persistent user pages.
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parent / 'yp001_gr_jlink_flash.py'

class EraseBoundaryTests(unittest.TestCase):
    def test_window_tool_uses_the_same_partition_endpoints(self):
        source = (SOURCE.parent / 'src' / 'GrJLinkFlash.cs').read_text(encoding='utf8')
        for endpoint in ('CLEAR_END - 1', 'B_ADDR + SLOT - 1', 'BOOT_ADDR + BOOT_MAX - 1'):
            self.assertTrue(endpoint in source, endpoint)
    def test_owner_erase_stops_before_name_page(self):
        self.assertTrue('0x{CLEAR_END - 1:X}' in SOURCE.read_text(encoding='utf8'), 'owner erase must exclude the name page')
    def test_slot_erase_stops_before_boot(self):
        self.assertTrue('0x{B_ADDR + SLOT - 1:X}' in SOURCE.read_text(encoding='utf8'), 'slot erase must exclude Boot')
    def test_boot_erase_stops_before_scratch(self):
        self.assertTrue('0x{BOOT_ADDR + BOOT_MAX - 1:X}' in SOURCE.read_text(encoding='utf8'), 'Boot erase must exclude scratch')

if __name__ == '__main__':
    unittest.main()
