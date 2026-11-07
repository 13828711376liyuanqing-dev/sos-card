"""SAM | 2026-10-24 +08:00 | Exercise actual version CLI without SWD injection or Flash mutation."""
from pathlib import Path
import os, re, subprocess
ROOT=Path(__file__).resolve().parents[2]
source=(ROOT/'ble_app_uart_c/Src/platform/user_periph_setup.c').read_text(encoding='utf-8-sig')
body=re.search(r'(static int cmd_fw_version\(.*?\n\})',source,re.S)[1]
out=ROOT/'logs/ota_wdt_fix_20261024/cli_host_test'
out.mkdir(parents=True,exist_ok=True)
harness=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#define YP001_FW_IDENTITY "test"
#define YP001_PRODUCT_VERSION "1.0.2"
#define VERSION 3
#define APP_DRV_SUCCESS 0
typedef struct {uint32_t size,version;uint8_t identity[32];} yp_boot_image;
static char output[2048];static int checks,refreshes,refresh_result,verify_result;
static void cli_printf(const char *fmt,...){va_list a;va_start(a,fmt);vsnprintf(output+strlen(output),sizeof(output)-strlen(output),fmt,a);va_end(a);}
static bool yp001_ota_port_provisioned(void){return true;}
unsigned ll_aon_wdt_is_active_flag_running(void){return 1;}
uint16_t app_aon_wdt_refresh(void){refreshes++;return refresh_result;}
int yp001_ota_running_image(uint32_t version,yp_boot_image *image){checks++;assert(version==1000002);image->size=426304;image->version=version;return verify_result;}
'''
tests=r'''
int main(void){char *normal[]={"fw_version"},*verify[]={"fw_version","verify"},*bad[]={"fw_version","bad"};
 assert(cmd_fw_version(1,normal)==0);assert(checks==0&&refreshes==0);
 assert(cmd_fw_version(2,bad)<0);assert(checks==0&&refreshes==0);
 output[0]=0;assert(cmd_fw_version(2,verify)==0);assert(checks==1&&refreshes==1);assert(strstr(output,"signature_ok=1"));
 output[0]=0;verify_result=-1;assert(cmd_fw_version(2,verify)<0);assert(strstr(output,"signature_ok=0"));
 output[0]=0;refresh_result=1;assert(cmd_fw_version(2,verify)<0);assert(checks==2);assert(strstr(output,"signature_ok=0"));
 puts("PASS version CLI: unchanged query, invalid argument, real verifier result, WDT failure prevents verification");return 0;
}
'''
(out/'test.c').write_text(harness+body+tests,encoding='utf-8')
gcc=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ.get('PATH',''))
subprocess.run([str(gcc),'-std=c99','-Wall','-Wextra','-Werror',str(out/'test.c'),'-o',str(out/'test.exe')],check=True,env=env)
subprocess.run([str(out/'test.exe')],check=True,env=env)
