"""SAM | 2026-11-04 +08:00 | OTA speed-up A: the whole-archive MD5 scan uses port.scan_bytes (device 16 KiB) and still
verifies the real signed fixture; without it the 4 KiB steps are unchanged; out-of-range values fall back to 4 KiB."""
import unittest
from test_zip_bundle import BundleTests


class ScanBytes(BundleTests):
    def scan_reads(self, setting):
        if setting is not None:
            self.lua.execute(b'p.scan_bytes=' + setting)
        self.opened()
        before = len(self.reads)
        self.assertIs(self.lua.eval(b'scan()'), True)
        self.assertIs(self.lua.eval(b"r:preflight_status().state=='VERIFIED'"), True)
        return [b - a + 1 for a, b in self.reads[before:]]

    def check(self, setting, step):
        sizes = self.scan_reads(setting)
        total = len(self.data)
        self.assertEqual(sum(sizes), total)
        self.assertTrue(all(n == step for n in sizes[:-1]), sizes[:5])
        self.assertEqual(len(sizes), -(-total // step))

    def test_scan_16k(self):
        self.check(b'16384', 16384)

    def test_scan_default_4k(self):
        self.check(None, 4096)

    def test_scan_out_of_range_falls_back(self):
        self.check(b'65536', 4096)


if __name__ == '__main__':
    names = ['test_scan_16k', 'test_scan_default_4k', 'test_scan_out_of_range_falls_back']
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(ScanBytes(n) for n in names))
    raise SystemExit(0 if result.wasSuccessful() else 1)
