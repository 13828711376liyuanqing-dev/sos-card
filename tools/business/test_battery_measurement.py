"""SAM | 2026-11-07 +08:00 | Execute the production battery callback with TEST_DATA enabled; never access hardware."""
from pathlib import Path
import os
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    source = (ROOT / 'ble_app_uart_c/Src/user/business/yp001_business.c').read_text(encoding='utf-8-sig')
    start = source.index('void yp_business_battery(')
    end = source.index('\n}\n', start) + 3
    callback = source[start:end]
    first = source.index('static bool ota_fresh(')
    last = source.index('/* SAM | 2026-10-25 +08:00 | Preserve the specific invalidation source', first)
    observations = source[first:last]
    code = r'''
#include <stdio.h>
#define assert(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); return 1; } } while(0)
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#define TEST_DATA 1
static struct {
 uint32_t now_ms,revision;
 bool battery_known,charging,imei_known,time_known,show_time,resident_known,searching,sleeping;
 uint8_t battery_percent;
 char imei[32],date[32],clock[32],weekday[32],name[64],room[64],campus[96];
} s;
static bool s_inited=true,ota_battery_seen,battery_pending;
static uint32_t ota_battery_ms;
static void changed(void){++s.revision;}
''' + callback + r'''
#define YP001_OTA_USB_BENCH_TEST 0
typedef struct {bool known,stable,activity;} yp_business_ota_inputs_t;
static bool ota_keys_seen,ota_motion_seen,ota_key_down,ota_moving;
static uint32_t ota_keys_ms,ota_motion_ms,ota_quiet_ms;
static uint32_t key_requests,consumed_keys,call_request,consumed_call;
''' + observations + r'''
int main(void){
 s.now_ms=1234;
 yp_business_battery(true,29,true);
 assert(s.battery_known && s.battery_percent==29 && s.charging);
 assert(ota_battery_seen && ota_battery_ms==1234 && battery_pending);
 assert(s.resident_known); /* retain unrelated bench display behavior */
 strcpy(s.name,"resident sentinel");
 for(unsigned i=0;i<4;++i){
  static const uint8_t values[]={0,69,70,100};
  yp_business_battery(true,values[i],false);
  assert(s.battery_known && s.battery_percent==values[i] && !s.charging);
  assert(!strcmp(s.name,"resident sentinel"));
 }
 yp_business_battery(false,80,true);
 assert(!s.battery_known && s.battery_percent==0 && s.charging);
 yp_business_battery(true,101,false);
 assert(!s.battery_known && s.battery_percent==0 && !s.charging);
 s.now_ms=4321;yp_business_battery(true,70,true);
 assert(s.battery_percent==70 && ota_battery_ms==4321);
 battery_pending=false;uint32_t revision=s.revision;
 yp_business_battery(true,70,true);
 assert(!battery_pending && s.revision==revision);
 /* SAM | 2026-11-07 07:14 +08:00 | USB replaces only battery validity, never stale keys/motion/battery observation or activity. */
 yp_business_ota_inputs_t g;
 s.now_ms=60000;ota_battery_ms=ota_keys_ms=ota_motion_ms=60000;
 ota_battery_seen=ota_keys_seen=ota_motion_seen=true;ota_quiet_ms=0;
 s.battery_known=false;
 yp_business_ota_inputs(&g);assert(!g.known && !g.stable);
 yp_business_ota_inputs_with_usb(&g,true);assert(g.known && g.stable && !g.activity);
 ota_battery_ms=56999;yp_business_ota_inputs_with_usb(&g,true);assert(!g.known);
 ota_battery_ms=60000;ota_keys_ms=59899;yp_business_ota_inputs_with_usb(&g,true);assert(!g.known);
 ota_keys_ms=60000;ota_motion_ms=58499;yp_business_ota_inputs_with_usb(&g,true);assert(!g.known);
 ota_motion_ms=60000;ota_key_down=true;yp_business_ota_inputs_with_usb(&g,true);assert(g.activity && !g.stable);
 ota_key_down=false;s.sleeping=true;yp_business_ota_inputs_with_usb(&g,true);assert(g.activity && !g.stable);
 return 0;
}
'''
    out = ROOT / 'logs/ota_battery_gate_20261107'
    out.mkdir(parents=True, exist_ok=True)
    cfile = out / 'battery_actual.c'
    cfile.write_text(code, encoding='utf-8')
    gcc = Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
    env = dict(os.environ, PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
    commands = ([str(gcc), '-std=c99', '-Wall', '-Wextra', '-Werror', str(cfile), '-o', str(out/'battery_checks.exe')],
                [str(out/'battery_checks.exe')])
    for cmd in commands:
        subprocess.run(cmd, env=env, check=True, timeout=30)
    print('PASS actual TEST_DATA battery callback: measured percent/unknown preserved, charge unchanged, resident retained')


if __name__ == '__main__':
    main()
