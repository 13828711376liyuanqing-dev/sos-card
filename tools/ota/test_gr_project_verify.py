"""SAM | 2026-10-23 +08:00 | Build portable fail-closed native verifier tests; no GR hardware operations."""
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
out = root/'logs/ota_gr_project_verify_20261023'
out.mkdir(exist_ok=True)
gcc = Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env = dict(os.environ, PATH=str(gcc.parent)+os.pathsep+os.environ.get('PATH',''))
subprocess.run([str(gcc), '-std=c99', '-Wall', '-Wextra', '-Werror', '-pedantic',
                '-I'+str(root/'tools/ota/boot'), '-I'+str(root/'ble_app_uart_c/Src/user/ota'),
                str(root/'tools/ota/test_gr_project_verify.c'),
                str(root/'tools/ota/boot/yp001_ota_project_verify.c'), '-o', str(out/'test.exe')], env=env, check=True)
subprocess.run([str(out/'test.exe')], env=env, check=True)
