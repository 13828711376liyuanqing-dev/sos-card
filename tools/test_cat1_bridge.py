"""SAM | 2026-10-10 16:58 +08:00 | Execute actual C bridge functions with host HAL stubs because UART framing must survive fragmentation.

Only HAL/CLI calls are stubbed. Functions and ring state are extracted from the
firmware source, not reimplemented. This verifies software, never physical UART.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
GCC = Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')

def function(source, name):
    match = re.search(r'(?:static\s+)?\w+\s+' + name + r'\([^;]*?\)\s*\{', source)
    if not match:
        raise ValueError('Missing function: ' + name)
    start = match.start()
    pos = match.end() - 1
    level = 1
    end = pos + 1
    while level:
        level += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--baseline', action='store_true')
    opts = ap.parse_args()
    source_path = ROOT / 'ble_app_uart_c/Src/platform/user_periph_setup.c'
    if opts.baseline:
        source_path = ROOT / 'logs/cat1_antenna_20261010/baseline/ble_app_uart_c/Src/platform/user_periph_setup.c'
    source = source_path.read_text(encoding='utf-8-sig')
    state_start = re.search(r'static (?:volatile )?bool s_uart4_ready;', source).start()
    globals_c = source[state_start:source.index('static void cat_diag_poll(')]
    prefix = r'''
#include <assert.h>
#include <stdlib.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <stdarg.h>
/* Return a normal failing exit code; never invoke Windows JIT debugging. */
#undef assert
#define assert(test) do { if (!(test)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #test); exit(1); } } while (0)
#define YP001_CAT1_UART_BAUDRATE 460800U
#define APP_UART_ID_4 4
#define APP_DRV_SUCCESS 0
#define APP_UART_EVT_RX_DATA 1
#define APP_UART_EVT_ERROR 2
#define UART4_BUFFER_SIZE 512
typedef struct {int value;} uart_handle_t;
static struct { struct {uart_handle_t handle;} uart_dev; } s_uart4_param;
typedef struct {int type; union {uint16_t size; uint32_t error_code;} data;} app_uart_evt_t;
static uint8_t s_uart4_rx_buffer[513];
static char output[16384], sent[1024];
static unsigned out_n, sent_n, init_n;
static uint16_t tx_result, rx_result, deinit_result;
static uart_handle_t *owner;
static uint32_t __get_PRIMASK(void){return 0;}
static void __disable_irq(void){}
static void __set_PRIMASK(uint32_t v){(void)v;}
static void __DMB(void){}
static void uart_tx_data_send_force(uint8_t *p, uint16_t n){assert(out_n+n<sizeof(output));memcpy(output+out_n,p,n);out_n+=n;output[out_n]=0;}
static void cli_printf(const char *fmt,...){char b[1024];va_list ap;va_start(ap,fmt);int n=vsnprintf(b,sizeof(b),fmt,ap);va_end(ap);assert(n>=0&&n<(int)sizeof(b));uart_tx_data_send_force((uint8_t*)b,(uint16_t)n);}
static uart_handle_t *app_uart_get_handle(int id){(void)id;return owner;}
static uint16_t app_uart_deinit(int id){(void)id;if(!deinit_result)owner=NULL;return deinit_result;}
static uint16_t app_uart_transmit_sync(int id,uint8_t *p,uint16_t n,uint32_t timeout){(void)id;(void)timeout;assert(n<sizeof(sent));memcpy(sent,p,n);sent[n]=0;sent_n=n;return tx_result;}
static uint16_t app_uart_receive_async(int id,uint8_t *p,uint16_t n){(void)id;(void)p;(void)n;return rx_result;}
/* SAM | 2026-10-13 09:20 +08:00 | Stub business consumers because this test
 * verifies actual UART framing and dispatch, not the separately tested state machines. */
static unsigned business_lines, ota_lines, transport_losses;
static bool power_allowed=true;
bool yp001_ota_power_change_allowed(void){return power_allowed;}
bool yp001_ota_handle_line(const char *p,size_t n){if(n>=4&&!memcmp(p,"OTA_",4)){++ota_lines;return true;}return false;}
bool yp_business_handle_line(const char *p,size_t n){if(n>=8&&!memcmp(p,"BUS_EVT=",8)){++business_lines;return true;}return false;}
void yp_business_transport_lost(void){++transport_losses;}
'''
    body = r'''
static void push(const char *p){while(*p){s_cat_diag_rx[s_cat_diag_write]=(uint8_t)*p++;s_cat_diag_write=(s_cat_diag_write+1U)%sizeof(s_cat_diag_rx);}}
int main(void){
push("[ANT] v=1 type=LTE seq=1 csq=");cat_diag_poll();assert(out_n==0);
push("20\r\n");cat_diag_poll();assert(strcmp(output,"\r\n[CAT1 RX] [ANT] v=1 type=LTE seq=1 csq=20\r\n")==0);
'''
    functions = function(source, 'cat_diag_poll')
    if not opts.baseline:
        functions += '\nstatic void uart4_init(void){++init_n;s_uart4_ready=true;owner=&s_uart4_param.uart_dev.handle;}\n'
        functions += '\n'.join(function(source, n) for n in ['uart4_evt_handler', 'cmd_cat_at', 'cmd_cat_baud'])
        body += r'''
out_n=0;output[0]=0;
/* SAM | 2026-10-13 09:20 +08:00 | Follow the real bounded frame capacity after OTA enlarged it. */
for(unsigned i=0;i<sizeof(s_cat_line)+1U;++i){push("x");}cat_diag_poll();cat_diag_poll();cat_diag_poll();push("\nOK\r\n");cat_diag_poll();
assert(strstr(output,"binary_or_long_line_discarded"));assert(strstr(output,"[CAT1 RX] OK"));assert(!strstr(output,"[CAT1 RX] x"));
out_n=0;output[0]=0;push("partial");cat_diag_poll();s_cat_diag_overflow=true;push("corrupt");cat_diag_poll();push("tail\nGOOD\n");cat_diag_poll();
assert(strstr(output,"rx_lost"));assert(strstr(output,"[CAT1 RX] GOOD"));assert(!strstr(output,"[CAT1 RX] partial"));
assert(transport_losses==1);out_n=0;output[0]=0;
push("BUS_EVT={\"op\":\"hello\"}");cat_diag_poll();assert(business_lines==0);
push("\r\nOTA_TEST={}\n");cat_diag_poll();assert(business_lines==1&&ota_lines==1&&out_n==0);
char *args[]={"cat_at","AT+ANTSTART=ALL,2"};assert(cmd_cat_at(2,args)==0);assert(strcmp(sent,"AT+ANTSTART=ALL,2\r\n")==0);
char longarg[480];memset(longarg,'x',479);longarg[479]=0;char *large[]={"cat_at",longarg};sent_n=0;assert(cmd_cat_at(2,large)==-1);assert(sent_n==0);
longarg[478]=0;assert(cmd_cat_at(2,large)==0);assert(sent_n==480);
char *words[]={"cat_at","TTSPLAY","hello","world"};assert(cmd_cat_at(4,words)==0);assert(strcmp(sent,"TTSPLAY hello world\r\n")==0);
tx_result=9;assert(cmd_cat_at(2,args)==-1);assert(strstr(output,"[CAT1 TX] ok=0"));tx_result=0;
char *badbaud[]={"cat_baud","460800oops"};unsigned prev=init_n;assert(cmd_cat_baud(2,badbaud)==-1);assert(init_n==prev);
char *baud[]={"cat_baud","460800"};assert(cmd_cat_baud(2,baud)==0);assert(s_cat_uart_baud==460800);prev=init_n;assert(cmd_cat_baud(2,baud)==0);assert(init_n==prev);
power_allowed=false;sent_n=0;assert(cmd_cat_at(2,args)==-1);assert(sent_n==0);assert(cmd_cat_baud(2,baud)==-1);power_allowed=true;
uart_handle_t foreign;owner=&foreign;assert(cmd_cat_baud(2,baud)==-1);owner=&s_uart4_param.uart_dev.handle;
char *baudold[]={"cat_baud","115200"};deinit_result=7;assert(cmd_cat_baud(2,baudold)==-1);assert(s_cat_uart_baud==460800);deinit_result=0;
s_cat_diag_read=s_cat_diag_write=0;memset(s_uart4_rx_buffer,'y',512);app_uart_evt_t evt={APP_UART_EVT_RX_DATA,{.size=512}};
for(int i=0;i<9;++i){uart4_evt_handler(&evt);}assert(s_cat_diag_overflow);assert(s_cat_diag_dropped>0);cat_diag_poll();
rx_result=3;uart4_evt_handler(&evt);assert(!s_uart4_ready);assert(s_cat_uart_error);cat_diag_poll();assert(strstr(output,"driver=0x80000003"));
puts("PASS: actual C framing, overflow recovery, length bounds, TX error, baud and UART owner checks");
'''
    body += '\nreturn 0; }\n'
    folder = ROOT / 'logs/cat1_antenna_20261010'
    label = 'bridge-baseline' if opts.baseline else 'bridge-test'
    cfile = folder / (label + '.c')
    cfile.write_text(prefix + globals_c + functions + body, encoding='utf-8')
    exe = folder / (label + '.exe')
    env = dict(os.environ, PATH=str(GCC.parent) + os.pathsep + os.environ.get('PATH', ''))
    subprocess.run([str(GCC), '-std=c99', '-Wall', '-Wextra', '-Wno-unused-function',
                    '-Wno-unused-variable', '-I'+str(ROOT/'ble_app_uart_c/Src/user'), str(cfile), '-o', str(exe)], check=True, env=env)
    result = subprocess.run([str(exe)], capture_output=True, text=True, env=env)
    report = (result.stdout + result.stderr + '\nEXIT=' + str(result.returncode))
    (folder / (label + '.log')).write_text(report, encoding='utf-8')
    print(report)
    raise SystemExit(result.returncode != 0)

if __name__ == '__main__':
    main()
