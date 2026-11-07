"""SAM | 2026-10-20 19:50 +08:00 | Compile the actual read-only geometry CLI against query-only stubs and invalid driver values."""
from pathlib import Path
import os, re, subprocess

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT/'ble_app_uart_c/Src/platform/user_periph_setup.c').read_text(encoding='utf-8-sig')
match = re.search(r'(static int cmd_ota_storage\(.*?\n\})\s*CLI_CMD_REGISTER\("ota_storage"', source, re.S)
assert match, 'read-only OTA storage CLI is not implemented'
body = match[1]
for forbidden in ('hal_flash_write', 'hal_flash_erase', 'nvds_put', 'nvds_del', 'nvds_init'):
    assert forbidden not in body
out = ROOT/'logs/ota_preflight_20261020/storage_cli_test'
out.mkdir(exist_ok=True)
harness = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <assert.h>
#define NVDS_NUM_SECTOR 1
static uint32_t size=0x100000,sector=4096,nvds=0x2fe000;
static char output[1024];static unsigned queries;
static int cli_printf(const char *fmt,...) {
 va_list a;va_start(a,fmt);int n=vsnprintf(output+strlen(output),sizeof(output)-strlen(output),fmt,a);va_end(a);return n;
}
static void hal_flash_get_info(uint32_t *id,uint32_t *bytes){++queries;*id=0x123456;*bytes=size;}
static uint32_t hal_flash_sector_size(void){++queries;return sector;}
static uint32_t nvds_get_start_addr(void){++queries;return nvds;}
'''
harness += body + r'''
int main(void) {
 char *argv[]={(char *)"ota_storage"};
 assert(cmd_ota_storage(2,argv)<0 && queries==0);output[0]=0;
 assert(cmd_ota_storage(1,argv)==0);assert(strstr(output,"flash_bytes=1048576"));
 assert(strstr(output,"nvds_start=0x002FE000"));assert(strstr(output,"nvds_end=0x00300000"));
 sector=0;assert(cmd_ota_storage(1,argv)<0);sector=4096;
 size=0;assert(cmd_ota_storage(1,argv)<0);size=0x100000;
 nvds=0x2ff000;assert(cmd_ota_storage(1,argv)<0);
 nvds=0x2fe001;assert(cmd_ota_storage(1,argv)<0);
 puts("PASS actual storage CLI: geometry, GC reserve, invalid counters, no mutation calls");return 0;
}
'''
(out/'test.c').write_text(harness,encoding='utf8')
gcc=Path(r'D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ.get('PATH',''))
subprocess.run([str(gcc),'-std=c99','-Wall','-Wextra','-Werror',str(out/'test.c'),'-o',str(out/'test.exe')],check=True,env=env)
subprocess.run([str(out/'test.exe')],check=True,env=env)
