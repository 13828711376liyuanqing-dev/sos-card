"""SAM | 2026-11-04 +08:00 | Check reboot attribution before real reset monitoring."""
import importlib.util
import pathlib
import struct
import unittest
import zlib

MODULE = pathlib.Path(__file__).with_name('gr_stability_monitor.py')


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.exists(), 'monitor implementation missing')
        spec = importlib.util.spec_from_file_location('monitor', MODULE)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_boot_markers_do_not_double_count(self):
        state = self.module.BootTracker()
        state.line('=== YP001 GR5526 BOOT / UART0 ===', 1)
        state.line('[ULTRA PRE-RESET] valid=0', 2)
        state.line('[BOOT] BSP_start complete; entering QF_run', 8)
        self.assertEqual(state.unexpected, 1)
        self.assertEqual(state.boots, 1)

    def test_second_banner_is_another_boot(self):
        state = self.module.BootTracker()
        state.line('=== YP001 GR5526 BOOT / UART0 ===', 1)
        state.line('=== YP001 GR5526 BOOT / UART0 ===', 3)
        self.assertEqual(state.unexpected, 2)

    def test_only_one_boot_is_associated_with_reset(self):
        state = self.module.BootTracker()
        state.arm(10)
        state.line('=== YP001 GR5526 BOOT / UART0 ===', 11)
        state.line('=== YP001 GR5526 BOOT / UART0 ===', 13)
        self.assertEqual(state.planned, 1)
        self.assertEqual(state.unexpected, 1)

    def test_expired_reset_window_is_not_planned(self):
        state = self.module.BootTracker()
        state.arm(10)
        state.line('=== YP001 GR5526 BOOT / UART0 ===', 80)
        self.assertEqual(state.unexpected, 1)

    def test_missing_banner_still_flags_boot(self):
        state = self.module.BootTracker()
        state.line('[ULTRA PRE-RESET] valid=0', 2)
        state.line('[BOOT] BSP_start complete; entering QF_run', 8)
        self.assertEqual(state.unexpected, 1)

    def test_journal_rejects_pending_and_corruption(self):
        page = bytearray(b'\xff' * 4096)
        struct.pack_into('<IIII', page, 0, 0x594F5432, 1, 1, 3)
        struct.pack_into('<I', page, 360, zlib.crc32(page[:360]))
        struct.pack_into('<I', page, 364, 0)
        self.assertFalse(self.module.journal_safe(bytes(page) + b'\xff' * 4096))
        struct.pack_into('<I', page, 12, 4)
        struct.pack_into('<I', page, 360, zlib.crc32(page[:360]))
        self.assertTrue(self.module.journal_safe(bytes(page) + b'\xff' * 4096))
        page[20] ^= 1
        self.assertFalse(self.module.journal_safe(bytes(page) + b'\xff' * 4096))

    def test_status_writer_survives_windows_replace_contention(self):
        from unittest.mock import patch
        path = pathlib.Path('unused_status.json')
        with patch.object(pathlib.Path, 'replace', side_effect=PermissionError('sharing')):
            with patch.object(pathlib.Path, 'write_text') as writer:
                self.assertTrue(self.module.write_status(path, {'result': 'running'}))
                self.assertEqual(writer.call_count, 4)

    def test_bench_offline_unknown_call_and_active_call(self):
        self.assertTrue(self.module.business_quiet('[BUSINESS] link=0 net=0 alarm=0 id=0 call=6'))
        self.assertFalse(self.module.business_quiet('[BUSINESS] link=1 net=4 alarm=0 id=0 call=6'))
        self.assertFalse(self.module.business_quiet('[BUSINESS] link=1 net=4 alarm=0 id=0 call=3'))
        self.assertFalse(self.module.business_quiet('[BUSINESS] link=0 net=0 alarm=1 id=1 call=0'))


if __name__ == '__main__':
    unittest.main()
