"""SAM | 2026-10-25 +08:00 | Run production callbacks/recovery against SDK state and abort-order models before device deployment."""
from pathlib import Path
import hashlib, json, os, subprocess

root=Path(__file__).resolve().parents[2]
out=root/'logs/uart_completed_abort_fix_20261025';out.mkdir(exist_ok=True)
source=(root/'ble_app_uart_c/Src/platform/user_periph_setup.c').read_text(encoding='utf-8-sig')
def function(signature):
    start=source.index(signature+' {');opening=source.index('{',start);depth=1;end=opening+1
    while depth:
        depth += (source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]
handler=function('static void uart4_evt_handler(app_uart_evt_t *p_evt)')
service=function('static void cat_uart_recovery_poll(void)') if 'static void cat_uart_recovery_poll(void) {' in source else 'static void cat_uart_recovery_poll(void) {}'
prefix=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include "yp001_uart_fault.h"
/* SAM | 2026-10-25 +08:00 | Deterministic failing tests must not open a Windows crash dialog. */
#undef assert
#define assert(c) do {if(!(c)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#c);exit(1);}}while(0)
#define APP_UART_EVT_RX_DATA 1
#define APP_UART_EVT_ERROR 2
#define APP_UART_EVT_ABORT_RX 3
#define APP_UART_ID_4 4
#define APP_DRV_SUCCESS 0
#define UART4_BUFFER_SIZE 512
#define HAL_UART_STATE_READY 0x10
#define __DMB() ((void)0)
static uint32_t __get_PRIMASK(void){return 0;}
static void __disable_irq(void){}
static void __set_PRIMASK(uint32_t v){(void)v;}
typedef struct { int type; union { uint16_t size; uint32_t error_code; } data; } app_uart_evt_t;
typedef struct { uint32_t rx_state,error_code; } uart_handle_t;
static uart_handle_t handle;
static uart_handle_t *s_cat_uart_diag_handle=&handle;
static struct {uint32_t now_ms;} status;
#define yp_business_status() (&status)
static uint32_t yp001_uart_clock_ms(void){return status.now_ms;}
static volatile yp_uart_fault g_cat_uart_first_fault;
static volatile yp_uart_recovery g_cat_uart_recovery;
static uint32_t s_cat_uart_rx_bytes,s_cat_diag_dropped,s_cat_uart_error;
static uint16_t s_cat_diag_write,s_cat_diag_read;
static bool s_cat_diag_overflow,s_uart4_ready;
static uint8_t s_cat_diag_rx[4096],s_uart4_rx_buffer[513];
static unsigned receives,aborts;static bool synchronous_abort,flush_pending,rearm_failed;
static unsigned handshake_requests;
#define YP_PEER_UART_RX_LOST 3
static void yp_business_transport_lost_from(int source){assert(source==3);++handshake_requests;}
static void uart4_evt_handler(app_uart_evt_t *p_evt);
static uint16_t app_uart_receive_async(int id,uint8_t *buffer,unsigned size){
 (void)id;(void)buffer;(void)size;++receives;
 /* app_uart only sets its flush flag AFTER hal_abort returns. */
 if(g_cat_uart_recovery.phase) assert(flush_pending || !aborts);
 if(handle.rx_state!=0x10 || rearm_failed)return 2;
 flush_pending=false;handle.error_code=0;handle.rx_state=0x12;return 0;
}
static void abort_complete(void){app_uart_evt_t e={.type=APP_UART_EVT_ABORT_RX};handle.rx_state=0x10;uart4_evt_handler(&e);}
static uint16_t app_uart_abort_receive(int id){
 (void)id;++aborts;
 if(synchronous_abort)abort_complete();
 /* Exactly mirrors the app_uart wrapper's post-HAL flag ordering. */
 flush_pending=true;return 0;
}
static void reset(void){
 memset((void*)&g_cat_uart_first_fault,0,sizeof(g_cat_uart_first_fault));
 memset((void*)&g_cat_uart_recovery,0,sizeof(g_cat_uart_recovery));
 handle.rx_state=0x12;handle.error_code=0;status.now_ms=100;
 receives=aborts=handshake_requests=0;synchronous_abort=true;flush_pending=rearm_failed=false;
 s_uart4_ready=true;s_cat_uart_error=0;s_cat_diag_read=s_cat_diag_write=0;
}
'''
tests=r'''
int main(void){app_uart_evt_t e={.type=APP_UART_EVT_ERROR};
 reset();e.data.error_code=8;handle.error_code=8;uart4_evt_handler(&e);
 assert(receives==0 && !s_uart4_ready && g_cat_uart_first_fault.driver_error==8);
 assert(g_cat_uart_first_fault.rearm_result==UINT32_MAX);
 cat_uart_recovery_poll();assert(aborts==1 && receives==0);
 cat_uart_recovery_poll();assert(receives==1 && s_uart4_ready && g_cat_uart_recovery.phase==0);
 assert(handshake_requests==1);
 cat_uart_recovery_poll();assert(receives==1 && aborts==1);
 puts("PASS FE: no IRQ rearm; synchronous completion waits for wrapper return; one foreground rearm");
 reset();handle.rx_state=0x10;handle.error_code=2;e.data.error_code=2;uart4_evt_handler(&e);
 cat_uart_recovery_poll();cat_uart_recovery_poll();assert(receives==1 && s_uart4_ready);
 puts("PASS OE: aborted receiver follows the same bounded lifecycle");
 reset();handle.rx_state=0x10;handle.error_code=8;e.type=APP_UART_EVT_RX_DATA;e.data.size=1;
 s_uart4_rx_buffer[0]='X';uart4_evt_handler(&e);
 assert(receives==0 && s_cat_diag_write==0 && g_cat_uart_first_fault.driver_error==8);
 e.type=APP_UART_EVT_ERROR;e.data.error_code=0;uart4_evt_handler(&e);
 assert(g_cat_uart_first_fault.driver_error==8);
 cat_uart_recovery_poll();cat_uart_recovery_poll();assert(receives==1);
 puts("PASS IRQ ORDER: RX completion snapshots raw error before rearm and quarantines data; later error cannot overwrite");
 reset();synchronous_abort=false;e.type=APP_UART_EVT_ERROR;e.data.error_code=8;uart4_evt_handler(&e);
 cat_uart_recovery_poll();cat_uart_recovery_poll();assert(aborts==1 && receives==0);
 e.type=APP_UART_EVT_RX_DATA;e.data.size=1;uart4_evt_handler(&e);assert(s_cat_diag_write==0);
 abort_complete();cat_uart_recovery_poll();assert(receives==1 && s_uart4_ready);
 puts("PASS ASYNC: no rearm before completion; callbacks during recovery cannot publish bytes");
 /* SAM | 2026-10-25 +08:00 | Seventh exposed the omitted case: scheduling
  * before abort, or after its timely completion, must not become an abort timeout. */
 reset();e.type=APP_UART_EVT_ERROR;e.data.error_code=2;handle.rx_state=0x10;uart4_evt_handler(&e);
 status.now_ms+=300;cat_uart_recovery_poll();cat_uart_recovery_poll();
 assert(s_uart4_ready && receives==1 && g_cat_uart_recovery.phase==0);
 puts("PASS DELAY BEFORE ABORT: deadline starts at actual abort call");
 reset();e.type=APP_UART_EVT_ERROR;e.data.error_code=2;handle.rx_state=0x10;uart4_evt_handler(&e);
 cat_uart_recovery_poll();status.now_ms+=300;cat_uart_recovery_poll();
 assert(s_uart4_ready && receives==1 && g_cat_uart_recovery.phase==0);
 puts("PASS LATE CONSUMER: timely synchronous completion remains valid after 300ms foreground delay");
 reset();synchronous_abort=false;e.type=APP_UART_EVT_ERROR;e.data.error_code=2;uart4_evt_handler(&e);
 cat_uart_recovery_poll();status.now_ms+=101;abort_complete();cat_uart_recovery_poll();
 assert(!s_uart4_ready && receives==0 && g_cat_uart_recovery.phase==3);
 puts("PASS ACTUALLY LATE COMPLETION: completion after deadline still fails closed");
 reset();synchronous_abort=false;status.now_ms=0xfffffff0u;e.type=APP_UART_EVT_ERROR;e.data.error_code=2;uart4_evt_handler(&e);
 cat_uart_recovery_poll();status.now_ms=40;abort_complete();status.now_ms=500;cat_uart_recovery_poll();
 assert(s_uart4_ready && receives==1);
 puts("PASS CLOCK WRAP: completion age uses uint32 modular difference");
 reset();synchronous_abort=false;e.type=APP_UART_EVT_ERROR;e.data.error_code=8;uart4_evt_handler(&e);
 cat_uart_recovery_poll();status.now_ms+=101;cat_uart_recovery_poll();
 assert(g_cat_uart_recovery.phase==3 && !s_uart4_ready && receives==0);
 abort_complete();cat_uart_recovery_poll();assert(receives==0);
 puts("PASS TIMEOUT: late completion cannot restart a failed recovery");
 reset();e.type=APP_UART_EVT_ERROR;e.data.error_code=8;uart4_evt_handler(&e);
 cat_uart_recovery_poll();rearm_failed=true;cat_uart_recovery_poll();cat_uart_recovery_poll();
 assert(g_cat_uart_recovery.phase==3 && receives==1 && !s_uart4_ready);
 puts("PASS BUSY: failed rearm remains blocked without init/retry loop");
 reset();handle.rx_state=0x10;e.type=APP_UART_EVT_RX_DATA;e.data.size=1;uart4_evt_handler(&e);
 assert(receives==1 && s_cat_diag_write==1 && !g_cat_uart_first_fault.valid);
 puts("PASS NORMAL: ordinary RX completion retains its existing path");return 0;}
'''
c=out/'recovery_contract.c';c.write_text(prefix+handler+'\n'+service+tests)
gcc=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
subprocess.run([str(gcc),'-std=c99','-Wall','-Wextra','-Werror','-Wno-unused-function',
 '-I'+str(root/'ble_app_uart_c/Src/platform'),str(c),'-o',str(out/'recovery_contract.exe')],check=True,env=env)
p=subprocess.run([str(out/'recovery_contract.exe')],capture_output=True,text=True,env=env)
(out/('recovery_green.log' if p.returncode==0 else 'recovery_red.log')).write_text(p.stdout+p.stderr)
(out/'recovery_result.json').write_text(json.dumps(dict(passed=p.returncode==0,hal_is_model=True,
 handler_sha256=hashlib.sha256(handler.encode()).hexdigest(),device_written=False),indent=2))
print(p.stdout+p.stderr);raise SystemExit(p.returncode)
