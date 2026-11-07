"""SAM | 2026-11-05 +08:00 | Keep CAT1 powered while it is flashed (Luatools) or left idle, and bring it back if GR cuts it.
- every 10 s: `at FOTA_STATUS` through the GR CLI -> GR Cat1Svr AO (UART_TX_DATA_SIG) refreshes its 60 s low-power timer
  (a direct cat_at poll does not);
- if GR reports `rail_request=off`: wait 3 s, `cat1_power on`, then one `cat1_power key` (same sequence GR uses at boot).
Uses only the GR port (YP_GR_PORT, default COM30). It must NOT open CAT1's own USB ports (COM21/COM23): Luatools needs them,
so stop cat1_vuart_log.py before flashing.
Usage: YP_GR_PORT=COM30 python keep_cat1.py [minutes=25]   (stops by itself; Ctrl-C releases the port)"""
import os
import sys
import time
import serial

port = os.environ.get('YP_GR_PORT', 'COM30')
end = time.time() + 60 * float(sys.argv[1] if len(sys.argv) > 1 else 25)
s = serial.Serial(port, 115200, timeout=0.2)


def say(msg):
    print(time.strftime('%H:%M:%S'), msg, flush=True)


say('keep CAT1 powered on ' + port)
try:
    while time.time() < end:
        s.write(b'at FOTA_STATUS\r\n')
        t0, buf = time.time(), ''
        while time.time() - t0 < 10:
            buf += s.read(4096).decode('utf-8', 'replace')
        for line in buf.splitlines():                    # network / OTA state lines worth keeping
            if ('[CAT1 RX] [MQTT' in line or '[CAT1 RX] [OTA_RX]' in line or 'OTA_HOLD' in line) and 'parse' not in line:
                say(line.strip()[:160])
        # only the LAST rail event counts: an old `off` followed by `on` (GR's own reset) means CAT1 is powered
        if buf.rfind('rail_request=off') > buf.rfind('rail_request=on'):
            say('GR cut CAT1 power -> power on again')
            time.sleep(3)
            for c in (b'cat1_power on\r\n', b'cat1_power key\r\n'):
                s.write(c)
                time.sleep(1.5)
finally:
    s.close()
    say('stopped, port released')
