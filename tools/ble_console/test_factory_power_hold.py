"""SAM | 2026-11-06 +08:00 | Exercise the actual power-command preamble; mocked rail remainder is not hardware evidence."""
from pathlib import Path
import os
import subprocess

root=Path(__file__).resolve().parents[2]
source=(root/'ble_app_uart_c/Src/platform/user_periph_setup.c').read_text(encoding='utf-8-sig')
part=source[source.index('int cat1_debug_power(int argc, char *argv[])'):]
part=part[:part.index('    /* SAM | 2026-10-27 +08:00 | Rail-on alone')]
unit=r'''
#include <assert.h>
#include <stdlib.h>
#undef assert
#define assert(x) do { if (!(x)) { fprintf(stderr,"assert failed: %s at %d\n",#x,__LINE__);exit(1); } } while(0)
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
static bool s_factory_power_hold,ship_locked,ota_allowed=true;
static int rail_result,rail_calls;
static struct {unsigned DATAOUT;} gpio;
#define GPIO0 (&gpio)
#define YP001_CAT1_POWER_PIN 64
static char mock_log[128];
#define cli_printf(...) ((void)snprintf(mock_log,sizeof(mock_log),__VA_ARGS__))
static bool yp001_charger_ship_locked(void){return ship_locked;}
static bool yp001_ota_power_change_allowed(void){return ota_allowed;}
'''+part+r'''
    rail_calls++;return rail_result;
}
static int command(char *op){char name[]="cat1_power";char *args[]={name,op};return cat1_debug_power(2,args);}
int main(void){
 assert(!command("hold_on")&&s_factory_power_hold&&rail_calls==1);
 for(unsigned i=0;i<4;i++){char *op[]={"off","isolate","key","reset"};assert(command(op[i])==-1);}
 assert(rail_calls==1);
 ota_allowed=false;assert(!command("hold_off")&&!s_factory_power_hold&&!ota_allowed&&rail_calls==1);
 assert(command("hold_on")==-1&&!s_factory_power_hold);
 ota_allowed=true;ship_locked=true;assert(command("hold_on")==-1&&!s_factory_power_hold);
 ship_locked=false;rail_result=-1;assert(command("hold_on")==-1&&!s_factory_power_hold);
 puts("PASS independent hold, cut/key/reset denial, release without rail-off, OTA separation and failed-on handling");
}
'''
out=root/'logs/factory_serial_tests';out.mkdir(exist_ok=True)
(out/'power_test.c').write_text(unit,encoding='utf-8')
gcc=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
subprocess.run([str(gcc),'-std=c11','-Wall','-Wextra',str(out/'power_test.c'),'-o',str(out/'power_test.exe')],env=env,check=True)
subprocess.run([str(out/'power_test.exe')],env=env,check=True)
