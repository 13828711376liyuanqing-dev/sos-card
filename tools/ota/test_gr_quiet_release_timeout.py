"""SAM | 2026-10-29 06:19 +08:00 | Build and run the GR phase-4 release-timeout reproduction against the real yp001_ota.c; host only."""
from pathlib import Path
import os, subprocess
r = Path(__file__).resolve().parents[2]; g = Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
o = r / 'logs/gr_quiet_release_timeout_20261029'; o.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, PATH=str(g.parent) + os.pathsep + os.environ.get('PATH', ''))
a = [str(g), '-std=c99', '-Wall', '-Wextra', '-Werror', '-Ible_app_uart_c/Src/user/ota', '-Ible_app_uart_c/Src/external/cJSON-1.7.19',
     'tools/ota/test_gr_quiet_release_timeout.c', 'ble_app_uart_c/Src/user/ota/yp001_ota.c', 'ble_app_uart_c/Src/user/ota/yp001_ota_wire.c',
     'ble_app_uart_c/Src/external/cJSON-1.7.19/cJSON.c', '-o', str(o / 'release_timeout.exe')]
for cmd in (a, [str(o / 'release_timeout.exe')]):
    p = subprocess.run(cmd, cwd=r, env=env, capture_output=True, text=True, timeout=60)
    print(p.stdout + p.stderr, end='')
    if p.returncode: raise SystemExit(p.returncode)
