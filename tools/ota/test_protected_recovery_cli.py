"""SAM | 2026-10-27 +08:00 | Execute actual protected CLI functions with explicit GPIO/UART models, no hardware access."""
from pathlib import Path
import os,subprocess
from replay_commit_observation_age import function,ROOT
o=ROOT/'logs/r6_install_stages_20261027/control_entry';o.mkdir(exist_ok=True)
p=ROOT/'ble_app_uart_c/Src/platform/user_periph_setup.c'
policy=ROOT/'ble_app_uart_c/Src/user/ota/yp001_ota_recovery_control.h'
src=r'''
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <stdlib.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static bool standard,recovery=true,s_uart4_ready=true,s_cat1_isolated,s_cat_line_discard;
static unsigned tx_calls,io_inits,io_writes,delays;static int level;
static uint32_t s_cat_diag_dropped,s_cat_diag_read,s_cat_diag_write,s_cat_line_used;
static int s_cat_mux;
typedef struct {int unused;} uart_handle_t;
static struct {struct {uart_handle_t handle;} uart_dev;} s_uart4_param;
typedef struct {int pull,mode;uint32_t pin;int mux;} app_io_init_t;
#define APP_IO_DEFAULT_CONFIG {0}
#define APP_IO_NOPULL 0
#define APP_IO_MODE_INPUT 0
#define APP_IO_MODE_OUTPUT 1
#define APP_DRV_SUCCESS 0
#define APP_UART_ID_4 4
#define YP001_CAT1_UART_TX_PIN 2
#define YP001_CAT1_UART_RX_PIN 4
#define YP001_CAT1_UART_TYPE 0
#define YP001_AON_GPIO_MUX 0
#define YP_PEER_POWER_OFF 1
#define YP001_CAT1_KEY_PIN 1
#define YP001_CAT1_POWER_PIN 64
#define YP001_GPIO_GPIO_MUX 0
#define YP001_CAT1_KEY_TYPE 0
#define YP001_CAT1_POWER_TYPE 0
#define YP001_CAT1_KEY_ASSERT 1
#define YP001_CAT1_KEY_RELEASE 0
#define YP001_CAT1_POWER_ON 1
#define YP001_CAT1_POWER_OFF 0
bool yp001_ota_power_change_allowed(void){return standard;}
bool yp001_ota_recovery_control_allowed(void){return recovery;}
static void cli_printf(const char*f,...){(void)f;}
static void uart4_init(void){s_uart4_ready=true;}
static uint16_t app_uart_transmit_sync(int id,uint8_t*p,uint16_t n,unsigned timeout){CHECK(id==4&&n>=2&&p[n-2]=='\r'&&p[n-1]=='\n'&&timeout==1000);tx_calls++;return 0;}
static uart_handle_t *app_uart_get_handle(int id){(void)id;return NULL;}
static uint16_t app_uart_abort_receive(int id){(void)id;return 0;}
static uint16_t app_uart_deinit(int id){(void)id;return 0;}
static uint16_t app_io_init(int type,app_io_init_t*p){(void)type;(void)p;io_inits++;level=0;return 0;}
static uint16_t app_io_write_pin(int type,uint32_t pin,int value){(void)type;(void)pin;io_writes++;level=value;return 0;}
static int app_io_read_pin(int type,uint32_t pin){(void)type;(void)pin;return level;}
static void delay_ms(unsigned ms){(void)ms;delays++;}
static void yp001_ota_mux_lost(int*p){(void)p;}
static void yp_business_transport_lost_from(int source){(void)source;}
'''
if policy.exists():src+='#include "yp001_ota_recovery_control.h"\n'
else:src=src.replace('static int app_io_read_pin','int app_io_read_pin')
src+=function(p,'cmd_cat_at')+'\n'+function(p,'cat1_debug_power')
src+=r'''
int main(void){
 char *status[]={"cat_at","FOTA_STATUS"};
 CHECK(cmd_cat_at(2,status)==0&&tx_calls==1);
 const char *allow[]={"OTA_HANDOFF_RESUME=782fc7f0bca7b0ef37f67a4e633604e4","OTA_HANDOFF_RESUME=782fc7f0bca7b0ef37f67a4e633604e4,4","OTA_HANDOFF_RESUME=782fc7f0bca7b0ef37f67a4e633604e4,5"};
 for(unsigned k=0;k<3;k++){char *v[]={"cat_at",(char*)allow[k]};CHECK(cmd_cat_at(2,v)==0);}
 const char *deny[]={"AT+CFUN=1","ATREBOOT","FOTA_STATUS;ATREBOOT","OTA_HANDOFF_RESUME=00000000000000000000000000000000,5","OTA_HANDOFF_RESUME=782fc7f0bca7b0ef37f67a4e633604e4,0","OTA_HANDOFF_RESUME=782fc7f0bca7b0ef37f67a4e633604e4,10"};
 unsigned before=tx_calls;
 for(unsigned k=0;k<6;k++){char *v[]={"cat_at",(char*)deny[k]};CHECK(cmd_cat_at(2,v)<0&&tx_calls==before);}
 char *extra[]={"cat_at","FOTA_STATUS","ATREBOOT"};CHECK(cmd_cat_at(3,extra)<0&&tx_calls==before);
 recovery=false;CHECK(cmd_cat_at(2,status)<0&&tx_calls==before);recovery=true;
 char *on[]={"cat1_power","on"};CHECK(cat1_debug_power(2,on)==0&&level==1&&io_inits==1&&io_writes==1);
 CHECK(cat1_debug_power(2,on)==0&&io_inits==1&&io_writes==1);
 const char *unsafe[]={"off","key","isolate"};
 for(unsigned k=0;k<3;k++){char *v[]={"cat1_power",(char*)unsafe[k]};CHECK(cat1_debug_power(2,v)<0&&io_inits==1&&io_writes==1&&delays==0);}
 recovery=false;CHECK(cat1_debug_power(2,on)<0&&io_inits==1);standard=true;
 char *ordinary[]={"cat_at","AT"};CHECK(cmd_cat_at(2,ordinary)==0);
 puts("PASS actual protected CLI: exact status/R6 transport, wrong commands denied, on idempotent without GPIO glitch, off/key/isolate still blocked; no quota or install changes");return 0;
}
'''
(o/'cli_checks.c').write_text(src,encoding='utf-8')
g=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe');env=dict(os.environ,PATH=str(g.parent)+os.pathsep+os.environ.get('PATH',''));log=[]
for command in ([str(g),'-std=c99','-Wall','-Wextra','-Werror','-I'+str(policy.parent),str(o/'cli_checks.c'),'-o',str(o/'cli_checks.exe')],[str(o/'cli_checks.exe')]):
 q=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60);log.append(q.stdout+q.stderr+f'\nexit={q.returncode}\n');(o/'result.log').write_text(''.join(log),encoding='utf-8');print(log[-1],end='')
 if q.returncode:raise SystemExit(q.returncode)
