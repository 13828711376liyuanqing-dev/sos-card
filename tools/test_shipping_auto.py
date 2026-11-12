"""SAM | 2026-11-08 +08:00 | Build and execute the shipping coordinator on the host."""
from pathlib import Path
import os
import subprocess

root = Path(__file__).resolve().parents[1]
out = root / 'logs/shipping_auto_20261108'
out.mkdir(parents=True, exist_ok=True)
gcc = Path(r'D:\Program Files\GUI Guider\environment\mingw\bin\gcc.exe')
env = dict(os.environ, PATH=str(gcc.parent) + os.pathsep + os.environ['PATH'])
exe = out / 'shipping_auto_test.exe'
result = subprocess.run([str(gcc), '-std=c99', '-Wall', '-Wextra', '-Werror',
    '-I' + str(root / 'ble_app_uart_c/Src/user/charger'),
    str(root / 'tools/test_shipping_auto.c'), '-o', str(exe)], env=env, capture_output=True, text=True)
log = result.stdout + result.stderr
if result.returncode == 0:
    result = subprocess.run([str(exe)], env=env, capture_output=True, text=True, timeout=10)
    log += result.stdout + result.stderr
(out / ('green.log' if result.returncode == 0 else 'red.log')).write_text(log, encoding='utf-8')
print(log)
raise SystemExit(result.returncode)
