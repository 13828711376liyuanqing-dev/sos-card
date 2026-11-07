"""SAM | 2026-11-07 +08:00 | Verify user-approved 50-percent OR measured USB power in both build modes, host only."""
from pathlib import Path
import os
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    out = ROOT / 'logs/ota_power_policy_20261107'
    out.mkdir(parents=True, exist_ok=True)
    cfile = ROOT / 'tools/ota/test_usb_bench_power.c'
    source = (ROOT/'ble_app_uart_c/Src/user/charger/yp001_charger.c').read_text()
    start = source.index('bool yp001_charger_live_input(')
    end = source.index('\n}\n', start)+3
    (out/'live_input_actual.h').write_text(source[start:end])
    gcc = Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
    env = dict(os.environ, PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
    for mode in (0, 1):
        exe = out / f'policy_{mode}.exe'
        subprocess.run([str(gcc), '-std=c99', '-Wall', '-Wextra', '-Werror',
                        f'-DYP001_OTA_USB_BENCH_TEST={mode}',
                        '-I'+str(ROOT/'ble_app_uart_c/Src/user/ota'), '-I'+str(out), str(cfile), '-o', str(exe)],
                       env=env, check=True, timeout=30)
        subprocess.run([str(exe)], env=env, check=True, timeout=10)
    print('PASS production and bench: battery 49/50/100/unknown, USB-only, unplug, charge, OTG, fault, thermal')


if __name__ == '__main__':
    main()
