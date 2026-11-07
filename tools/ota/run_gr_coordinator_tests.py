# SAM | 2026-10-12 19:28 +08:00 | Reproducible headless host checks because assertions must not display Windows dialogs.
from pathlib import Path
import os
import subprocess

ROOT = Path(__file__).resolve().parents[2]
GCC = Path(r'D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
OUT = ROOT / 'logs/ota_impl_20261012'
OUT.mkdir(parents=True, exist_ok=True)
env = os.environ.copy()
env['PATH'] = str(GCC.parent) + os.pathsep + env.get('PATH', '')
exe = OUT / 'test_gr_coordinator.exe'
args = [str(GCC), '-std=c99', '-Wall', '-Wextra', '-Werror',
        '-Ible_app_uart_c/Src/user/ota', '-Ible_app_uart_c/Src/external/cJSON-1.7.19',
        'tools/ota/test_gr_coordinator.c', 'ble_app_uart_c/Src/user/ota/yp001_ota.c',
        'ble_app_uart_c/Src/user/ota/yp001_ota_wire.c', 'ble_app_uart_c/Src/external/cJSON-1.7.19/cJSON.c', '-o', str(exe)]
flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
log = []
for command in [args, [str(exe)]]:
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True,
                            creationflags=flags, timeout=60)
    log.append(result.stdout + result.stderr + f'\nexit={result.returncode}\n')
    (OUT / 'coordinator_host_test.log').write_text(''.join(log), encoding='utf-8')
    print(log[-1], end='')
    if result.returncode:
        raise SystemExit(result.returncode)
