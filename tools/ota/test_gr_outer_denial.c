/* SAM | 2026-10-26 +08:00 | Exercise the real outer quiet gate; inner RX is deliberately never entered on denial. */
#define YP_TEST_EXTERNAL_QUIET 1
#define main historical_coordinator_suite
#include "test_gr_coordinator.c"
#undef main
static unsigned wire_calls,measured;
uint32_t yp001_uart_clock_ms(void){return 1234;}
int yp001_ota_random(uint8_t out[16]){memset(out,0x35,16);return 0;}
void yp001_ota_measure_begin(uint32_t k,uint32_t t){(void)k;(void)t;++measured;}
void yp001_ota_measure_end(void){}
void yp001_ota_port_wire(const uint8_t*p,size_t n){(void)p;(void)n;++wire_calls;}
bool yp001_ota_port_retire(const yp001_ota_record*r){(void)r;return false;}
static void offer(void){
 uint8_t frame[44];uint32_t token;
 assert(yp001_ota_wire_encode(frame,sizeof frame,1,4,5,0,NULL,0)==28);
 yp001_ota_dispatch_wire(frame,28);assert(quiet_offer[5]==240);
 memcpy(&token,quiet_offer+12,4);
 assert(yp001_ota_wire_encode(frame,sizeof frame,241,1,token,0,quiet_offer+24,16)==44);
 yp001_ota_dispatch_wire(frame,44);yp001_ota_poll();
 assert(quiet_offer[5]==242);
}
static void release(void){
 uint8_t frame[44];uint32_t token;memcpy(&token,quiet_offer+12,4);
 assert(yp001_ota_wire_encode(frame,sizeof frame,243,1,token,0,quiet_offer+24,16)==44);
 yp001_ota_dispatch_wire(frame,44);
}
int main(void){
 load_result=0;yp001_ota_init();gates.peer_stable=false;offer();
 assert(quiet_offer[16]==1&&wire_calls==0&&measured==0);
 assert(yp001_ota_quiet_denial.sequence==1&&yp001_ota_quiet_denial.mask==16);
 assert(yp001_ota_quiet_denial.token==1&&yp001_ota_quiet_denial.kind==2);
 assert(yp001_ota_quiet_denial.observed_ms==1234&&yp001_ota_quiet_denial.count==1);
 assert(yp001_ota_quiet_denial.battery==70);
 release();gates.peer_stable=true;gates.alarm=true;offer();
 assert(yp001_ota_quiet_denial.count==2&&yp001_ota_quiet_denial.mask==16);
 assert(yp001_ota_quiet_denial.token==1&&wire_calls==0);
 release();gates.alarm=false;gates.known=false;gates.call=true;offer();
 assert(yp001_ota_quiet_denial.count==3&&yp001_ota_quiet_denial.mask==16);
 assert(wire_calls==0&&measured==0);
 release();gates.known=true;gates.call=false;gates.charging=false;gates.stable=false;gates.battery=0;offer();
 assert(wire_calls==1&&measured==1&&quiet_offer[16]==0);
 assert(yp001_ota_quiet_denial.count==3&&yp001_ota_quiet_denial.mask==16);
 puts("PASS outer gate: first peer denial retained; later alarms cannot overwrite; no inner RX/Flash on denial; transfer does not acquire commit-only gates");
 return 0;
}
