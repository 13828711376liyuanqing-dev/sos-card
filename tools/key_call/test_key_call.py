"""SAM | 2026-11-06 +08:00 | Build the real yp001_business.c on the host (MinGW gcc, same stubs idea as tools/name_push) and run
test_key_call.c: left or right key answers an incoming call / hangs up a dialing or connected one."""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GCC = Path(r'D:\Program Files\GUI Guider\environment\mingw\bin\gcc.exe')
BUS = ROOT / 'ble_app_uart_c' / 'Src' / 'user' / 'business'
CJSON = ROOT / 'ble_app_uart_c' / 'Src' / 'external' / 'cJSON-1.7.19'
STUBS = ROOT / 'tools' / 'name_push' / 'stubs'
OUT = ROOT / 'logs' / 'key_call_20261106'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PATH=str(GCC.parent) + os.pathsep + os.environ['PATH'])
    exe = OUT / 'test_key_call.exe'
    cmd = [str(GCC), '-std=c99', '-Wall', '-Wextra', '-Werror', '-Wno-error=unused-variable', '-Wno-error=discarded-qualifiers', '-DYP_BUSINESS_HOST_TEST',
           '-I' + str(STUBS), '-I' + str(BUS), '-I' + str(CJSON),
           str(HERE / 'test_key_call.c'), str(BUS / 'yp001_business.c'), str(BUS / 'yp_name_glyphs.c'),
           str(CJSON / 'cJSON.c'), '-o', str(exe)]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout + r.stderr)
        return 1
    r = subprocess.run([str(exe)], env=env, capture_output=True, text=True, timeout=30)
    print(r.stdout + r.stderr, end='')
    return r.returncode


if __name__ == '__main__':
    sys.exit(main())
