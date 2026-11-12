"""SAM | 2026-10-13 15:00 +08:00 | Execute the real firmware request parser."""
from pathlib import Path
import os,subprocess
r=Path(__file__).resolve().parents[2]
out=r/'logs/factory_final_20261013';out.mkdir(parents=True,exist_ok=True)
h=r/'ble_app_uart_c/Src/user/factory/yp001_factory_protocol.h'
if not h.exists():
 print('FAIL: BLE factory protocol is not implemented');raise SystemExit(1)
gcc=Path(r'D:\Program Files\GUI Guider\environment\mingw\bin\gcc.exe')
env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
cmd=[str(gcc),'-std=c99','-Wall','-Wextra','-Werror','-I'+str(h.parent),str(r/'tools/factory_final/tests/test_factory_protocol.c'),'-o',str(out/'protocol_test.exe')]
t=subprocess.run(cmd,env=env,capture_output=True,text=True);log=t.stdout+t.stderr
if not t.returncode:
 t=subprocess.run([str(out/'protocol_test.exe')],env=env,capture_output=True,text=True,timeout=10);log+=t.stdout+t.stderr
(out/'firmware_protocol.log').write_text(log,encoding='utf-8');print(log);raise SystemExit(t.returncode)
