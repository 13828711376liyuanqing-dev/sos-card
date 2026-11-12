"""SAM | 2026-10-09 12:20 +08:00 | Guard disabled-only source contract.
Static checks only: do not claim device/bus fault-injection coverage.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
TREES = (ROOT / 'ble_app_uart_c', ROOT / 'SVN交付_YP001_GR5526_20261001/ble_app_uart_c')


class DisabledChargerContract(unittest.TestCase):
    def test_both_trees(self):
        for tree in TREES:
            with self.subTest(tree=tree.name):
                driver = (tree / 'Src/user/charger/yp001_charger.c').read_text(encoding='utf-8')
                self.assertIn('bool yp001_charger_prepare_disabled(void)', driver)
                prepare = driver.split('bool yp001_charger_prepare_disabled(void)', 1)[1].split('bool yp001_charger_set_enabled', 1)[0]
                self.assertLess(prepare.index('yp001_charger_set_enabled(false)'), prepare.index('yp001_charger_apply_profile'))
                self.assertIn('{ 500U, 100U, 4200U }', prepare)
                self.assertIn('write_field(REG_PRE_TERM, 0xFFU, 0U)', prepare)
                self.assertIn('write_field(REG_TIMER, 0xB8U, 0x88U)', prepare)
                self.assertIn('write_field(REG_FINE, 0x80U, 0U)', prepare)
                self.assertIn('DISABLE NOT CONFIRMED', prepare)
                # SAM | 2026-10-09 14:48 +08:00 | Bound the generic API check
                # because the separately guarded manual API now follows it.
                enable = driver.split('bool yp001_charger_set_enabled(bool enabled)', 1)[1].split('\n}', 1)[0]
                self.assertRegex(enable, r'if\s*\(enabled\)\s*return false;')
                self.assertNotIn('CHARGE_ENABLE :', enable)
                cli = (tree / 'Src/user/charger/yp001_charger_cli.c').read_text(encoding='utf-8')
                self.assertIn('yp001_charger_prepare_disabled()', cli)
                self.assertIn('CHG_EN=', cli)
                bsp = (tree / 'Src/platform/bsp.c').read_text(encoding='utf-8')
                self.assertLess(bsp.index('gpio_init();'), bsp.index('cli_execute_string("charger prepare")'))
                self.assertLess(bsp.index('cli_execute_string("charger prepare")'), bsp.index('epaper_depg0150_init()'))

    def test_driver_copies_match(self):
        for name in ('yp001_charger.c', 'yp001_charger.h', 'yp001_charger_cli.c'):
            self.assertEqual(*( (t / 'Src/user/charger' / name).read_bytes() for t in TREES))


if __name__ == '__main__':
    unittest.main()
