"""SAM | 2026-10-13 08:35 +08:00 | Build actual C business logic because model-only tests miss integration errors."""
from pathlib import Path
import os, subprocess
root = Path(__file__).resolve().parents[2]
gcc = Path(r'D:\Program Files\GUI Guider\environment\mingw\bin\gcc.exe')
out = root/'logs/business_20261013'
out.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
sources = ['tools/business/test_gr_business.c','ble_app_uart_c/Src/user/business/yp001_business.c','ble_app_uart_c/Src/user/business/yp_name_glyphs.c','ble_app_uart_c/Src/external/cJSON-1.7.19/cJSON.c']
cmd = [str(gcc), '-std=c99','-Wall','-Wextra','-Werror','-DYP_BUSINESS_HOST_TEST','-I'+str(root/'ble_app_uart_c/Src/user/business'),'-I'+str(root/'ble_app_uart_c/Src/external/cJSON-1.7.19')]
# SAM | 2026-10-28 17:10 +08:00 | Build production and USB-bench variants because bench motion relaxation must not leak into the default build.
code = 0
for name, defines in (('gr_business_test', []), ('gr_business_bench_test', ['-DYP001_OTA_USB_BENCH_TEST=1'])):
    result = subprocess.run(cmd+defines+[str(root/x) for x in sources]+['-o',str(out/(name+'.exe'))],env=env,capture_output=True,text=True)
    log = result.stdout+result.stderr
    if result.returncode == 0:
        result = subprocess.run([str(out/(name+'.exe'))],env=env,capture_output=True,text=True,timeout=20)
        log += result.stdout+result.stderr
    (out/(name+'.log')).write_text(log,encoding='utf-8')
    print(name+': '+log)
    code = code or result.returncode
raise SystemExit(code)
