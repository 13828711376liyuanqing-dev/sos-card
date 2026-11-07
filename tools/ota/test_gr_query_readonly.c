/* SAM | 2026-10-27 +08:00 | Reproduce real QUERY-driven quiet starvation without a device or new OTA trial. */
#define YP_TEST_EXTERNAL_QUIET
#define main existing_coordinator_tests
#include "test_gr_coordinator.c"
#undef main
uint32_t yp001_uart_clock_ms(void){return 0;}
int yp001_ota_random(uint8_t out[16]){memset(out,0x35,16);return 0;}
void yp001_ota_measure_begin(uint32_t k,uint32_t t){(void)k;(void)t;}
void yp001_ota_measure_end(void){}
void yp001_ota_port_wire(const uint8_t*p,size_t n){(void)p;(void)n;}
bool yp001_ota_port_retire(const yp001_ota_record*r){(void)r;return false;}
int main(void){
 const char*q="OTA_CTL={\"op\":\"QUERY\"}";yp001_ota_record before;
 memset(&nv,0,sizeof nv);nv.epoch=4;nv.phase=OTA_INSTALL_PENDING;strcpy(nv.job,"1a092304771d1850f747237e3964fc5e071c63618f661c349494efe75e14b752");strcpy(nv.hash,"eaf020f7a88d368d3017cd2c093535beb20b35f6001a71a505cf54662ad659f4");strcpy(nv.target,"GR5526");strcpy(nv.version,"1.5.0");strcpy(nv.source_version,"1.0.2");before=nv;load_result=1;health_stage_ready=false;prepared_recovery=true;yp001_ota_init();
 for(unsigned i=0;i<20;i++){
  memset(quiet_offer,0,sizeof quiet_offer);reply[0]=0;assert(yp001_ota_handle_line(q,strlen(q)));assert(quiet_offer[5]!=240);assert(strstr(reply,"STATUS"));assert(!memcmp(&before,&nv,sizeof nv));assert(!yp001_ota_flash_allowed());assert(yp001_ota_recovery_control_allowed());
 }
 assert(prepare_calls==0&&commit_calls==0);
 const char*bad="OTA_CTL={\"op\":\"QUERY\",\"op\":\"ACTIVATE\"}";memset(quiet_offer,0,sizeof quiet_offer);assert(yp001_ota_handle_line(bad,strlen(bad)));assert(quiet_offer[5]==240);assert(!yp001_ota_recovery_control_allowed());
 char saved[sizeof reply];memcpy(saved,reply,sizeof saved);assert(yp001_ota_handle_line(q,strlen(q)));assert(!memcmp(saved,reply,sizeof saved));
 puts("PASS 20 exact QUERY replies without silence or writes; duplicate op and active quiet cannot bypass mutation gates");return 0;
}
