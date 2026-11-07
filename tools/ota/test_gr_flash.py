"""SAM | 2026-10-20 20:22 +08:00 | Compile real Flash adapter against fault-injecting SDK-shaped HAL; never access hardware."""
from pathlib import Path
import os, subprocess,re
r=Path(__file__).resolve().parents[2]
o=r/'logs/ota_preflight_20261020/flash_backend_test';o.mkdir(exist_ok=True)
(o/'gr_soc.h').write_text('#include <stdint.h>\nuint32_t nvds_get_start_addr(void);\n')
(o/'hal_flash.h').write_text('''#include <stdint.h>
#include <stdbool.h>
void hal_flash_get_info(uint32_t*,uint32_t*);
uint32_t hal_flash_sector_size(void);
uint32_t hal_flash_read(uint32_t,uint8_t*,uint32_t);
uint32_t hal_flash_write(uint32_t,const uint8_t*,uint32_t);
bool hal_flash_erase(uint32_t,uint32_t);
''')
gcc=Path(r'D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe');env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ.get('PATH',''))
subprocess.run([str(gcc),'-std=c99','-Wall','-Wextra','-Werror','-pedantic','-I'+str(o),'-I'+str(r/'tools/ota/boot'),'-I'+str(r/'ble_app_uart_c/Src/user/ota'),str(r/'tools/ota/test_gr_flash.c'),str(r/'tools/ota/boot/yp001_ota_flash.c'),str(r/'tools/ota/boot/yp001_ota_start.c'),str(r/'ble_app_uart_c/Src/user/ota/yp001_ota_boot.c'),'-o',str(o/'test.exe')],env=env,check=True)
subprocess.run([str(o/'test.exe')],env=env,check=True)
# SAM | 2026-10-21 +08:00 | Extract actual SDK structure, so a future trailer change breaks the bound assumption.
sdk=(r/'SDK/components/libraries/app_bootloader/sign_verify/src/sign_verify.c').read_text()
shape=re.search(r'typedef struct\s*\{\s*uint32_t\s+reserved0;.*?\}\s*bl_fw_info_t;',sdk,re.S)
assert shape,'SDK signature structure changed'
macros='\n'.join(re.search(r'^#define\s+'+name+r'\s+[^\r\n]+',sdk,re.M)[0] for name in ['SIGNATURE_SIZE','RSA_KEY_SIZE','RSA_PUBLIC_KEY_SIZE','ECIES_PUBLIC_KEY_SIZE'])
# SAM | 2026-10-23 +08:00 | Offline native inspector depends on offsets as well
# as total size; fail if an SDK change moves the authenticated public key/span.
probe='#include <stddef.h>\n#include "yp001_ota_flash.h"\n'+macros+'\n'+shape[0]+'\nint main(void){return sizeof(bl_fw_info_t)==YP_BOOT_SIGNATURE_TRAILER_BYTES && offsetof(bl_fw_info_t,rsa)==128 && offsetof(bl_fw_info_t,signature)==648 ?0:1;}\n'
(o/'signature_size.c').write_text(probe)
subprocess.run([str(gcc),'-std=c99','-Wall','-Wextra','-Werror','-I'+str(r/'tools/ota/boot'),'-I'+str(r/'ble_app_uart_c/Src/user/ota'),str(o/'signature_size.c'),'-o',str(o/'signature_size.exe')],env=env,check=True)
subprocess.run([str(o/'signature_size.exe')],env=env,check=True)
print('PASS actual SDK trailer size and public-key/signature offsets match protected extent and inspector')
