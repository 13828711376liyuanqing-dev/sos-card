/* SAM | 2026-10-27 +08:00 | Run real coordinator phases with modeled crypto completion/physical gates, no device or new ticket. */
#define YP_TEST_EXTERNAL_QUIET 1
#define main prior_coordinator_suite
#include "test_gr_coordinator.c"
#undef main
extern volatile uint32_t g_ota_activation_trace[24];
static uint32_t now_ms;
uint32_t yp001_uart_clock_ms(void){return now_ms;}
int yp001_ota_random(uint8_t out[16]){memset(out,0x35,16);return 0;}
void yp001_ota_measure_begin(uint32_t k,uint32_t t){assert(k&&t);}
void yp001_ota_measure_end(void){}
void yp001_ota_port_wire(const uint8_t*p,size_t n){(void)p;(void)n;}
bool yp001_ota_port_retire(const yp001_ota_record*r){(void)r;return false;}
static void setup_stage(yp001_ota_phase phase){
 memset(&nv,0,sizeof nv);memset(quiet_offer,0,sizeof quiet_offer);reply[0]=0;
 nv.epoch=4;nv.phase=phase;memset(nv.job,'a',64);memset(nv.hash,'b',64);strcpy(nv.target,"GR5526");strcpy(nv.version,"2.0");strcpy(nv.source_version,"1.0");
 load_result=1;store_ok=true;ready=true;install_ready=install_commit=true;prepare_calls=commit_calls=0;
 gates=(yp001_ota_gates){true,true,true,false,false,false,true,89};bench_usb=false;now_ms=0;validation_result=0;validation_calls=validation_resets=0;yp001_ota_init();
}
static void grant(void){uint8_t frame[44];uint32_t token;memcpy(&token,quiet_offer+12,4);assert(yp001_ota_wire_encode(frame,sizeof frame,241,1,token,0,quiet_offer+24,16)==44);yp001_ota_dispatch_wire(frame,44);yp001_ota_poll();}
int main(void){
 /* SAM | 2026-11-07 07:14 +08:00 | Exercise real admission at 49/50 percent and with USB replacing low/unknown battery. */
 setup_stage(OTA_PREPARED);gates.charging=false;gates.battery=50;validation_result=1;
 request("ACTIVATE",4,"GR5526");yp001_ota_poll();assert(quiet_offer[5]==240);grant();assert(commit_calls==1);
 setup_stage(OTA_PREPARED);gates.charging=true;gates.battery=49;validation_result=1;
 request("ACTIVATE",4,"GR5526");yp001_ota_poll();assert(!quiet_offer[5]&&!commit_calls);
 now_ms=120001;yp001_ota_poll();assert(strstr(reply,"activation_safe_wait"));
 setup_stage(OTA_PREPARED);gates.charging=false;gates.battery=255;bench_usb=true;validation_result=1;
 request("ACTIVATE",4,"GR5526");yp001_ota_poll();assert(quiet_offer[5]==240);grant();assert(commit_calls==1);
 setup_stage(OTA_PREPARED);gates.battery=0;bench_usb=true;gates.alarm=true;validation_result=1;
 request("ACTIVATE",4,"GR5526");yp001_ota_poll();assert(!quiet_offer[5]&&!commit_calls);
 /* SAM | 2026-11-06 +08:00 | Admission can race fresh safety; wait without a lease or misreporting unrun crypto. */
 setup_stage(OTA_PREPARED);gates.stable=false;validation_result=1;
 request("ACTIVATE",4,"GR5526");assert(!quiet_offer[5]&&!validation_calls);
 yp001_ota_poll();assert(validation_calls==1&&!quiet_offer[5]&&!prepare_calls);
 now_ms=119999;yp001_ota_poll();assert(!reply[0]&&!prepare_calls);
 gates.stable=true;yp001_ota_poll();assert(quiet_offer[5]==240);grant();assert(prepare_calls==1&&commit_calls==1&&strstr(reply,"GRANT"));
 setup_stage(OTA_PREPARED);gates.known=false;request("ACTIVATE",4,"GR5526");
 yp001_ota_poll();assert(!validation_calls&&!quiet_offer[5]);activation_evidence[1]=7;now_ms=120001;yp001_ota_poll();
 assert(!validation_calls&&!commit_calls&&nv.phase==OTA_PREPARED&&strstr(reply,"activation_safe_wait"));
 assert(g_ota_activation_trace[14]==70u&&g_ota_activation_trace[17]==3001u&&g_ota_activation_trace[18]==101u&&g_ota_activation_trace[19]==1501u);
 assert(g_ota_activation_trace[10]==70u&&g_ota_activation_trace[1]==6u);activation_evidence[1]=3001;

 setup_stage(OTA_PREPARED);gates.stable=false;validation_result=1;request("ACTIVATE",4,"GR5526");yp001_ota_poll();
 now_ms=120001;yp001_ota_poll();assert(validation_calls==1&&!commit_calls&&strstr(reply,"activation_safe_wait"));assert(g_ota_activation_trace[13]==0&&g_ota_activation_trace[22]==1);
 setup_stage(OTA_PREPARED);gates.known=false;request("ACTIVATE",4,"GR5526");yp001_ota_poll();
 now_ms=100000;gates.known=true;validation_result=1;yp001_ota_poll();assert(quiet_offer[5]==240);grant();assert(prepare_calls==1&&commit_calls==1);
 setup_stage(OTA_INSTALL_PENDING);prepared_recovery=true;assert(yp001_ota_recovery_control_allowed());
 prepared_recovery=false;assert(!yp001_ota_recovery_control_allowed());
 prepared_recovery=true;request("ACTIVATE",4,"GR5526");assert(!yp001_ota_recovery_control_allowed());prepared_recovery=false;
 setup_stage(OTA_PREPARED);request("ACTIVATE",4,"GR5526");
 assert(!yp001_ota_power_change_allowed());
 assert(!quiet_offer[5]&&!prepare_calls&&!commit_calls&&!validation_calls&&!yp001_ota_flash_allowed());
 yp001_ota_poll();yp001_ota_poll();assert(validation_calls==2&&!quiet_offer[5]&&!prepare_calls&&!commit_calls);
 validation_result=1;gates.stable=false;yp001_ota_poll();assert(!quiet_offer[5]&&!prepare_calls);
 gates.stable=true;yp001_ota_poll();assert(quiet_offer[5]==240&&!yp001_ota_flash_allowed());
 grant();assert(prepare_calls==1&&commit_calls==1&&nv.phase==OTA_INSTALL_PENDING&&strstr(reply,"GRANT")&&!validation_ready);assert(g_ota_activation_trace[13]==0&&g_ota_activation_trace[22]==1);
 setup_stage(OTA_INSTALL_PENDING);request("ACTIVATE",4,"GR5526");validation_result=1;yp001_ota_poll();grant();assert(!prepare_calls&&commit_calls==1&&strstr(reply,"GRANT"));
 setup_stage(OTA_PREPARED);request("ACTIVATE",4,"GR5526");validation_result=-1;yp001_ota_poll();assert(!quiet_offer[5]&&!prepare_calls&&!commit_calls&&strstr(reply,"activation_validation_failed"));
 /* SAM | 2026-11-06 +08:00 | The later durable PREPARED power guard remains after this command releases its volatile validation wait. */
 assert(!yp001_ota_power_change_allowed()&&!yp001_ota_flash_allowed());
 setup_stage(OTA_PREPARED);request("ACTIVATE",4,"GR5526");now_ms=120001;yp001_ota_poll();assert(!quiet_offer[5]&&!commit_calls&&strstr(reply,"activation_validation_timeout"));
 setup_stage(OTA_PREPARED);request("ACTIVATE",4,"GR5526");validation_result=1;yp001_ota_poll();gates.alarm=true;grant();assert(!prepare_calls&&!commit_calls&&strstr(reply,"DENY")&&!validation_ready);
 setup_stage(OTA_PREPARED);request("ACTIVATE",4,"GR5526");validation_result=1;yp001_ota_poll();now_ms=2001;yp001_ota_poll();assert(!prepare_calls&&!commit_calls&&!validation_ready);assert(g_ota_activation_trace[13]==0&&g_ota_activation_trace[22]==1&&g_ota_activation_trace[1]==9);
 puts("PASS real activation stages: no lease/writes during validation, real stability wait, initial/resume, validation failure, timeout, alarm and lost grant");return 0;
}
