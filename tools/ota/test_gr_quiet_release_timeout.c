/* SAM | 2026-10-29 06:19 +08:00 | Reproduce the post-rollback GR deadlock: a result-lease handshake that CAT1 never answers (CAT1 restarting) reached phase 4 and waited for 243 forever, dropping every OTA_CTL. The fix must leave phase 4 after a bound, never touch Flash, then answer QUERY and retry. */
#define YP_TEST_EXTERNAL_QUIET
#define main existing_coordinator_tests
#include "test_gr_coordinator.c"
#undef main
static uint32_t clock_ms;
uint32_t yp001_uart_clock_ms(void){return clock_ms;}
int yp001_ota_random(uint8_t out[16]){memset(out,0x35,16);return 0;}
void yp001_ota_measure_begin(uint32_t k,uint32_t t){(void)k;(void)t;}
void yp001_ota_measure_end(void){}
void yp001_ota_port_wire(const uint8_t*p,size_t n){(void)p;(void)n;}
bool yp001_ota_port_retire(const yp001_ota_record*r){(void)r;return false;}
static uint32_t offer_token(void){uint32_t t;memcpy(&t,quiet_offer+12,4);return t;}
static void answer(uint8_t type,uint32_t token){uint8_t b[44];assert(yp001_ota_wire_encode(b,sizeof b,type,1,token,0,quiet_offer+24,16)==44);yp001_ota_dispatch_wire(b,sizeof b);}
static bool query_answered(void){const char*q="OTA_CTL={\"op\":\"QUERY\"}";reply[0]=0;assert(yp001_ota_handle_line(q,strlen(q)));return strstr(reply,"STATUS")!=NULL;}
int main(void){
 memset(&nv,0,sizeof nv);nv.epoch=4;nv.phase=OTA_INSTALL_PENDING;strcpy(nv.job,"1a092304771d1850f747237e3964fc5e071c63618f661c349494efe75e14b752");strcpy(nv.hash,"eaf020f7a88d368d3017cd2c093535beb20b35f6001a71a505cf54662ad659f4");strcpy(nv.target,"GR5526");strcpy(nv.version,"1.5.0");strcpy(nv.source_version,"1.0.2");
 load_result=1;store_ok=true;health_stage_ready=true;health_result_ready=true;yp001_ota_init();
 /* Result lease requested; CAT1 is restarting and answers nothing. */
 clock_ms=1000;memset(quiet_offer,0,sizeof quiet_offer);yp001_ota_poll();assert(quiet_offer[5]==240);uint32_t first=offer_token();
 clock_ms=3100;yp001_ota_poll();assert(quiet_offer[5]==242);            /* phase 1 timeout -> release */
 clock_ms=5200;yp001_ota_poll();assert(quiet_offer[5]==242);            /* phase 3 timeout -> phase 4 replay */
 /* Inside the bound the existing behavior holds: no Flash, QUERY dropped, no new lease. */
 clock_ms=9000;memset(quiet_offer,0,sizeof quiet_offer);yp001_ota_poll();assert(quiet_offer[5]==0);assert(!query_answered());assert(!yp001_ota_flash_allowed());
 assert(health_result_calls==0&&nv.phase==OTA_INSTALL_PENDING);
 /* After the bound GR must leave phase 4: QUERY answered again and the result lease retried. */
 /* Leaving phase 4 immediately retries the lease on the same poll (QUERY may be dropped during that 2 s handshake; CAT1 no longer latches on it). */
 clock_ms=5200+10001;memset(quiet_offer,0,sizeof quiet_offer);yp001_ota_poll();
 assert(quiet_offer[5]==240&&offer_token()!=first&&"PHASE4_NEVER_EXITS");
 /* A normal handshake now completes the result exactly once. */
 uint32_t t=offer_token();answer(241,t);yp001_ota_poll();assert(health_result_calls==1&&nv.phase==OTA_COMPLETE);assert(strstr(reply,"RELEASED"));
 answer(243,t);yp001_ota_poll();assert(!yp001_ota_flash_allowed());
 assert(query_answered());
 puts("PASS GR result-lease release timeout: phase 4 bounded, no Flash while waiting, QUERY answered and lease retried, result written once");
 return 0;
}
