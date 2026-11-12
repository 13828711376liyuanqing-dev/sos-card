"""SAM | 2026-11-05 +08:00 | Reproduce qv_port:110 at the actual callback boundary and validate copied, bounded foreground delivery."""
from pathlib import Path
import os
import subprocess

ROOT=Path(__file__).resolve().parents[2]
app=(ROOT/'ble_app_uart_c/Src/user/app.h').read_text(encoding='utf8',errors='replace')
user=(ROOT/'ble_app_uart_c/Src/user/user_app.c').read_text(encoding='utf8')

def function(source,signature):
    start=source.index(signature);end=source.index('{',start)+1;depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]

helpers=function(app,'static inline BeaconDataEvt * BeaconDataEvt_init(')+'\n'+function(app,'static inline void BeaconDataEvt_send(')
if '/* YP_BEACON_DEFER_BEGIN */' in user:
    implementation=user.split('/* YP_BEACON_DEFER_BEGIN */')[1].split('/* YP_BEACON_DEFER_END */')[0]
else:
    implementation='static void beacon_report_defer(const ble_gap_evt_adv_report_t *p){BeaconDataEvt_send(p);}\nvoid yp_beacon_deferred_poll(void){}'
unit=r'''
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
typedef struct {int dummy;} QEvt;
typedef struct {uint16_t major,minor;} tk_beacon_data_t;
typedef struct {QEvt super;uint8_t addr[6];int8_t rssi;tk_beacon_data_t data;} BeaconDataEvt;
typedef struct {uint8_t prio;} QActive;
typedef struct {uint16_t length;uint8_t *data;int8_t rssi;} ble_gap_evt_adv_report_t;
static QActive actor={1};static QActive *app_state_machine=&actor;
static bool g_beacon_process_enable=true;
static uint32_t basepri=0x41,ipsr=17,primask;
static unsigned unsafe_calls,delivered,cached;
static BeaconDataEvt event,saved[64];
static uint32_t __get_BASEPRI(void){return basepri;}
static uint32_t __get_IPSR(void){return ipsr;}
static uint32_t __get_PRIMASK(void){return primask;}
#define __DMB() ((void)0)
static void *alloc(void){if(basepri||ipsr||primask)unsafe_calls++;return &event;}
static bool post(BeaconDataEvt *p){if(basepri||ipsr||primask)unsafe_calls++;if(delivered<64)saved[delivered]=*p;delivered++;return true;}
#define Q_NEW_X(type,margin,sig) ((type*)alloc())
#define QACTIVE_POST_X(a,e,margin,sender) post((BeaconDataEvt*)(e))
static bool tk_beacon_process(const void *raw,uint8_t addr[6],int8_t *rssi,tk_beacon_data_t *data){const ble_gap_evt_adv_report_t *p=raw;if(!p||!p->data||p->length<9||p->data[0]!=0xaa)return false;memcpy(addr,p->data+1,6);*rssi=p->rssi;data->major=p->data[7];data->minor=p->data[8];return true;}
static void yp_scan_sched_on_adv_report(const void *raw){(void)raw;if(basepri||ipsr||primask)unsafe_calls++;cached++;}
'''+helpers+'\n'+implementation+r'''
static unsigned failures;
#define CHECK(ok,name) do {bool pass=(ok);printf("%s %s\n",pass?"PASS":"FAIL",name);failures+=!pass;}while(0)
int main(void){
 uint8_t bytes[31]={0xaa,1,2,3,4,5,6,7,8};ble_gap_evt_adv_report_t report={31,bytes,-42};
 beacon_report_defer(&report);
 CHECK(!unsafe_calls&&!delivered,"logging_lock_BASEPRI_41_BLE_IRQ_must_not_call_QP");
 basepri=0x3f;bytes[1]=99;yp_beacon_deferred_poll();
 CHECK(!unsafe_calls&&!delivered,"poll_rejects_masked_or_IRQ_context");
 basepri=0;ipsr=0;yp_beacon_deferred_poll();
 CHECK(!unsafe_calls&&delivered==1&&saved[0].addr[0]==1&&saved[0].rssi==-42,"foreground_delivers_deep_copy_after_SDK_buffer_reuse");
 unsigned before=delivered;
 for(unsigned i=0;i<20;i++)beacon_report_defer(&report);
 yp_beacon_deferred_poll();
 CHECK(delivered-before<=4,"foreground_batch_is_bounded");
 for(unsigned i=0;i<8;i++)yp_beacon_deferred_poll();
 CHECK(delivered-before<=7&&!unsafe_calls,"queue_overflow_is_bounded_without_QP_assertion");
 beacon_report_defer(&report);before=delivered;g_beacon_process_enable=false;yp_beacon_deferred_poll();g_beacon_process_enable=true;yp_beacon_deferred_poll();
 CHECK(delivered==before,"disabled_processing_discards_pending_samples");
 report.length=32;beacon_report_defer(&report);report.length=31;report.data=NULL;beacon_report_defer(&report);yp_beacon_deferred_poll();
 CHECK(delivered==before,"oversize_and_null_payload_are_rejected");
 CHECK(cached==delivered,"both_QP_and_scan_cache_run_in_foreground");
 return failures?1:0;
}
'''
out=ROOT/'logs/beacon_deferred_tests';out.mkdir(exist_ok=True)
(out/'actual_callback.c').write_text(unit,encoding='utf8')
gcc=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe');env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
subprocess.run([str(gcc),'-std=c11','-Wall',str(out/'actual_callback.c'),'-o',str(out/'test.exe')],env=env,check=True)
r=subprocess.run([str(out/'test.exe')],env=env,text=True,capture_output=True)
(out/'result.txt').write_text(r.stdout+f'EXIT={r.returncode}\n',encoding='utf8');print(r.stdout,end='');raise SystemExit(r.returncode)
