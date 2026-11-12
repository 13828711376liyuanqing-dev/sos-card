"""SAM | 2026-11-05 +08:00 | Execute the actual scan cache callback with fake IRQ mask and log sink; no board access."""
from pathlib import Path
import os
import subprocess

ROOT=Path(__file__).resolve().parents[2]
source=(ROOT/'ble_app_uart_c/Src/user/yp001_scan_sched.c').read_text(encoding='utf8')
start=source.index('void yp_scan_sched_on_adv_report(');end=source.index('{',start)+1;depth=1
while depth:
    depth+=(source[end]=='{')-(source[end]=='}');end+=1
callback=source[start:end]
unit=r'''
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#define MAX_BEACON_PER_SCAN 5
typedef struct { uint16_t major,minor; } tk_beacon_data_t;
typedef struct { uint8_t addr[6]; int8_t rssi; uint16_t major,minor; } Item;
typedef struct { uint8_t count; uint32_t timestamp; Item list[MAX_BEACON_PER_SCAN]; } BeaconScanResult;
static bool s_enabled=true,s_scanning=true;
static BeaconScanResult s_cur;
static uint32_t mask=1;static unsigned print_calls;
static uint32_t __get_PRIMASK(void){return mask;}
static void __disable_irq(void){mask=1;}
static void __enable_irq(void){mask=0;}
static void __set_PRIMASK(uint32_t value){mask=value;}
static int fake_printf(const char *fmt,...){(void)fmt;print_calls++;return 0;}
#define printf fake_printf
static bool tk_beacon_process(const void *p,uint8_t addr[6],int8_t *rssi,tk_beacon_data_t *data){memcpy(addr,p,6);*rssi=-50;data->major=7;data->minor=8;return true;}
'''+callback+r'''
#undef printf
int main(void){
 uint8_t address[6]={1,2,3,4,5,6};int failures=0;
 yp_scan_sched_on_adv_report(address);
 if(mask!=1){puts("FAIL preserve_already_masked_interrupt_state");failures++;}else puts("PASS preserve_already_masked_interrupt_state");
 if(print_calls){puts("FAIL no_log_inside_scan_callback_critical_section");failures++;}else puts("PASS no_log_inside_scan_callback_critical_section");
 mask=0;yp_scan_sched_on_adv_report(address);
 if(mask!=0||s_cur.count!=1||s_cur.list[0].major!=7){puts("FAIL unmasked_state_and_beacon_update");failures++;}else puts("PASS unmasked_state_and_beacon_update");
 return failures?1:0;
}
'''
out=ROOT/'logs/ble_scan_cache_repro';out.mkdir(exist_ok=True)
(out/'callback.c').write_text(unit,encoding='utf8')
gcc=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe');env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
subprocess.run([str(gcc),'-std=c11',str(out/'callback.c'),'-o',str(out/'callback.exe')],env=env,check=True)
result=subprocess.run([str(out/'callback.exe')],env=env,text=True,capture_output=True)
(out/'result.txt').write_text(result.stdout+f'EXIT={result.returncode}\n',encoding='utf8')
print(result.stdout,end='');raise SystemExit(result.returncode)
