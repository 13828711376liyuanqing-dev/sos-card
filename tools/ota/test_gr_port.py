"""SAM | 2026-10-23 +08:00 | Compile production port against a confined Flash model."""
from pathlib import Path
import os,subprocess
r=Path(__file__).resolve().parents[2];out=r/'logs/gr_port_20261023';out.mkdir(exist_ok=True)
(out/'hal_flash.h').write_text('#include <stdint.h>\n#include <stdbool.h>\nvoid hal_flash_get_info(uint32_t*,uint32_t*);\nuint32_t hal_flash_sector_size(void);\nuint32_t hal_flash_read(uint32_t,uint8_t*,uint32_t);\nuint32_t hal_flash_write(uint32_t,const uint8_t*,uint32_t);\nbool hal_flash_erase(uint32_t,uint32_t);\n')
(out/'app_aon_wdt.h').write_text('#include <stdint.h>\n#define APP_DRV_SUCCESS 0\nuint16_t app_aon_wdt_refresh(void);\n')
(out/'gr_soc.h').write_text('#include <stdint.h>\nuint32_t nvds_get_start_addr(void);\n')
# SAM | 2026-10-23 19:26 +08:00 | Model the two separately compiled running versions without changing production version files.
(out/'yp001_fw_version.h').write_text('extern char yp_test_product_version[16];\n#define YP001_PRODUCT_VERSION yp_test_product_version\n',encoding='utf-8')
gcc=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ.get('PATH',''))
subprocess.run([str(gcc),'-std=c99','-Wall','-Wextra','-Werror','-I'+str(out),'-I'+str(r/'ble_app_uart_c/Src/user/ota'),'-I'+str(r/'ble_app_uart_c/Src/config'),str(r/'tools/ota/test_gr_port.c'),str(r/'ble_app_uart_c/Src/user/ota/yp001_ota_port.c'),str(r/'ble_app_uart_c/Src/user/ota/yp001_ota_boot.c'),str(r/'ble_app_uart_c/Src/user/ota/yp001_ota_receive.c'),str(r/'ble_app_uart_c/Src/user/ota/yp001_ota_wire.c'),'-o',str(out/'test.exe')],check=True,env=env)
subprocess.run([str(out/'test.exe')],check=True,env=env)
