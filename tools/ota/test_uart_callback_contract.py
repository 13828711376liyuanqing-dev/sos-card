"""SAM | 2026-10-25 +08:00 | Execute actual UART callback against SDK-documented error-state scenarios; no device writes."""
from pathlib import Path
import subprocess,os,hashlib,json
r=Path(__file__).resolve().parents[2];out=r/'logs/uart_first_fault_20261025';src=(r/'ble_app_uart_c/Src/platform/user_periph_setup.c').read_text(encoding='utf-8-sig')
a=src.index('static void uart4_evt_handler(app_uart_evt_t *p_evt) {');b=src.index('\n/* SAM',a);handler=src[a:b]
prefix=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <assert.h>
#include <string.h>
#include "yp001_uart_fault.h"
#define APP_UART_EVT_RX_DATA 1
#define APP_UART_EVT_ERROR 2
#define APP_UART_ID_4 4
#define APP_DRV_SUCCESS 0
#define UART4_BUFFER_SIZE 512
#define __DMB() ((void)0)
typedef struct { int type; union { uint16_t size; uint32_t error_code; } data; } app_uart_evt_t;
typedef struct { uint32_t rx_state, error_code; } uart_handle_t;
static uart_handle_t handle;
static uart_handle_t *s_cat_uart_diag_handle=&handle;
static struct { uint32_t now_ms; } status;
#define yp_business_status() (&status)
static volatile yp_uart_fault g_cat_uart_first_fault;
static uint32_t s_cat_uart_rx_bytes,s_cat_diag_dropped,s_cat_uart_error;
static uint16_t s_cat_diag_write,s_cat_diag_read;
static bool s_cat_diag_overflow,s_uart4_ready;
static uint8_t s_cat_diag_rx[4096],s_uart4_rx_buffer[513];
static unsigned calls;
static uint16_t app_uart_receive_async(int id,uint8_t *buffer,unsigned size){
 (void)id;(void)buffer;(void)size;++calls;
 /* SAM | 2026-10-25 +08:00 | Match deployed AXF: READY is 0x10;
  * all other RX states return BUSY, and successful rearm clears HAL error. */
 if(handle.rx_state!=0x10) return 2;
 handle.error_code=0;handle.rx_state=0x12;return 0;
}
'''
suffix=r'''
int main(void){
 app_uart_evt_t evt={.type=APP_UART_EVT_ERROR};
 /* Recoverable frame error keeps receive active per SDK header. */
 handle.rx_state=0x12;s_uart4_ready=true;evt.data.error_code=8;status.now_ms=100;
 uart4_evt_handler(&evt);
 assert(calls==1 && !s_uart4_ready && s_cat_uart_error==0x80000002u);
 assert(g_cat_uart_first_fault.driver_error==8 && g_cat_uart_first_fault.rearm_result==2);
 puts("REPRODUCED: continuing RX -> redundant rearm -> BUSY -> ready=false");
 memset((void*)&g_cat_uart_first_fault,0,sizeof(g_cat_uart_first_fault));
 handle.rx_state=0x10;s_uart4_ready=true;evt.data.error_code=2;calls=0;
 uart4_evt_handler(&evt);
 assert(calls==1 && s_uart4_ready && g_cat_uart_first_fault.rearm_result==0);
 puts("CONTROL: aborted RX -> rearm succeeds; original error preserved");
 /* Model the conditional RX-complete-before-error ordering visible at
  * the HAL IRQ call site; ROM completion internals remain outside this test. */
 memset((void*)&g_cat_uart_first_fault,0,sizeof(g_cat_uart_first_fault));
 handle.rx_state=0x10;handle.error_code=8;s_uart4_ready=true;calls=0;
 evt.type=APP_UART_EVT_RX_DATA;evt.data.size=1;s_uart4_rx_buffer[0]='X';
 uart4_evt_handler(&evt);
 assert(s_cat_diag_write==1 && s_cat_diag_rx[0]=='X' && handle.error_code==0);
 evt.type=APP_UART_EVT_ERROR;evt.data.error_code=handle.error_code;
 uart4_evt_handler(&evt);
 assert(calls==2 && !s_uart4_ready);
 assert(g_cat_uart_first_fault.valid==YP_UART_FAULT_VALID);
 assert(g_cat_uart_first_fault.source==1 && g_cat_uart_first_fault.driver_error==0);
 puts("ORDERING MODEL: RX completion rearm clears error before later error event; captured error=0/BUSY");
 /* READY=0x20 in the earlier control was inaccurate; now reject it. */
 handle.rx_state=0x20;assert(app_uart_receive_async(4,s_uart4_rx_buffer,512)==2);
 puts("BOUNDARY: invalid RX state 0x20 is BUSY, not READY");
 return 0;
}
'''
(out/'callback_contract.c').write_text(prefix+handler+suffix)
gcc=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe');env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
subprocess.run([str(gcc),'-std=c99','-Wall','-Wextra','-Werror','-I'+str(r/'ble_app_uart_c/Src/platform'),str(out/'callback_contract.c'),'-o',str(out/'callback_contract.exe')],check=True,env=env)
p=subprocess.run([str(out/'callback_contract.exe')],check=True,capture_output=True,text=True,env=env)
(out/'callback_contract.log').write_text(p.stdout)
(out/'callback_contract.json').write_text(json.dumps({'handler_sha256':hashlib.sha256(handler.encode()).hexdigest(),'test_passed':True,'hal_is_model':True,'sixth_root_cause_proven':False,'device_written':False},indent=2));print(p.stdout)
