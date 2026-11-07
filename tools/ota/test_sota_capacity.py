"""SAM | 2026-10-24 +08:00 | Exercise the real native generator so capacity acceptance cannot be inferred from compressed SOTA size."""
import json
import os
from pathlib import Path
import subprocess
import unittest
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]

class NativeCapacityTests(unittest.TestCase):
    def test_current_source_generates_bounded_readback_verified_sota(self):
        cli = ROOT / 'OTA_Packager/YP001OtaReleaseCli.exe'
        vendor = Path(os.environ.get('YP_LUATOOLS_HOME', 'D:/Installers'))
        if not cli.exists() or not (vendor / '_temp/tools/luac_64bit.exe').exists():
            self.skipTest('native generator/vendor compiler unavailable')
        output = ROOT / 'logs/ota_sequential_20261024' / ('capacity_' + datetime.now().strftime('%H%M%S_%f'))
        output.mkdir(parents=True)
        result = subprocess.run([str(cli), 'cat1', str(ROOT / 'Air780EGH'), str(vendor), str(output)],
                                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
        (output / 'build.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        reports = list(output.glob('*.sota.json'))
        self.assertEqual(len(reports), 1)
        report = json.loads(reports[0].read_text(encoding='utf-8-sig'))
        self.assertLessEqual(report['script_bytes'], 524288)
        self.assertEqual(report['script_limit'], 524288)
        self.assertTrue(report['native_structure_verified'])
        self.assertTrue(report['decompressed_readback_verified'])
        self.assertFalse(report['user_data_ranges_in_payload'])
        self.assertFalse(report['device_installation_verified'])
        print('CAPACITY_REPORT=' + str(reports[0]))
        print('LUA_DB_BYTES=' + str(report['script_bytes']))

if __name__ == '__main__':
    unittest.main()
