"""SAM | 2026-10-27 +08:00 | Check actual coordinator read-validation/lease sequencing, host only."""
from pathlib import Path
import os,subprocess
r=Path(__file__).resolve().parents[2];g=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe');o=r/'logs/ota_fix_execution_20261106/gr_activation';o.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,PATH=str(g.parent)+os.pathsep+os.environ.get('PATH',''))
args=[str(g),'-std=c99','-Wall','-Wextra','-Werror','-Ible_app_uart_c/Src/user/ota','-Ible_app_uart_c/Src/external/cJSON-1.7.19','tools/ota/test_gr_activation_stages.c','ble_app_uart_c/Src/user/ota/yp001_ota.c','ble_app_uart_c/Src/user/ota/yp001_ota_wire.c','ble_app_uart_c/Src/external/cJSON-1.7.19/cJSON.c','-o',str(o/'stage_checks.exe')]
# SAM | 2026-11-06 +08:00 | Host-only linkage stubs never access hardware.
(o/'platform_sdk.h').write_text('''#define MEM_POWER_FULL_MODE 0
static inline void mem_pwr_mgmt_mode_set(int mode){(void)mode;}
''')
(o/'power_stubs.c').write_text('''#include <stdbool.h>
bool yp_psram_mem_init(void){return true;}
int cat1_debug_power(int n,char **v){(void)n;(void)v;return 0;}
''')
args[1:1]=['-I'+str(o),str(o/'power_stubs.c')]
log=[]
for command in (args,[str(o/'stage_checks.exe')]):
 p=subprocess.run(command,cwd=r,env=env,capture_output=True,text=True,timeout=60)
 log.append(p.stdout+p.stderr+f'\nexit={p.returncode}\n');(o/'result.log').write_text(''.join(log),encoding='utf-8');print(log[-1],end='')
 if p.returncode:raise SystemExit(p.returncode)
