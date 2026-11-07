"""SAM | 2026-10-27 +08:00 | Replay archived Boot-stage guard functions; current health acceptance uses full production integration."""
from pathlib import Path
import json
import os
import subprocess
from replay_commit_observation_age import function, ROOT

out = ROOT / 'logs/r6_quiet_once_20261027/preinstall_health_historical_guard'
out.mkdir(exist_ok=True)
source = r'''
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
typedef struct {unsigned version,identity;} yp_boot_image;
typedef struct {int state;yp_boot_image old_image,new_image;} yp_boot;
typedef struct {char version[16],source_version[16],actual_version[16],outcome[16];int phase;} yp001_ota_record;
typedef struct {bool known;} yp_business_ota_inputs_t;
typedef struct {uint32_t now_ms;bool transport_ready;int network;} status_t;
enum {OTA_INSTALL_PENDING=3,OTA_COMPLETE=4,YP_BOOT_PREPARED=1,YP_BOOT_INSTALL=2,YP_BOOT_TRIAL=3,YP_BOOT_CONFIRMED=5,YP_BOOT_REVERTED=6,YP_NET_MQTT=4};
#define YP001_PRODUCT_VERSION "1.0.2"
static status_t status={10000,true,YP_NET_MQTT};
static bool result_check_started,health_started;
static uint32_t result_check_at,health_since;
static unsigned auth_calls;static int boot_state;
static const status_t *yp_business_status(void){return &status;}
static bool durable_owner(const yp001_ota_record*r,int p){(void)r;return p==3;}
static unsigned version_number(const char*s){return !strcmp(s,"1.5.0")?5:2;}
static bool boot_open(yp_boot*b){b->state=boot_state;b->old_image=(yp_boot_image){2,20};b->new_image=(yp_boot_image){5,50};return true;}
static int yp001_ota_running_image(unsigned v,yp_boot_image*i){auth_calls++;*i=(yp_boot_image){v,v==5?50:20};return 0;}
static void yp_business_ota_inputs(yp_business_ota_inputs_t*i){i->known=true;}
static int yp_boot_confirm(yp_boot*b){b->state=YP_BOOT_CONFIRMED;return 0;}
'''
source += function(ROOT/'tools/ota/fixtures/health_before_readonly_preparation.c', 'result_boot')
source += function(ROOT/'tools/ota/fixtures/health_before_readonly_preparation.c', 'yp001_ota_port_result')
source += r'''
int main(void){yp001_ota_record r={"1.5.0","1.0.2","","",3},result;int states[]={1,2,3};
for(unsigned k=0;k<3;k++){boot_state=states[k];auth_calls=0;result_check_started=false;health_started=false;
int ok=yp001_ota_port_result(&r,&result);printf("%d %u %d\n",boot_state,auth_calls,ok);
if(auth_calls!=(k==2?1u:0u)||ok)return 1;}return 0;}
'''
(out/'replay.c').write_text(source,encoding='utf-8')
gcc=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ.get('PATH',''))
build=subprocess.run([str(gcc),'-std=c99','-Wall','-Wextra','-Werror',str(out/'replay.c'),'-o',str(out/'replay.exe')],env=env,capture_output=True,text=True)
(out/'build.log').write_text(build.stdout+build.stderr)
assert build.returncode==0,build.stderr
run=subprocess.run([str(out/'replay.exe')],env=env,capture_output=True,text=True)
assert run.returncode==0,run.stdout+run.stderr
rows=[dict(zip(('boot_state','full_auth_calls','completion'),map(int,line.split()))) for line in run.stdout.splitlines()]
report={'historical_production_function':'yp001_ota_port_result','current_firmware_test':False,'hardware_crypto_stubbed':True,'historical_first_failure_proven':False,'cases':rows}
(out/'result.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
