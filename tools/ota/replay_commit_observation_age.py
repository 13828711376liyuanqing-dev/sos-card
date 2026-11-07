"""SAM | 2026-10-27 +08:00 | Replay the archived pre-fix commit function with modeled authentication time; current-code acceptance uses staged integration tests."""
from pathlib import Path
import subprocess, json, os

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'logs/r6_quiet_once_20261027/commit_age_historical_replay'

def function(path, name):
    text=path.read_text(encoding='utf-8-sig')
    start=text.index(name+'(')
    start=text.rfind('\n',0,start)+1
    at=text.index('{',start);depth=1;end=at+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]

def main():
    OUT.mkdir(exist_ok=True)
    business=ROOT/'ble_app_uart_c/Src/user/business/yp001_business.c'
    port=ROOT/'tools/ota/fixtures/commit_before_staging.c'
    source='''#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
typedef struct {bool known,activity,stable;} yp_business_ota_inputs_t;
static struct {uint32_t now_ms;bool battery_known,searching,sleeping;} s;
static bool ota_keys_seen,ota_battery_seen,ota_motion_seen,ota_key_down,ota_moving;
static uint32_t ota_keys_ms,ota_battery_ms,ota_motion_ms,ota_quiet_ms;
static unsigned key_requests,consumed_keys,call_request,consumed_call;
'''+function(business,'ota_fresh')+'\n'+function(business,'yp_business_ota_inputs')+'''
typedef struct {int version,identity;} yp_boot_image;
typedef struct {int state;yp_boot_image old_image,new_image;} yp_boot;
typedef struct {int dummy;} yp001_ota_record;
typedef struct {bool known,stable,charging,alarm,call,activity,peer_stable;unsigned battery;} yp001_ota_gates;
enum {OTA_INSTALL_PENDING=3,YP_BOOT_PREPARED=1,YP_BOOT_INSTALL=2};
#define YP001_PRODUCT_VERSION "1.0.2"
static unsigned auth_ms,activations;static bool boot_reset_armed;static uint32_t boot_reset_at;
static int durable_owner(const yp001_ota_record*r,int p){(void)r;return p==3;}
static int boot_open(yp_boot*b){b->state=1;b->old_image=(yp_boot_image){1,2};b->new_image=(yp_boot_image){3,4};return 1;}
static int version_number(const char*s){(void)s;return 1;}
static int yp001_ota_running_image(int v,yp_boot_image*i){(void)v;ota_keys_ms+=auth_ms;*i=(yp_boot_image){1,2};return 0;}
static int verified_candidate(const yp001_ota_record*r,yp_boot_image*i){(void)r;ota_keys_ms+=auth_ms;*i=(yp_boot_image){3,4};return 1;}
static void yp001_ota_port_gates(yp001_ota_gates*g){yp_business_ota_inputs_t v;yp_business_ota_inputs(&v);memset(g,0,sizeof(*g));g->known=v.known;g->stable=v.stable;g->activity=v.activity;g->charging=1;g->battery=89;g->peer_stable=1;}
static int yp001_ota_commit_power(bool b){return b;}
static int yp_boot_activate(yp_boot*b){activations++;b->state=2;return 0;}
static const void*yp_business_status(void){return &s;}
/* Explicit diagnostic sink; this replay measures gate aging, not RAM snapshot publication. */
static bool install_fail(unsigned stage,const yp001_ota_record*r,const yp_boot*b,uint32_t mask){(void)stage;(void)r;(void)b;(void)mask;return false;}
'''
    # The production function dereferences the status return type; use the same minimal named status layout.
    source=source.replace('static struct {uint32_t now_ms;bool battery_known,searching,sleeping;} s;',
                          'typedef struct {uint32_t now_ms;bool battery_known,searching,sleeping;} status_t;static status_t s;')
    source=source.replace('static const void*yp_business_status','static const status_t*yp_business_status')
    source+='\n'+function(port,'yp001_ota_port_install_commit')+'''
int main(void){unsigned cases[]={0,800,1100};yp001_ota_record r={0};unsigned k;
for(k=0;k<3;k++){yp_business_ota_inputs_t v;auth_ms=cases[k];activations=0;boot_reset_armed=0;
s.now_ms=100000;s.battery_known=1;ota_keys_ms=ota_battery_ms=ota_motion_ms=100000;
ota_quiet_ms=0;ota_keys_seen=ota_battery_seen=ota_motion_seen=1;
int ok=yp001_ota_port_install_commit(&r);yp_business_ota_inputs(&v);
printf("%u %d %u %u %d\\n",auth_ms,ok,activations,ota_keys_ms-ota_motion_ms,v.known);
if((k==0&&(!ok||activations!=1))||(k>0&&(ok||activations)))return 1;
}return 0;}
'''
    (OUT/'replay.c').write_text(source,encoding='utf-8')
    gcc=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
    env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ.get('PATH',''))
    p=subprocess.run([str(gcc),'-std=c99','-Wall','-Wextra','-Werror',str(OUT/'replay.c'),'-o',str(OUT/'replay.exe')],env=env,capture_output=True,text=True)
    (OUT/'build.log').write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr
    p=subprocess.run([str(OUT/'replay.exe')],env=env,capture_output=True,text=True);assert p.returncode==0,p.stdout+p.stderr
    rows=[dict(zip(('modeled_each_auth_ms','commit_ok','activate_calls','motion_age_ms','known'),map(int,line.split()))) for line in p.stdout.splitlines()]
    report={'historical_production_functions':['ota_fresh','yp_business_ota_inputs','yp001_ota_port_install_commit'],'current_firmware_test':False,'modeled_crypto_and_io':True,'historical_cause_proven':False,'cases':rows}
    (OUT/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
