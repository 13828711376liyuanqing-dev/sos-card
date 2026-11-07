"""SAM | 2026-10-24 +08:00 | Validate real board watchdog settings against SDK104's 16-bit alarm ticks, including measured 26740 Hz."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
class WatchdogConfigurationTests(unittest.TestCase):
    def test_board_alarm_fits_sdk_counter_at_measured_and_nominal_clocks(self):
        text=(ROOT/'ble_app_uart_c/Src/platform/bsp.c').read_text(encoding='utf-8')
        counter=int(re.search(r's_params\.init\.counter\s*=\s*(\d+)',text)[1])
        alarm=int(re.search(r's_params\.init\.alarm_counter\s*=\s*(\d+)',text)[1])
        self.assertEqual(counter,5000,'Do not change the existing reset timeout to hide an invalid alarm')
        self.assertGreater(counter,alarm)
        for hz in [26740,32768]:
            with self.subTest(slow_hz=hz):
                self.assertLessEqual((alarm*hz+999)//1000,65535,
                    'SDK104 alarm is 16 bit; failed init leaves all guarded OTA operations unavailable')

if __name__=='__main__':unittest.main()
