"""SAM | 2026-10-23 +08:00 | Hardware-shaped SDK adapter failure tests; never access the real board."""
from pathlib import Path
import os
import subprocess

root=Path(__file__).resolve().parents[2]
out=root/'logs/ota_gr_project_sdk_adapter_20261023'
out.mkdir(exist_ok=True)
(out/'gr_includes.h').write_text('''#include <stdint.h>
int sys_security_enable_status_check(void);
void app_boot_security_clock_set(void);
void ll_cgc_disable_force_off_secu_hclk(void);
void ll_cgc_disable_force_off_secu_div4_pclk(void);
void ll_cgc_disable_force_off_rng_hclk(void);
void ll_cgc_disable_force_off_hmac_hclk(void);
void ll_cgc_disable_force_off_pkc_hclk(void);
''')
(out/'grx_sys.h').write_text('#include <stdint.h>\n')
(out/'hal_flash.h').write_text('#include <stdint.h>\nuint32_t hal_flash_read(uint32_t,void*,uint32_t);\n')
(out/'custom_config.h').write_text('#define SECURITY_CFG_VAL 0\n')
(out/'bootloader_config.h').write_text('#define SOC_GR5526 1\n#define BOOTLOADER_SIGN_ENABLE 1\n#define BOOTLOADER_BOOT_PORT_ENABLE 0\n#define BOOTLOADER_WDT_ENABLE 1\n')
(out/'test.c').write_text(r'''
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include "yp001_ota_project_sdk.h"
#include "rsa.h"
static int secure,wdt_fail,wdt_calls,clocks,short_read,sha_error,pss_error,sha_calls,pss_calls;
int sys_security_enable_status_check(void){return secure;}
int bootloader_wdt_service(void*p){(void)p;wdt_calls++;return wdt_fail;}
void app_boot_security_clock_set(void){clocks++;}
void ll_cgc_disable_force_off_secu_hclk(void){clocks++;}
void ll_cgc_disable_force_off_secu_div4_pclk(void){clocks++;}
void ll_cgc_disable_force_off_rng_hclk(void){clocks++;}
void ll_cgc_disable_force_off_hmac_hclk(void){clocks++;}
void ll_cgc_disable_force_off_pkc_hclk(void){clocks++;}
uint32_t hal_flash_read(uint32_t a,void*p,uint32_t n){(void)a;memset(p,7,n);return short_read?n-1:n;}
int gm_drv_sha_encrypt(const void*c,const uint8_t*p,uint32_t n,uint8_t*out){(void)c;(void)p;(void)n;sha_calls++;memset(out,9,32);return sha_error;}
int bl_rsa_rsassa_pss_verify(bl_rsa_context*c,const uint8_t*h,const uint8_t*s){(void)h;(void)s;assert(c->len==256&&c->pk&&c->sk==0);pss_calls++;return pss_error;}
int main(void){
 yp_project_verify p;unsigned char pin[32],data[904],hash[32];memset(pin,1,32);
 secure=1;assert(yp_boot_project_sdk_init(&p,pin,pin,pin));assert(!p.read&&!clocks);
 secure=0;wdt_fail=1;assert(yp_boot_project_sdk_init(&p,pin,pin,pin));assert(!p.read&&!clocks);
 wdt_fail=0;assert(!yp_boot_project_sdk_init(&p,pin,pin,pin));assert(clocks==6);
 assert(!memcmp(p.layout_hash,pin,32)&&!memcmp(p.data_hash,pin,32)&&!memcmp(p.public_hash,pin,32));
 assert(!p.read(0,0x202000,data,904));short_read=1;assert(p.read(0,0x202000,data,904));short_read=0;
 assert(!p.hash_ram(0,data,904,hash));sha_error=1;assert(p.hash_ram(0,data,904,hash));sha_error=0;
 assert(!p.pss(0,data,data,hash));pss_error=1;assert(p.pss(0,data,data,hash));
 secure=1;sha_calls=pss_calls=0;assert(p.hash_flash(0,0x202000,10,hash));assert(p.pss(0,data,data,hash));assert(!sha_calls&&!pss_calls);
 assert(wdt_calls>0);puts("PASS SDK adapter: secure-mode refusal, short reads, positive crypto errors, watchdog and pinned context");return 0;
}
''')
gcc=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ.get('PATH',''))
cmd=[str(gcc),'-std=c99','-Wall','-Wextra','-Werror','-I'+str(out),
     '-I'+str(root/'tools/ota/boot'),'-I'+str(root/'ble_app_uart_c/Src/user/ota'),
     '-I'+str(root/'SDK/components/libraries/app_bootloader/sign_verify/inc'),
     str(out/'test.c'),str(root/'tools/ota/boot/yp001_ota_project_sdk.c'),'-o',str(out/'test.exe')]
subprocess.run(cmd,env=env,check=True)
subprocess.run([str(out/'test.exe')],env=env,check=True)
