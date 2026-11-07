"""SAM | 2026-10-24 +08:00 | Verify RSP framing before using a read-only target function; no device connection in tests."""
import unittest
from gr_gdb_probe import packet, unescape, checked_payload, probe_plan

class RspTests(unittest.TestCase):
    def test_checksum_and_bad_frame(self):
        self.assertEqual(packet(b'?'),b'$?#3f')
        self.assertEqual(checked_payload(b'OK',b'9a'),b'OK')
        with self.assertRaises(ValueError):checked_payload(b'OK',b'00')
    def test_escaping_and_rle(self):
        self.assertEqual(unescape(b'}\x03'),b'#')
        self.assertEqual(unescape(b'a* '),b'aaaa')
        with self.assertRaises(ValueError):unescape(b'}')
        with self.assertRaises(ValueError):unescape(b'* ')
    def test_probe_only_uses_saved_thread_stack(self):
        r=probe_plan(0x233000,0x2003ff00,0x01000000)
        self.assertGreaterEqual(r['scratch_start'],0x20006000)
        self.assertLess(r['call_sp'],r['output'])
        self.assertEqual(probe_plan(0x107df2,0x2003ff20,0x81000000)['return_pc'],0x107df2)
        for values in [(0x233000,0x2003ff00,0x01000003),(0x233000,0x20007000,0x01000000),
                       (0x233000,0x20050000,0x01000000),(0x1000,0x2003ff00,0x01000000)]:
            with self.assertRaises(ValueError):probe_plan(*values)

if __name__=='__main__':unittest.main()
