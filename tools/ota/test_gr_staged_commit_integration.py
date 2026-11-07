"""SAM | 2026-10-27 +08:00 | Combined production coordinator/port/Boot execution; no device access."""
from pathlib import Path
import os,subprocess
r=Path(__file__).resolve().parents[2];o=r/'logs/r6_quiet_once_20261027/activation_stages';o.mkdir(exist_ok=True);g=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env=dict(os.environ,PATH=str(g.parent)+os.pathsep+os.environ.get('PATH',''))
args=[str(g),'-std=c99','-Wall','-Wextra','-Werror','-I'+str(r/'logs/gr_port_20261023'),'-Ible_app_uart_c/Src/user/ota','-Ible_app_uart_c/Src/config','-Ible_app_uart_c/Src/external/cJSON-1.7.19','tools/ota/test_gr_staged_commit_integration.c']
args += [str(r/'ble_app_uart_c/Src/user/ota'/p) for p in ('yp001_ota_port.c','yp001_ota_boot.c','yp001_ota_receive.c','yp001_ota_wire.c')]
args += ['ble_app_uart_c/Src/external/cJSON-1.7.19/cJSON.c','-o',str(o/'combined_checks.exe')]
log=[]
for command in (args,[str(o/'combined_checks.exe')],[str(o/'combined_checks.exe'),'--health']):
 p=subprocess.run(command,cwd=r,env=env,capture_output=True,text=True,timeout=60);log.append(p.stdout+p.stderr+f'\nexit={p.returncode}\n');(o/'combined_result.log').write_text(''.join(log),encoding='utf-8');print(log[-1],end='')
 if p.returncode:raise SystemExit(p.returncode)
