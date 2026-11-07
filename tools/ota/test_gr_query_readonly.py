"""SAM | 2026-10-27 +08:00 | Verify the actual coordinator QUERY fix; host-only, never compile target firmware or run OTA."""
from pathlib import Path
import os,subprocess
r=Path(__file__).resolve().parents[2];g=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe');o=r/'logs/r6_install_stages_20261027/live_after_power';env=dict(os.environ,PATH=str(g.parent)+os.pathsep+os.environ.get('PATH',''))
a=[str(g),'-std=c99','-Wall','-Wextra','-Werror','-Ible_app_uart_c/Src/user/ota','-Ible_app_uart_c/Src/external/cJSON-1.7.19','tools/ota/test_gr_query_readonly.c','ble_app_uart_c/Src/user/ota/yp001_ota.c','ble_app_uart_c/Src/user/ota/yp001_ota_wire.c','ble_app_uart_c/Src/external/cJSON-1.7.19/cJSON.c','-o',str(o/'query_readonly.exe')];log=[]
for cmd in (a,[str(o/'query_readonly.exe')]):
 p=subprocess.run(cmd,cwd=r,env=env,capture_output=True,text=True,timeout=60);log.append(p.stdout+p.stderr+f'\nexit={p.returncode}\n');(o/'query_after.log').write_text(''.join(log),encoding='utf-8');print(log[-1],end='')
 if p.returncode:raise SystemExit(p.returncode)
