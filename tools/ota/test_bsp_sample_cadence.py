"""SAM | 2026-10-24 +08:00 | Execute the real BSP poll with blocking partial-frame stubs to detect stale OTA samples."""
from pathlib import Path
import os,subprocess

root=Path(__file__).resolve().parents[2]
text=(root/'ble_app_uart_c/Src/platform/bsp.c').read_text(encoding='utf-8-sig')
function=text.split('static void battery_display_poll(void)',1)[1].split('\napp_aon_wdt_params_t',1)[0]
prefix=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#define BSP_TICKS_PER_SEC 100U
#define cli_printf(...) ((void)0)
static uint32_t s_battery_ui_ticks;
static bool s_lcd_ready=true,s_ble_started;
typedef struct {unsigned fault,power_raw,charge_state;bool input_present;} yp001_charger_status_t;
typedef struct {bool ble_known,battery_known,voltage_known,xyz_checked,xyz_known,ble_ready;uint8_t battery_percent;uint16_t battery_mv;const char *power_text;int32_t xyz_mg[3];} epaper_home_status_t;
typedef enum {YP001_BATTERY_OK,YP001_BATTERY_ADC_RANGE} yp001_battery_result_t;
static unsigned battery_count,motion_count,battery_gap,motion_gap,last_battery,last_motion;
static yp001_battery_result_t yp001_battery_read(uint16_t *mv){*mv=4200;return YP001_BATTERY_OK;}
static void yp001_charger_poll(void){}
static bool yp001_charger_display_status(yp001_charger_status_t *s){s->fault=0;s->power_raw=0x10;s->charge_state=1;s->input_present=true;return true;}
static uint8_t yp001_battery_estimate(uint16_t mv){(void)mv;return 90;}
static bool yp001_charger_is_complete(void){return false;}
static void yp_business_battery(bool known,uint8_t pct,bool charging){unsigned ms=s_battery_ui_ticks*10;(void)known;(void)pct;(void)charging;if(battery_count&&ms-last_battery>battery_gap)battery_gap=ms-last_battery;last_battery=ms;battery_count++;}
static bool gsensor_read_mg(int32_t *v){v[0]=v[1]=0;v[2]=1000;return true;}
static void yp_business_acceleration(bool known,const int32_t *v,uint32_t ms){(void)known;(void)v;if(motion_count&&ms-last_motion>motion_gap)motion_gap=ms-last_motion;last_motion=ms;motion_count++;}
static bool epaper_ui_needs_refresh(void){return true;}
static void epaper_depg0150_force_full_next(void){}
static bool epaper_lvgl_show_home(const epaper_home_status_t *s){(void)s;s_battery_ui_ticks+=48;return true;}
static void battery_display_poll(void)
'''
suffix=r'''
int main(void){for(s_battery_ui_ticks=0;s_battery_ui_ticks<6500;s_battery_ui_ticks++)battery_display_poll();
 printf("battery_count=%u motion_count=%u max_battery_gap_ms=%u max_motion_gap_ms=%u\n",battery_count,motion_count,battery_gap,motion_gap);
 return battery_count>=20&&motion_count>=80&&battery_gap<=3000&&motion_gap<=1500?0:1;}
'''
out=root/'logs/ota_first_trial_live_20261024/sample_cadence_test';out.mkdir(exist_ok=True)
source=out/'poll.c';source.write_text(prefix+function+suffix,encoding='utf8')
gcc=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
subprocess.run([str(gcc),'-std=c99','-Wall','-Wextra','-Werror',str(source),'-o',str(out/'poll.exe')],env=env,check=True)
raise SystemExit(subprocess.run([str(out/'poll.exe')],env=env).returncode)
