"""SAM | 2026-10-27 +08:00 | Compile actual application port/Boot with confined fake Flash, no hardware access."""
from pathlib import Path
import os, subprocess
r=Path(__file__).resolve().parents[2]
o=r/'logs/gr_port_20261023'
o.mkdir(parents=True,exist_ok=True)
# SAM | 2026-11-06 +08:00 | Build a standalone confined fixture instead of relying on a prior port-suite run.
(o/'hal_flash.h').write_text('#include <stdint.h>\n#include <stdbool.h>\nvoid hal_flash_get_info(uint32_t*,uint32_t*);\nuint32_t hal_flash_sector_size(void);\nuint32_t hal_flash_read(uint32_t,uint8_t*,uint32_t);\nuint32_t hal_flash_write(uint32_t,const uint8_t*,uint32_t);\nbool hal_flash_erase(uint32_t,uint32_t);\n')
(o/'app_aon_wdt.h').write_text('#include <stdint.h>\n#define APP_DRV_SUCCESS 0\nuint16_t app_aon_wdt_refresh(void);\n')
(o/'gr_soc.h').write_text('#include <stdint.h>\nuint32_t nvds_get_start_addr(void);\n')
# SAM | 2026-10-23 19:26 +08:00 | Model the two separately compiled running versions without changing production version files.
(o/'yp001_fw_version.h').write_text('extern char yp_test_product_version[16];\n#define YP001_PRODUCT_VERSION yp_test_product_version\n',encoding='utf-8')
# SAM | 2026-11-06 +08:00 | Receipt tests model PSRAM unavailable; they never enter staging or touch hardware.
(o/'psram_unavailable.c').write_text('#include <stdbool.h>\n#include <stdint.h>\nbool yp_psram_mem_init(void){return false;}\nbool yp_psram_ota_region(void **p,uint32_t *n){*p=0;*n=0;return false;}\n')

g=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env=dict(os.environ,PATH=str(g.parent)+os.pathsep+os.environ.get('PATH',''))
args=[str(g),'-std=c99','-Wall','-Wextra','-Werror','-include','stdlib.h','-I'+str(o),'-I'+str(r/'ble_app_uart_c/Src/user/ota'),'-I'+str(r/'ble_app_uart_c/Src/config'),str(r/'tools/ota/test_gr_install_receipt.c')]
args += [str(r/'ble_app_uart_c/Src/user/ota'/p) for p in ('yp001_ota_port.c','yp001_ota_boot.c','yp001_ota_receive.c','yp001_ota_wire.c')]
args.append(str(o/'psram_unavailable.c'))
log=[]
# Avoid Windows' legacy installer-name elevation heuristic; this is a normal host test.
for command in (args+['-o',str(o/'receipt_checks.exe')],[str(o/'receipt_checks.exe')]):
 p=subprocess.run(command,cwd=r,env=env,capture_output=True,text=True,timeout=60)
 log.append(p.stdout+p.stderr+f'\nexit={p.returncode}\n')
 (o/'install_receipt.log').write_text(''.join(log),encoding='utf-8')
 print(log[-1],end='')
 if p.returncode:raise SystemExit(p.returncode)
