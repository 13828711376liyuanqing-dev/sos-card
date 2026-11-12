"""SAM | 2026-11-06 +08:00 | Exercise the actual service with mocked transport, including ISR deferral and disconnect races."""
from pathlib import Path
import re
import os
import subprocess

root=Path(__file__).resolve().parents[2]
source=(root/'ble_app_uart_c/Src/user/factory/yp001_factory_ble.c').read_text(encoding='utf-8')
source=re.sub(r'^#include.*$', '', source, flags=re.M)
prefix=r'''
#include <assert.h>
#include <stdlib.h>
#undef assert
#define assert(x) do { if (!(x)) { fprintf(stderr,"assert failed: %s at %d\n",#x,__LINE__);exit(1); } } while(0)
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include "yp001_factory_protocol.h"
#include "yp001_factory_stream.h"
typedef int sdk_err_t;
#define SDK_SUCCESS 0
#define APP_IO_PIN_RESET 0
#define YP001_KEY1_TYPE 0
#define YP001_KEY1_PIN 1
#define YP001_KEY2_TYPE 0
#define YP001_KEY2_PIN 2
#define YP001_CAT1_POWER_PIN 64
#define YP001_BATTERY_OK 0
#define YP_CALL_DIALING 1
#define YP_CALL_INCOMING 2
#define YP_CALL_CONNECTED 3
static char mock_log[128];
#define APP_LOG_INFO(...) ((void)snprintf(mock_log,sizeof(mock_log),__VA_ARGS__))
#define APP_LOG_WARNING(...) ((void)0)
#define app_log_flush() ((void)0)
#define __DMB() ((void)0)
enum {GUS_EVT_TX_PORT_OPENED,GUS_EVT_TX_PORT_CLOSED,GUS_EVT_TX_DATA_SENT,GUS_EVT_RX_DATA_RECEIVED};
typedef struct {int evt_type;uint8_t conn_idx;uint16_t length;uint8_t *p_data;} gus_evt_t;
typedef struct {void (*evt_handler)(gus_evt_t*);} gus_init_t;
typedef int epaper_ui_page_t;
typedef struct {bool alarm_active,searching,transport_ready,imei_known;unsigned call,network;const char *imei;} yp_business_status_t;
typedef struct {unsigned power_raw,input_present;} yp001_charger_status_t;
static yp_business_status_t business={0};
static struct {unsigned DATAOUT;} gpio;
#define GPIO0 (&gpio)
static unsigned mask,irq,basepri,executed;static bool ota_allowed=true,left,hold,cut_during_command;
static char wire[20000];static unsigned wire_used;
static uint32_t __get_PRIMASK(void){return mask;}
static uint32_t __get_IPSR(void){return irq;}
static uint32_t __get_BASEPRI(void){return basepri;}
static void __disable_irq(void){mask=1;}
static void __set_PRIMASK(uint32_t v){mask=v;}
static const yp_business_status_t *yp_business_status(void){return &business;}
static bool yp001_charger_ship_locked(void){return false;}
static bool yp001_ota_power_change_allowed(void){return ota_allowed;}
static int app_io_read_pin(int t,int p){(void)t;return p==1&&left?0:1;}
static int yp001_battery_read(uint16_t *v){*v=4000;return 0;}
static unsigned yp001_battery_estimate(uint16_t v){(void)v;return 90;}
static bool yp001_charger_cached_status(yp001_charger_status_t *s){s->power_raw=0;s->input_present=0;return true;}
static void yp001_charger_ship_snapshot(uint8_t *p,uint32_t *t,bool *a){*p=0;*t=0;*a=false;}
static unsigned ship_starts;
static bool yp001_charger_ship_start(void){++ship_starts;return ota_allowed;}
static void yp001_charger_ship_auto_snapshot(uint8_t *p,const char **reason){*p=5;*reason="remove_card_USB";}
static bool yp001_charger_ship_prepare(void){return true;}
static bool yp001_charger_ship_confirm(uint32_t t){return t!=0;}
static bool yp001_charger_ship_cancel(void){return true;}
static bool yp001_cat1_factory_hold_active(void){return hold;}
static int cat1_debug_power(int argc,char **argv){(void)argc;if(!strcmp(argv[1],"hold_off"))hold=false;return 0;}
static bool epaper_ui_select_page(epaper_ui_page_t p){(void)p;return true;}
static int gus_service_init(gus_init_t *i){(void)i;return 0;}
static int ble_gap_disconnect(uint8_t c){(void)c;return 0;}
static int gus_tx_data_send(uint8_t c,uint8_t *p,uint16_t n){(void)c;assert(n<=20);memcpy(wire+wire_used,p,n);wire_used+=n;wire[wire_used]=0;return 0;}
void yp_factory_ble_capture(const uint8_t *,uint16_t);
void yp_factory_ble_disconnected(uint8_t);
static int cli_execute_string_result(const char *cmd){assert(!irq&&!basepri&&!mask);executed++;yp_factory_ble_capture((const uint8_t*)"FW_VERSION test\r\n",17);if(cut_during_command)yp_factory_ble_disconnected(0);(void)cmd;return 0;}
'''
main=r'''
static void open_link(void){gus_evt_t e={GUS_EVT_TX_PORT_OPENED,0,0,NULL};service_event(&e);}
static void receive(const char *line){gus_evt_t e={GUS_EVT_RX_DATA_RECEIVED,0,(uint16_t)strlen(line),(uint8_t*)line};irq=17;basepri=0x41;service_event(&e);irq=basepri=0;}
static void pump(void){for(int i=0;i<150;i++){yp_factory_ble_poll();if(tx_busy){gus_evt_t e={GUS_EVT_TX_DATA_SENT,0,0,NULL};service_event(&e);}}}
int main(void){
 open_link();receive("FT CLI 1 fw_version\n");assert(!executed);
 irq=17;yp_factory_ble_poll();assert(!executed);irq=0;
 pump();assert(executed==1 && strstr(wire,"op=CLI ok=1") && strstr(wire,"SER 46575f"));
 wire_used=0;receive("FT CLI 2 cat1_power off\n");pump();assert(executed==1&&strstr(wire,"physical_unlock"));
 wire_used=0;receive("FT CLI 3 name_store clear\n");pump();assert(executed==1&&strstr(wire,"command_not_enabled"));
 serial_enabled=true;uint8_t bytes[1000];memset(bytes,'x',sizeof(bytes));mask=1;
 yp_factory_ble_capture(bytes,sizeof(bytes));assert(mask==1&&serial_stream.dropped==744);mask=0;pump();assert(strstr(wire,"SER_DROP 744"));
 serial_enabled=true;ota_allowed=false;yp_factory_ble_poll();assert(!serial_enabled);ota_allowed=true;
 serial_enabled=true;yp_factory_ble_capture((const uint8_t*)"old-log",7);
 receive("FT SERIAL_OFF 5\n");yp_factory_ble_poll();assert(!serial_enabled&&serial_stream.read==serial_stream.write);
 unsigned before=serial_stream.write;yp_factory_ble_capture((const uint8_t*)"stopped",7);assert(serial_stream.write==before);pump();
 wire_used=0;cut_during_command=true;receive("FT CLI 4 fw_version\n");pump();assert(!port_open&&tx_size==0);
 open_link();pump();assert(wire_used==0);assert(!serial_enabled&&!granted);
 uint32_t old=session_generation;yp_factory_ble_disconnected(0);open_link();
 strcpy(pending_tx,"old-session");publish_frame(11,old);assert(tx_size==0);
 tx_busy=true;publish_frame(11,session_generation);assert(tx_size==0);tx_busy=false;
 serial_enabled=true;yp_factory_ble_capture((const uint8_t*)"BACKGROUND",10);
 serial_command=true;yp_factory_ble_capture((const uint8_t*)"COMMAND",7);serial_command=false;
 serial_frame();assert(!strncmp(tx,"SER 434f4d4d414e44",18));
 wire_used=0;receive("FT SHIP_START 90\n");pump();assert(ship_starts==1 && strstr(wire,"op=SHIP_START ok=1") && strstr(wire,"auto_phase=5"));
 ota_allowed=false;wire_used=0;receive("FT SHIP_START 91\n");pump();assert(ship_starts==2 && strstr(wire,"op=SHIP_START ok=0"));
 ota_allowed=true;cut_during_command=false;wire_used=0;unsigned count=executed;receive("FT CLI 92 charger ship start\n");pump();assert(executed==count+1 && strstr(wire,"op=CLI ok=1"));
 puts("PASS IRQ enqueue only, real CLI output framing, authorization, overflow, OTA pause and disconnect isolation");
}
'''
out=root/'logs/factory_serial_tests';out.mkdir(exist_ok=True)
(out/'service_test.c').write_text(prefix+source+main,encoding='utf-8')
gcc=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
subprocess.run([str(gcc),'-std=c11','-Wall','-Wextra','-I',str(root/'ble_app_uart_c/Src/user/factory'),str(out/'service_test.c'),'-o',str(out/'service_test.exe')],env=env,check=True)
subprocess.run([str(out/'service_test.exe')],env=env,check=True)
