/* SAM | 2026-11-07 07:14 +08:00 | Shared >=50-percent OR measured USB policy; host-only physical supply model. */

#include "yp001_ota_port.h"
#include <stdio.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x); return 1; } } while(0)
static bool live_usb;
bool yp001_ota_port_usb_power(void){return live_usb;}
#include "../../ble_app_uart_c/Src/user/charger/yp001_charger.h"
#define REG_STATUS 8
#define REG_DPM_STATUS 10
#define REG_POWER 1
static bool s_ready=true,s_stop_pending,ship_locked;
static int fail_reg=-1;
static uint8_t status_reg=4,dpm_reg=0x80,power_reg;
bool yp001_charger_ship_locked(void){return ship_locked;}
static bool read_reg(uint8_t reg,uint8_t *value){
 if(reg==fail_reg)return false;
 if(reg==REG_STATUS)*value=status_reg;else if(reg==REG_DPM_STATUS)*value=dpm_reg;
 else if(reg==REG_POWER)*value=power_reg;else return false;
 return true;
}
#include "live_input_actual.h"
int main(void){
 yp001_charger_status_t status={0};status.fault=2;
 CHECK(yp001_charger_live_input(&status)&&status.input_present&&status.power_good&&status.fault==2);
 dpm_reg=0;CHECK(yp001_charger_live_input(&status)&&!status.input_present);dpm_reg=0x80;
 status_reg=0;CHECK(yp001_charger_live_input(&status)&&!status.power_good);status_reg=6;
 CHECK(yp001_charger_live_input(&status)&&status.thermal_limit);status_reg=4;
 power_reg=0x20;CHECK(yp001_charger_live_input(&status)&&status.power_raw==0x20);power_reg=0;
 for(int i=0;i<3;i++){static const int regs[]={REG_STATUS,REG_DPM_STATUS,REG_POWER};fail_reg=regs[i];CHECK(!yp001_charger_live_input(&status));}
 fail_reg=-1;ship_locked=true;CHECK(!yp001_charger_live_input(&status));ship_locked=false;
 s_stop_pending=true;CHECK(!yp001_charger_live_input(&status));s_stop_pending=false;

 CHECK(!yp001_ota_commit_power(49));
 CHECK(yp001_ota_commit_power(50));
 CHECK(yp001_ota_commit_power(100));
 CHECK(!yp001_ota_commit_power(101));
 CHECK(!yp001_ota_commit_power(255));
 live_usb=true;
 CHECK(yp001_ota_commit_power(0));
 CHECK(yp001_ota_commit_power(49));
 CHECK(yp001_ota_commit_power(255));
 live_usb=false;CHECK(!yp001_ota_commit_power(0));
 CHECK(yp001_ota_usb_supply(true,true,false,0,0));
 CHECK(yp001_ota_usb_supply(true,true,false,0,0x10));
 CHECK(yp001_ota_usb_supply(true,true,false,2,0));
 CHECK(!yp001_ota_usb_supply(true,true,false,2,0x10));
 CHECK(!yp001_ota_usb_supply(false,true,false,0,0));
 CHECK(!yp001_ota_usb_supply(true,false,false,0,0));
 CHECK(!yp001_ota_usb_supply(true,true,true,0,0));
 CHECK(!yp001_ota_usb_supply(true,true,false,0x80,0));
 CHECK(!yp001_ota_usb_supply(true,true,false,0,0x20));
 return 0;
}
