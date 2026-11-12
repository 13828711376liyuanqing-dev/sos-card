"""SAM | 2026-10-14 14:17 +08:00 | Test real diagnostic C snapshots because a
successful HAL return must not conceal a changed input buffer or failed TX.
This host test does not verify FIFO writes, pins, or physical UART reliability.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

from test_cat1_bridge import function, GCC, ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default='ble_app_uart_c/Src/platform/user_periph_setup.c')
    parser.add_argument('--label', default='main')
    args = parser.parse_args()
    source = (ROOT / args.source).read_text(encoding='utf-8-sig')
    declarations = re.search(
        r'typedef struct\s*\{[^{}]*\}\s*cat1_at_trace_t;\s*'
        r'volatile cat1_at_trace_t g_cat1_at_trace;', source, re.S)
    if declarations is None:
        print('FAIL: diagnostic has no RAM evidence for the bytes passed to UART')
        return 1
    prefix = r'''
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#define APP_UART_ID_4 4
#define APP_DRV_SUCCESS 0
#define CHECK(v) do { if (!(v)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#v); return 1; } } while(0)
static bool s_uart4_ready=true, fail_init, mutate;
static uint32_t s_cat_diag_dropped;
static uint16_t tx_result;
static unsigned calls;
static uint8_t sent[32];
static uint16_t sent_len;
static char output[4096];
static size_t used;
static void __DMB(void){}
static void uart4_init(void){s_uart4_ready=!fail_init;}
static void cli_printf(const char *fmt,...){
    va_list ap; va_start(ap,fmt);
    int n=vsnprintf(output+used,sizeof(output)-used,fmt,ap);va_end(ap);
    if(n<0||(size_t)n>=sizeof(output)-used) exit(2);
    used+=(size_t)n;
}
'''
    stubs = r'''
static uint16_t app_uart_transmit_sync(int id,uint8_t *data,uint16_t n,uint32_t timeout){
    if(id!=4||timeout!=1000||n>sizeof(sent)) exit(2);
    ++calls;sent_len=n;memcpy(sent,data,n);
    if(mutate&&n==4)data[0]=0x40;
    return tx_result;
}
'''
    cases = r'''
int main(void){
    char *at[]={"cat_diag","AT"};
    CHECK(cmd_cat_diag(2,at)==0);
    CHECK(calls==1&&sent_len==4&&!memcmp(sent,"AT\r\n",4));
    CHECK(g_cat1_at_trace.seq==1&&g_cat1_at_trace.phase==2&&g_cat1_at_trace.length==4);
    CHECK(g_cat1_at_trace.before==0x41540D0A&&g_cat1_at_trace.after==0x41540D0A);
    CHECK(g_cat1_at_trace.status==0&&strstr(output,"pre=41540D0A post=41540D0A"));
    used=0;output[0]=0;mutate=true;
    CHECK(cmd_cat_diag(2,at)==0);
    CHECK(g_cat1_at_trace.seq==2&&g_cat1_at_trace.before==0x41540D0A);
    CHECK(g_cat1_at_trace.after==0x40540D0A&&strstr(output,"post=40540D0A"));
    CHECK(!memcmp(sent,"AT\r\n",4));
    mutate=false;tx_result=9;used=0;output[0]=0;
    CHECK(cmd_cat_diag(2,at)==-1);
    CHECK(g_cat1_at_trace.status==9&&g_cat1_at_trace.phase==2);
    CHECK(strstr(output,"tx=0x0009"));
    tx_result=0;uint32_t seq=g_cat1_at_trace.seq;unsigned previous=calls;
    fail_init=true;s_uart4_ready=false;
    CHECK(cmd_cat_diag(2,at)==-1&&calls==previous&&g_cat1_at_trace.seq==seq);
    fail_init=false;s_uart4_ready=true;used=0;output[0]=0;
    char *ati[]={"cat_diag","ATI"};
    CHECK(cmd_cat_diag(2,ati)==0&&sent_len==5&&!memcmp(sent,"ATI\r\n",5));
    CHECK(g_cat1_at_trace.seq==seq&&!strstr(output,"TXRAW"));
    previous=calls;char *invalid[]={"cat_diag","AT_BAD"};
    CHECK(cmd_cat_diag(2,invalid)==-1&&calls==previous&&g_cat1_at_trace.seq==seq);
    puts("PASS: real C pre/post bytes, mutation visibility, HAL failure, init failure and non-AT isolation");
    return 0;
}
'''
    code = (prefix + declarations.group(0) + '\n' + stubs +
            function(source, 'cat1_at_pack') + '\n' +
            function(source, 'cmd_cat_diag') + '\n' + cases)
    folder = ROOT / 'logs/uart4_txraw_20261014'
    folder.mkdir(parents=True, exist_ok=True)
    cfile = folder / (args.label + '_txraw_test.c')
    exe = folder / (args.label + '_txraw_test.exe')
    cfile.write_text(code, encoding='utf-8')
    env = dict(os.environ, PATH=str(GCC.parent)+os.pathsep+os.environ.get('PATH',''))
    subprocess.run([str(GCC),'-std=c99','-Wall','-Wextra',str(cfile),'-o',str(exe)],check=True,env=env)
    result = subprocess.run([str(exe)],capture_output=True,text=True,env=env)
    report = result.stdout+result.stderr+'\nEXIT='+str(result.returncode)
    (folder/(args.label+'_txraw_test.log')).write_text(report,encoding='utf-8')
    print(report)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
