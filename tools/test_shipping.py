"""SAM | 2026-10-13 14:03 +08:00 | Run real C controller with a simulated register bus."""
from pathlib import Path
import os, subprocess
root=Path(__file__).resolve().parents[1]
out=root/'logs/shipping_20261013'
out.mkdir(parents=True,exist_ok=True)
header=root/'ble_app_uart_c/Src/user/charger/yp001_shipping.h'
if not header.exists():
    print('FAIL: shipping controller is not implemented')
    raise SystemExit(1)
gcc=Path(r'D:\Program Files\GUI Guider\environment\mingw\bin\gcc.exe')
env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
cmd=[str(gcc),'-std=c99','-Wall','-Wextra','-Werror','-I'+str(header.parent),str(root/'tools/test_shipping.c'),'-o',str(out/'shipping_test.exe')]
r=subprocess.run(cmd,env=env,capture_output=True,text=True)
log=r.stdout+r.stderr
if r.returncode==0:
    r=subprocess.run([str(out/'shipping_test.exe')],env=env,capture_output=True,text=True,timeout=10)
    log+=r.stdout+r.stderr
(out/'host_test.log').write_text(log,encoding='utf-8')
print(log)
raise SystemExit(r.returncode)
