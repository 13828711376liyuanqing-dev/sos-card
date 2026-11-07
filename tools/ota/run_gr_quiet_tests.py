# SAM | 2026-10-25 +08:00 | Real coordinator quiet-window integration, host only.
from pathlib import Path
import subprocess,os
r=Path(__file__).resolve().parents[2];g=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe');o=r/'logs/uart_window_20261025';o.mkdir(exist_ok=True)
e=os.environ.copy();e['PATH']=str(g.parent)+os.pathsep+e['PATH']
a=[str(g),'-std=c99','-Wall','-Wextra','-Werror','-Ible_app_uart_c/Src/user/ota','-Ible_app_uart_c/Src/external/cJSON-1.7.19','tools/ota/test_gr_quiet_integration.c','ble_app_uart_c/Src/user/ota/yp001_ota.c','ble_app_uart_c/Src/user/ota/yp001_ota_wire.c','ble_app_uart_c/Src/external/cJSON-1.7.19/cJSON.c','-o',str(o/'gr_quiet.exe')]
log=''
for cmd in (a,[str(o/'gr_quiet.exe')]):
 p=subprocess.run(cmd,cwd=r,capture_output=True,text=True,env=e,timeout=60);log+=p.stdout+p.stderr+'exit='+str(p.returncode)+'\n';print(log);(o/'gr_quiet_test.log').write_text(log)
 if p.returncode:raise SystemExit(p.returncode)
