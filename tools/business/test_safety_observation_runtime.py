"""SAM | 2026-10-25 +08:00 | Execute actual BSP observation code with delayed/failed IO and screen off."""
from pathlib import Path
import os,subprocess
r=Path(__file__).resolve().parents[2]
s=(r/'ble_app_uart_c/Src/platform/bsp.c').read_text(encoding='utf-8-sig')
helper=s[s.index('static epaper_home_status_t home ='):s.index('static void battery_display_poll(void)')]
code=r'''#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#define BSP_TICKS_PER_SEC 100
#define YP001_BATTERY_OK 0
#define YP001_BATTERY_ADC_RANGE 1
typedef int yp001_battery_result_t;
typedef struct {bool ble_known,xyz_checked,xyz_known,battery_known,voltage_known; int32_t xyz_mg[3]; uint8_t battery_percent;uint16_t battery_mv;const char *power_text;} epaper_home_status_t;
typedef struct {unsigned fault,power_raw,charge_state;bool input_present,power_good,thermal_limit;} yp001_charger_status_t;
static uint32_t s_battery_ui_ticks,clock_ms,motion_reads,battery_reads,motion_ms,battery_ms;
static bool s_business_ready=true,s_sleep_test,locked,motion_ok=true,adc_ok=true,charger_ok=true,seen_motion,seen_battery;
void yp001_safety_observation_poll(void);
static bool yp001_charger_ship_locked(void){return locked;}
static bool gsensor_read_mg(int32_t*v){motion_reads++;yp001_safety_observation_poll();s_battery_ui_ticks+=10;v[2]=1000;return motion_ok;}
static void yp_business_acceleration(bool k,const int32_t*v,uint32_t ms){(void)v;seen_motion=k;motion_ms=ms;}
static void yp_business_observation_clock(uint32_t ms){clock_ms=ms;}
static int yp001_battery_read(uint16_t*v){battery_reads++;yp001_safety_observation_poll();s_battery_ui_ticks+=2;*v=4100;return adc_ok?0:1;}
static void yp001_charger_poll(void){}
static bool yp001_charger_display_status(yp001_charger_status_t*c){*c=(yp001_charger_status_t){0,0x10,1,true,true,false};return charger_ok;}
static uint8_t yp001_battery_estimate(uint16_t v){(void)v;return 90;}
static bool yp001_charger_is_complete(void){return false;}
static bool yp001_ota_usb_supply(bool a,bool b,bool c,unsigned d,unsigned e){(void)c;(void)d;(void)e;return a&&b;}
static void yp_business_battery(bool k,uint8_t p,bool c){(void)p;(void)c;seen_battery=k;battery_ms=clock_ms;}
'''+helper+r'''
int main(void){
 yp001_safety_observation_poll();assert(motion_reads==1&&motion_ms==100&&battery_reads==0);
 s_battery_ui_ticks=59;yp001_safety_observation_poll();assert(motion_reads==1);
 s_battery_ui_ticks=60;yp001_safety_observation_poll();assert(motion_reads==2);
 s_battery_ui_ticks=250;yp001_safety_observation_poll();assert(battery_reads==1&&seen_battery&&battery_ms==2620&&clock_ms==2620);
 s_battery_ui_ticks=361;yp001_safety_observation_poll();assert(battery_reads==2); /* motion read advances real clock across due time */
 adc_ok=false;motion_ok=false;s_battery_ui_ticks=500;yp001_safety_observation_poll();assert(!seen_motion&&!seen_battery);
 adc_ok=true;charger_ok=false;s_battery_ui_ticks=650;yp001_safety_observation_poll();assert(!seen_battery);
 unsigned reads=motion_reads+battery_reads;locked=true;s_battery_ui_ticks=900;yp001_safety_observation_poll();assert(reads==motion_reads+battery_reads);
 locked=false;s_sleep_test=true;yp001_safety_observation_poll();assert(reads==motion_reads+battery_reads);
 s_sleep_test=false;s_business_ready=false;yp001_safety_observation_poll();assert(reads==motion_reads+battery_reads);
 s_business_ready=true;motion_ok=true;charger_ok=true;s_battery_ui_ticks=0xfffffff0u;yp001_safety_observation_poll();
 unsigned wrap_reads=motion_reads;s_battery_ui_ticks=10;yp001_safety_observation_poll();assert(motion_reads==wrap_reads);
 s_battery_ui_ticks=60;yp001_safety_observation_poll();assert(motion_reads==wrap_reads+1);
 return 0;
}
'''
o=r/'logs/ota_system_review_20261025';src=o/'test_safety_actual.c';src.write_text(code)
gcc=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe');env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
subprocess.run([str(gcc),'-std=c99','-Wall','-Wextra','-Werror',str(src),'-o',str(src.with_suffix('.exe'))],env=env,check=True)
subprocess.run([str(src.with_suffix('.exe'))],env=env,check=True)
print('PASS actual BSP: timed sensor/ADC, reentrancy, failure unknown, screen independent, ship/sleep/startup suppression')
