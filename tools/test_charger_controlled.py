"""SAM | 2026-10-09 14:48 +08:00 | Static controlled-test guards.
These source contracts do not replace device fault-injection tests.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TREES = (ROOT/'ble_app_uart_c', ROOT/'SVN交付_YP001_GR5526_20261001/ble_app_uart_c')

class ControlledContract(unittest.TestCase):
    def test_controlled_entry(self):
        for tree in TREES:
            c = (tree/'Src/user/charger/yp001_charger.c').read_text(encoding='utf-8')
            self.assertTrue('bool yp001_charger_test_start(void)' in c, 'missing controlled start')
            start = c.split('bool yp001_charger_test_start(void)', 1)[1].split('void yp001_charger_poll', 1)[0]
            self.assertLess(start.index('test_status_ok'), start.index('write_field(REG_POWER, CHARGE_ENABLE, CHARGE_ENABLE)'))
            self.assertIn('yp001_charger_prepare_disabled()', start)
            self.assertIn('s_stop_pending', start)
            self.assertIn('if (s_test_active)', start)
            # SAM | 2026-10-09 21:25 +08:00 | Automatic insertion replaces
            # the bench deadline; preserve stop/rearm and safety contracts.
            self.assertNotIn('>= 180000U', c)
            self.assertIn('s_auto_ready = true;', c)
            self.assertIn('if (s_auto_blocked)', c)
            self.assertIn('now - s_input_since) >= 2000U', c)
            self.assertIn('now - s_absent_since) >= 2000U', c)
            self.assertIn('!status.input_present && !status.power_good', c)
            self.assertIn('if (status.charge_state == 3U)', c)
            self.assertIn('s_auto_blocked = true;', c)
            self.assertIn('IC termination/safety timer', c)
            self.assertIn('status->fault_history == 0U', c)
            self.assertIn('status->fault == 0U', c)
            self.assertIn('DISCONNECT BATTERY', c)
            bsp = (tree/'Src/platform/bsp.c').read_text(encoding='utf-8')
            self.assertIn('yp001_charger_tick_ms(1000U / BSP_TICKS_PER_SEC)', bsp)
            self.assertIn('yp001_charger_poll()', bsp)
            cli = (tree/'Src/user/charger/yp001_charger_cli.c').read_text(encoding='utf-8')
            self.assertLess(cli.index('return yp001_charger_test_stop()'), cli.index('else if (!yp001_charger_probe())'))
            self.assertIn('return yp001_charger_test_start()', cli)
            stop = c.split('bool yp001_charger_test_stop(void)', 1)[1].split('bool yp001_charger_test_start', 1)[0]
            self.assertLess(stop.index('s_test_active = false'), stop.index('yp001_charger_probe()'))
            self.assertIn('s_stop_pending = true', stop)

if __name__ == '__main__':
    unittest.main()
