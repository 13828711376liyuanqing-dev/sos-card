"""SAM | 2026-10-25 +08:00 | Only new retirement boundaries, using existing confined HAL headers."""
from pathlib import Path
import subprocess,os
r=Path(__file__).resolve().parents[2];o=r/'logs/gr_port_20261023';g=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
e=os.environ.copy();e['PATH']=str(g.parent)+os.pathsep+e['PATH']
args=[str(g),'-std=c99','-Wall','-Wextra','-Werror','-I'+str(o),'-I'+str(r/'ble_app_uart_c/Src/user/ota'),'-I'+str(r/'ble_app_uart_c/Src/config'),str(r/'tools/ota/test_gr_retire_port.c')]
args += [str(r/'ble_app_uart_c/Src/user/ota'/p) for p in ('yp001_ota_port.c','yp001_ota_boot.c','yp001_ota_receive.c','yp001_ota_wire.c')]
subprocess.run(args+['-o',str(o/'retire.exe')],check=True,env=e)
subprocess.run([str(o/'retire.exe')],check=True,env=e)
