"""SAM | 2026-10-27 +08:00 | Regression for journal-bound baseline replacement; no device writes."""
from pathlib import Path
import os,subprocess,sys
r=Path(__file__).resolve().parents[2];o=r/'logs/r6_install_stages_20261027/boot_handoff';o.mkdir(exist_ok=True);g=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env=dict(os.environ,PATH=str(g.parent)+os.pathsep+os.environ.get('PATH',''))
before='--before' in sys.argv
args=[str(g),'-std=c99','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-Itools/ota/boot','-Ible_app_uart_c/Src/user/ota','tools/ota/test_prepared_baseline_handoff.c','ble_app_uart_c/Src/user/ota/yp001_ota_boot.c','tools/ota/boot/yp001_ota_start.c']
if before:args+=['-DBEFORE_REPAIR']
else:args+=['tools/ota/boot/yp001_ota_entry.c']
args+=['-o',str(o/'handoff_checks.exe')];log=[]
for command in (args,[str(o/'handoff_checks.exe')]):
 p=subprocess.run(command,cwd=r,env=env,capture_output=True,text=True,timeout=60);log.append(p.stdout+p.stderr+f'\nexit={p.returncode}\n');(o/('before.log' if before else 'after.log')).write_text(''.join(log),encoding='utf-8');print(log[-1],end='')
 if p.returncode:raise SystemExit(p.returncode)
