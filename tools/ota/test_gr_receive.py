"""SAM | 2026-10-23 +08:00 | Compile real receiver against bounded fault-injecting Flash."""
from pathlib import Path
import os,subprocess
r=Path(__file__).resolve().parents[2];out=r/'logs/ota_receive_20261023';out.mkdir(exist_ok=True)
g=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env=dict(os.environ,PATH=str(g.parent)+os.pathsep+os.environ.get('PATH',''))
subprocess.run([str(g),'-std=c99','-Wall','-Wextra','-Werror','-I'+str(r/'ble_app_uart_c/Src/user/ota'),str(r/'tools/ota/test_gr_receive.c'),str(r/'ble_app_uart_c/Src/user/ota/yp001_ota_receive.c'),str(r/'ble_app_uart_c/Src/user/ota/yp001_ota_wire.c'),'-o',str(out/'test.exe')],env=env,check=True)
subprocess.run([str(out/'test.exe')],env=env,check=True)
