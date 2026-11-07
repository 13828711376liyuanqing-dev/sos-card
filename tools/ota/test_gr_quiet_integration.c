/* SAM | 2026-10-25 +08:00 | Real coordinator must defer even REQUEST persistence until CAT has physically stopped TX. */
#define YP_TEST_EXTERNAL_QUIET 1
#define main historical_coordinator_suite
#include "test_gr_coordinator.c"
#undef main
#include "yp001_ota_wire.h"
static unsigned measured;
void yp001_ota_measure_begin(uint32_t kind,uint32_t token){assert(kind&&token);measured++;}
void yp001_ota_measure_end(void){}
static uint32_t quiet_clock;
static unsigned recovered_frames;
static void recovery_sink(const uint8_t*p,size_t n,void*ctx){(void)ctx;recovered_frames++;yp001_ota_dispatch_wire(p,n);}
static void no_text(const uint8_t*p,size_t n,void*ctx){(void)p;(void)n;(void)ctx;}
static bool retire_safe=true;
bool yp001_ota_port_retire(const yp001_ota_record*r){return retire_safe&&r->phase==OTA_DOWNLOADING;}
uint32_t yp001_uart_clock_ms(void){return quiet_clock;}
int yp001_ota_random(uint8_t out[16]){memset(out,0x35,16);return 0;}
void yp001_ota_port_wire(const uint8_t *p,size_t n){(void)p;(void)n;}
static void ack(uint8_t type,uint32_t offset,bool wrong){
 uint8_t b[44],nonce[16];memset(nonce,wrong?0x36:0x35,16);
 assert(yp001_ota_wire_encode(b,sizeof b,type,1,1,offset,nonce,16)==44);
 yp001_ota_dispatch_wire(b,sizeof b);yp001_ota_poll();
}
int main(void){
 load_result=0;store_ok=true;yp001_ota_init();
 request("REQUEST",0,"CAT1");assert(load_result==0);assert(!yp001_ota_flash_allowed());
 ack(241,0,true);assert(load_result==0);
 ack(241,0,false);assert(load_result==1);assert(nv.phase==OTA_DOWNLOADING);assert(!yp001_ota_flash_allowed());
 ack(243,0,false);
 /* SAM | 2026-10-26 +08:00 | A CRC-valid matching release must close silence after RX loss even when no text newline has arrived; ordinary DATA stays quarantined. */
 {yp001_ota_mux mux={0};uint8_t frame[44],nonce[16];unsigned before=recovered_frames;memset(nonce,0x35,16);
  yp001_ota_init();request("QUERY",0,"CAT1");ack(241,0,false);yp001_ota_mux_lost(&mux);
  assert(yp001_ota_wire_encode(frame,sizeof frame,4,1,1,0,nonce,16)==44);
  for(unsigned i=0;i<44;i++)yp001_ota_mux_feed(&mux,frame[i],quiet_clock,no_text,recovery_sink,0);
  assert(recovered_frames==before);
  /* SAM | 2026-10-26 +08:00 | Wrong nonce/token must not end the old lease; a valid release must permit a fresh control transaction, not merely reach its callback. */
  {unsigned count=measured;nonce[0]^=1;
   assert(yp001_ota_wire_encode(frame,sizeof frame,243,1,1,0,nonce,16)==44);
   for(unsigned i=0;i<44;i++)yp001_ota_mux_feed(&mux,frame[i],quiet_clock,no_text,recovery_sink,0);
   request("QUERY",0,"CAT1");ack(241,0,false);assert(measured==count);nonce[0]^=1;
   assert(yp001_ota_wire_encode(frame,sizeof frame,243,1,2,0,nonce,16)==44);
   for(unsigned i=0;i<44;i++)yp001_ota_mux_feed(&mux,frame[i],quiet_clock,no_text,recovery_sink,0);
   request("QUERY",0,"CAT1");ack(241,0,false);assert(measured==count);}
  assert(yp001_ota_wire_encode(frame,sizeof frame,243,1,1,0,nonce,16)==44);
  for(unsigned i=0;i<44;i++)yp001_ota_mux_feed(&mux,frame[i],quiet_clock,no_text,recovery_sink,0);
  assert(recovered_frames==before+3);
  {unsigned count=measured;request("QUERY",0,"CAT1");
   assert(yp001_ota_wire_encode(frame,sizeof frame,241,1,2,0,nonce,16)==44);
   yp001_ota_dispatch_wire(frame,sizeof frame);yp001_ota_poll();assert(measured==count+1);
   assert(yp001_ota_wire_encode(frame,sizeof frame,243,1,2,0,nonce,16)==44);
   yp001_ota_dispatch_wire(frame,sizeof frame);yp001_ota_poll();assert(measured==count+1);}}
 /* SAM | 2026-10-26 13:08 +08:00 | Matching duplicate release ACKs are inert after phase reset: no additional Flash work or persistence. */
 {unsigned before=measured;yp001_ota_record saved=nv;
  ack(243,0,false);assert(measured==before&&!memcmp(&saved,&nv,sizeof nv));}
 load_result=0;yp001_ota_init();request("REQUEST",0,"CAT1");ack(241,1,false);assert(load_result==0);ack(243,0,false);
 load_result=0;yp001_ota_init();request("REQUEST",0,"CAT1");gates.alarm=true;ack(241,0,false);assert(load_result==0);gates.alarm=false;
 load_result=0;yp001_ota_init();request("REQUEST",0,"CAT1");quiet_clock+=2001;yp001_ota_poll();ack(241,0,false);assert(load_result==0);
 load_result=1;memset(&nv,0,sizeof nv);nv.epoch=2;nv.phase=OTA_DOWNLOADING;
 strcpy(nv.job,"2bdfc1ca8e696f2f77218982fa61b80939f6e95852aa3336bf64264feaeace8d");
 strcpy(nv.hash,"96bc08c57633b4a820fa2ed0b2df57860eefefa85596aff338b407454c1a5139");
 strcpy(nv.target,"GR5526");strcpy(nv.version,"1.5.0");strcpy(nv.source_version,"1.0.2");yp001_ota_init();
 {char line[600];snprintf(line,sizeof line,"OTA_CTL={\"op\":\"RETIRE\",\"job\":\"%s\",\"hash\":\"%s\",\"target\":\"GR5526\",\"version\":\"1.5.0\",\"epoch\":2}",nv.job,nv.hash);
 /* SAM | 2026-10-25 +08:00 | Boot refusal and a failed retirement commit must preserve the downloading owner. */
 retire_safe=false;assert(yp001_ota_handle_line(line,strlen(line)));ack(241,0,false);assert(nv.phase==OTA_DOWNLOADING);
 retire_safe=true;yp001_ota_init();store_ok=false;
 assert(yp001_ota_handle_line(line,strlen(line)));ack(241,0,false);assert(nv.phase==OTA_DOWNLOADING);
 store_ok=true;yp001_ota_init();
 assert(yp001_ota_handle_line(line,strlen(line)));ack(241,0,false);assert(nv.phase==OTA_COMPLETE&&!strcmp(nv.outcome,"retired"));}
 /* SAM | 2026-10-26 +08:00 | This board's dirty R4 B slot makes CANCEL_EMPTY inapplicable; the exact R5 owner needs its own no-B-write retirement. */
 nv.phase=OTA_DOWNLOADING;nv.outcome[0]=0;nv.actual_version[0]=0;nv.epoch=3;
 strcpy(nv.job,"5fbfa8fba57e15654dab0c62023f245c681227dd3ef481078fa681bf894edc5f");
 strcpy(nv.hash,"eaf020f7a88d368d3017cd2c093535beb20b35f6001a71a505cf54662ad659f4");yp001_ota_init();
 {char line[600];snprintf(line,sizeof line,"OTA_CTL={\"op\":\"RETIRE\",\"job\":\"%s\",\"hash\":\"%s\",\"target\":\"GR5526\",\"version\":\"1.5.0\",\"epoch\":3}",nv.job,nv.hash);
 assert(yp001_ota_handle_line(line,strlen(line)));ack(241,0,false);assert(nv.phase==OTA_COMPLETE&&!strcmp(nv.outcome,"retired"));ack(243,0,false);}
 nv.phase=OTA_INSTALL_PENDING;nv.outcome[0]=0;nv.actual_version[0]=0;load_result=1;
 health_result_ready=true;health_result_calls=0;yp001_ota_init();quiet_clock+=1000;
 /* SAM | 2026-10-27 +08:00 | PREPARED/INSTALL eligibility false must suppress the whole health quiet handshake, not just its crypto work. */
 health_stage_ready=false;
 {unsigned before=measured;uint8_t prior[44];memcpy(prior,quiet_offer,44);
  yp001_ota_poll();assert(measured==before&&health_result_calls==0&&!memcmp(prior,quiet_offer,44));}
 health_stage_ready=true;
 /* The read-only health probe is throttled even when no lease was needed. */
 quiet_clock+=1000;
 yp001_ota_poll();assert(quiet_offer[5]==240&&health_result_calls==0&&nv.phase==OTA_INSTALL_PENDING);
 ack(241,0,false);assert(health_result_calls==1&&nv.phase==OTA_COMPLETE);ack(243,0,false);
 puts("PASS real GR coordinator: deferred write, wrong nonce, grant, deny, emergency and late grant");return 0;
}
