/* SAM | 2026-10-12 19:28 +08:00 | Host fault injection because grants must follow durable writes. */
#include "yp001_ota_port.h"
#include "yp001_ota_wire.h"
#include <stdlib.h>
#define assert(x) do { if (!(x)) { fprintf(stderr,"CHECK failed line %d: %s\n",__LINE__,#x); exit(1); } } while (0)
#include <stdio.h>
#include <string.h>
static yp001_ota_record nv;
static int load_result;
static bool store_ok=true, ready=true, completed=true;
/* SAM | 2026-10-23 19:26 +08:00 | Distinguish durable coordinator intent from Boot prepare/commit failures. */
static bool install_ready=true, install_commit=true;
/* SAM | 2026-10-27 +08:00 | Real coordinator stage tests use an explicit port-validation model; real signed receipt invalidation is exercised by the production-port suite. */
static int validation_result=1;
static unsigned validation_calls,validation_resets;
static bool validation_ready;
void yp001_ota_port_install_check_reset(void){validation_resets++;validation_ready=false;}
int yp001_ota_port_install_check_step(const yp001_ota_record *r){(void)r;validation_calls++;validation_ready=validation_result==1;return validation_result;}
bool yp001_ota_port_install_check_ready(const yp001_ota_record *r){(void)r;return validation_ready;}
/* SAM | 2026-11-06 +08:00 | Explicit sample-age fixture verifies durable ingress diagnostics independently from later gates. */
static uint32_t activation_evidence[5]={100,3001,101,1501,7};
void yp001_ota_port_activation_evidence(uint32_t out[6]){memcpy(out,activation_evidence,5*sizeof(uint32_t));out[5]=validation_result<0?12u:validation_ready?3u:0u;}

static unsigned prepare_calls, commit_calls;
/* SAM | 2026-10-24 +08:00 | Fail closed unless the physical port proves an empty, unactivated GR download. */
static bool cancel_empty_ready;
bool yp001_ota_port_cancel_empty(const yp001_ota_record *r){return cancel_empty_ready&&r->phase==OTA_DOWNLOADING&&!strcmp(r->target,"GR5526");}
/* SAM | 2026-10-23 22:30 +08:00 | Coordinator tests isolate the bounded transport; signature verification is tested with production port/crypto separately. */
void yp001_ota_port_cat_proof_reset(void){}
bool yp001_ota_port_cat_proof_present(const yp001_ota_record*r){(void)r;return ready;}
bool yp001_ota_port_cat_proof(const yp001_ota_record*r,uint32_t o,const uint8_t*b,uint32_t n,uint32_t*next){(void)b;if(strcmp(r->target,"CAT1")||o||n!=1)return false;*next=1;return true;}
bool yp001_ota_port_install_prepare(const yp001_ota_record *r){assert(r->phase==OTA_PREPARED);prepare_calls++;return install_ready;}
bool yp001_ota_port_install_commit(const yp001_ota_record *r){assert(r->phase==OTA_INSTALL_PENDING);commit_calls++;return install_commit;}
/* SAM | 2026-10-29 21:53 +08:00 | Round-2 defect 1: the PREPARED ACTIVATE commits with its pre-Flash gate snapshot; the INSTALL_PENDING resume keeps the plain commit. */
static unsigned prechecked_calls;
bool yp001_ota_port_install_commit_prechecked(const yp001_ota_record *r){prechecked_calls++;return yp001_ota_port_install_commit(r);}
void yp001_ota_port_poll(void){}
bool yp001_ota_port_power_safe(const yp001_ota_record *r){(void)r;return false;}
static bool prepared_recovery;
bool yp001_ota_port_recovery_prepared(const yp001_ota_record *r){(void)r;return prepared_recovery;}
static bool health_result_ready;
/* SAM | 2026-10-27 +08:00 | Independent Boot-stage eligibility model for quiet scheduling tests. */
static bool health_stage_ready=true;
bool yp001_ota_port_result_pending(const yp001_ota_record *r){(void)r;return health_stage_ready;}
static unsigned health_result_calls;
bool yp001_ota_port_result(const yp001_ota_record *r,yp001_ota_record *out){
 health_result_calls++;if(!health_result_ready)return false;
 assert(yp001_ota_flash_allowed());*out=*r;out->phase=OTA_COMPLETE;
 strcpy(out->actual_version,r->version);strcpy(out->outcome,"success");return true;
}
static yp001_ota_gates gates={true,true,true,false,false,false,true,70};
/* SAM | 2026-11-07 07:14 +08:00 | Model physical USB in every build because the new user power policy is shared. */
static bool bench_usb;
bool yp001_ota_port_usb_power(void){return bench_usb;}
static uint8_t quiet_offer[44];
static char reply[1025];
bool yp001_ota_port_provisioned(void){return true;}
int yp001_ota_port_load(yp001_ota_record *r){*r=nv;return load_result;}
/* SAM | 2026-10-29 21:53 +08:00 | Round-2 defect 2: a Flash write may stall the motion sampler (gates unstable right after the write). */
static bool stale_after_store;
bool yp001_ota_port_store(const yp001_ota_record *r){if(!store_ok)return false;nv=*r;load_result=1;if(stale_after_store)gates.stable=false;return true;}
void yp001_ota_port_gates(yp001_ota_gates *g){*g=gates;}
bool yp001_ota_port_source_version(const yp001_ota_record *r,char *v,size_t n){(void)r;snprintf(v,n,"1.0");return true;}
bool yp001_ota_port_package_ready(const yp001_ota_record *r){(void)r;return ready;}
bool yp001_ota_port_receive_prepare(const yp001_ota_record *r,uint32_t n){return r->epoch>0 && n==5000;}
bool yp001_ota_port_completed(const yp001_ota_record *r){(void)r;return completed;}
/* SAM | 2026-10-23 +08:00 | Challenge IO is modeled here; production port tests cover owner/freshness/health. */
bool yp001_ota_port_cat_challenge(const yp001_ota_record*r,char n[33]){if(r->phase!=OTA_INSTALL_PENDING||strcmp(r->target,"CAT1"))return false;memset(n,'a',32);n[32]=0;return true;}
bool yp001_ota_port_cat_result(const yp001_ota_record*r,const char*n,const char*v,bool ok){return r->phase==OTA_INSTALL_PENDING&&strlen(n)==32&&!strcmp(v,r->version)&&ok;}
void yp001_ota_port_reply(const char *s,size_t n){if(n==44&&!memcmp(s,"OTA2",4)){memcpy(quiet_offer,s,44);return;}assert(n<sizeof(reply));memcpy(reply,s,n);reply[n]=0;}
/* SAM | 2026-10-25 +08:00 | Existing authorization regression now traverses the real asynchronous quiet wrapper. */
#ifndef YP_TEST_EXTERNAL_QUIET
uint32_t yp001_uart_clock_ms(void){return 0;}
int yp001_ota_random(uint8_t out[16]){memset(out,0x35,16);return 0;}
void yp001_ota_measure_begin(uint32_t k,uint32_t t){(void)k;(void)t;}
void yp001_ota_measure_end(void){}
void yp001_ota_port_wire(const uint8_t*p,size_t n){(void)p;(void)n;}
bool yp001_ota_port_retire(const yp001_ota_record*r){(void)r;return false;}
static bool quiet_request(const char *line,size_t n){
 bool result=yp001_ota_handle_line(line,n);uint8_t b[44];uint32_t token;
 if(!result)return false;
 yp001_ota_poll();
 if(quiet_offer[5]==240){
  memcpy(&token,quiet_offer+12,4);
  yp001_ota_wire_encode(b,sizeof b,241,1,token,0,quiet_offer+24,16);
  yp001_ota_dispatch_wire(b,44);yp001_ota_poll();
  yp001_ota_wire_encode(b,sizeof b,243,1,token,0,quiet_offer+24,16);
  yp001_ota_dispatch_wire(b,44);yp001_ota_poll();
 }
 return result;
}
#define yp001_ota_handle_line quiet_request
#endif
static const char *wire_version="2.0", *wire_outcome="success";
static void request(const char *op,unsigned epoch,const char *target){char line[600];snprintf(line,sizeof(line),"OTA_CTL={\"op\":\"%s\",\"job\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"hash\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"target\":\"%s\",\"version\":\"%s\",\"epoch\":%u,\"outcome\":\"%s\",\"size\":5000}",op,target,wire_version,epoch,wire_outcome);assert(yp001_ota_handle_line(line,strlen(line)));}
int main(void){
 load_result=-1;yp001_ota_init();request("REQUEST",0,"CAT1");assert(strstr(reply,"DENY"));assert(!yp001_ota_power_change_allowed());
 load_result=0;yp001_ota_init();gates.known=false;request("REQUEST",0,"CAT1");assert(strstr(reply,"DENY"));gates.known=true;
 store_ok=false;request("REQUEST",0,"CAT1");assert(strstr(reply,"DENY"));assert(!yp001_ota_power_change_allowed());
 store_ok=true;load_result=0;yp001_ota_init();request("REQUEST",0,"CAT1");assert(strstr(reply,"GRANT"));assert(nv.epoch==1 && nv.phase==OTA_DOWNLOADING);
 request("REQUEST",0,"CAT1");assert(strstr(reply,"STATUS"));assert(nv.epoch==1);
 request("REQUEST",0,"GR5526");assert(strstr(reply,"DENY"));
 {char line[700];snprintf(line,sizeof line,"OTA_CTL={\"op\":\"CAT_PROOF\",\"job\":\"%s\",\"hash\":\"%s\",\"target\":\"CAT1\",\"version\":\"2.0\",\"epoch\":1,\"offset\":0,\"data\":\"ab\"}",nv.job,nv.hash);
  assert(yp001_ota_handle_line(line,strlen(line)));assert(strstr(reply,"PROOF_ACK")&&strstr(reply,"\"offset\":1"));
  gates.alarm=true;assert(yp001_ota_handle_line(line,strlen(line)));assert(strstr(reply,"DENY"));gates.alarm=false;}
 request("PREPARED",0,"CAT1");assert(strstr(reply,"DENY"));request("PREPARED",1,"CAT1");assert(nv.phase==OTA_PREPARED);request("PREPARED",1,"CAT1");assert(strstr(reply,"STATUS"));
 /* SAM | 2026-10-23 +08:00 | CAT preflight must receive fresh GR gates; a denied request must never advertise permission. */
 assert(strstr(reply,"\"commit_safe\":true"));
 gates.battery=49;request("QUERY",0,"CAT1");assert(strstr(reply,"\"commit_safe\":false"));gates.battery=70;
 request("PREPARED",0,"CAT1");assert(strstr(reply,"\"commit_safe\":false"));
 gates.battery=49;request("ACTIVATE",1,"CAT1");assert(strstr(reply,"DENY"));gates.battery=70;
 gates.call=true;request("ACTIVATE",1,"CAT1");assert(strstr(reply,"DENY"));gates.call=false;
 gates.stable=false;request("ACTIVATE",1,"CAT1");assert(strstr(reply,"DENY"));gates.stable=true;
 gates.battery=49;request("ACTIVATE",1,"CAT1");assert(strstr(reply,"DENY"));gates.battery=50;
 gates.alarm=true;request("ACTIVATE",1,"CAT1");assert(strstr(reply,"DENY"));gates.alarm=false;
 gates.activity=true;request("ACTIVATE",1,"CAT1");assert(strstr(reply,"DENY"));gates.activity=false;
 gates.peer_stable=false;request("ACTIVATE",1,"CAT1");assert(strstr(reply,"DENY"));gates.peer_stable=true;
 gates.known=false;request("ACTIVATE",1,"CAT1");assert(strstr(reply,"DENY"));gates.known=true;
 gates.battery=101;request("ACTIVATE",1,"CAT1");assert(strstr(reply,"DENY"));gates.battery=70;
 ready=false;request("ACTIVATE",1,"CAT1");assert(strstr(reply,"DENY"));ready=true;
 /* SAM | 2026-10-29 21:53 +08:00 | The GRANT advertises the gate result checked before its owner write, even if the write left a stale motion sample (1.5.1: false). */
 stale_after_store=true;request("ACTIVATE",1,"CAT1");stale_after_store=false;
 assert(strstr(reply,"GRANT")&&strstr(reply,"\"commit_safe\":true"));gates.stable=true;assert(nv.phase==OTA_INSTALL_PENDING);assert(!yp001_ota_power_change_allowed());
 request("QUERY",0,"CAT1");assert(strstr(reply,"\"commit_safe\":true"));gates.stable=false;request("QUERY",0,"CAT1");assert(strstr(reply,"\"commit_safe\":false"));gates.stable=true;
 /* SAM | 2026-10-23 +08:00 | Check real JSON dispatch: report ACK never substitutes for persistent COMPLETE. */
 {
  char line[1000];request("RESULT_QUERY",1,"CAT1");assert(strstr(reply,"RESULT_CHALLENGE")&&strstr(reply,"nonce"));
  snprintf(line,sizeof(line),"OTA_CTL={\"op\":\"CAT_RESULT\",\"job\":\"%s\",\"hash\":\"%s\",\"target\":\"CAT1\",\"version\":\"2.0\",\"epoch\":1,\"nonce\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"actual_version\":\"2.0\",\"native_phase\":\"CONFIRMED\",\"code_identity\":true,\"installation_verified\":true,\"data_ok\":true,\"durable_result\":true,\"health_ms\":120000}",nv.job,nv.hash);
  /* SAM | 2026-10-24 +08:00 | Old pending-clear frames must not satisfy the new installation-result contract. */
  { char legacy[1000],*key;strcpy(legacy,line);key=strstr(legacy,"installation_verified");assert(key);
    memmove(key+strlen("pending_clear"),key+strlen("installation_verified"),strlen(key+strlen("installation_verified"))+1);
    memcpy(key,"pending_clear",strlen("pending_clear"));
    assert(yp001_ota_handle_line(legacy,strlen(legacy)));assert(strstr(reply,"DENY")); }
  assert(yp001_ota_handle_line(line,strlen(line)));assert(strstr(reply,"RESULT_ACK"));assert(nv.phase==OTA_INSTALL_PENDING);
  *strstr(line,"120000")='0';assert(yp001_ota_handle_line(line,strlen(line)));assert(strstr(reply,"DENY"));
 }
 /* SAM | 2026-10-23 +08:00 | Native commit does not bypass a new safe reboot decision; echo the bounded request ticket only for the active CAT task. */
 {
  char line[640];
  snprintf(line,sizeof(line),"OTA_CTL={\"op\":\"REBOOT\",\"job\":\"%s\",\"hash\":\"%s\",\"target\":\"CAT1\",\"version\":\"2.0\",\"epoch\":1,\"ticket\":4}",nv.job,nv.hash);
  gates.battery=49;assert(yp001_ota_handle_line(line,strlen(line)));assert(strstr(reply,"DENY"));
  gates.battery=50;assert(yp001_ota_handle_line(line,strlen(line)));
  assert(strstr(reply,"REBOOT_GRANT")&&strstr(reply,"\"ticket\":4")&&strstr(reply,"\"commit_safe\":true"));
  request("REBOOT",1,"CAT1");assert(strstr(reply,"DENY"));
 }
 yp001_ota_init();request("REQUEST",0,"GR5526");assert(strstr(reply,"DENY"));request("ACTIVATE",1,"CAT1");assert(strstr(reply,"DENY"));
 completed=false;request("COMPLETE",1,"CAT1");assert(strstr(reply,"DENY"));completed=true;request("COMPLETE",1,"CAT1");assert(strstr(reply,"RELEASED"));assert(yp001_ota_power_change_allowed());request("COMPLETE",1,"CAT1");assert(strstr(reply,"RELEASED"));
 request("REQUEST",0,"GR5526");assert(nv.epoch==2);request("PREPARED",1,"CAT1");assert(strstr(reply,"DENY"));

 request("PREPARED",2,"GR5526");
 install_ready=false;request("ACTIVATE",2,"GR5526");assert(strstr(reply,"boot_prepare_failed")&&nv.phase==OTA_PREPARED&&prepare_calls==1);
 install_ready=true;install_commit=false;request("ACTIVATE",2,"GR5526");assert(strstr(reply,"boot_commit_failed")&&nv.phase==OTA_INSTALL_PENDING&&commit_calls==1&&prechecked_calls==1);
 install_commit=true;request("ACTIVATE",2,"GR5526");assert(strstr(reply,"GRANT")&&commit_calls==2&&prechecked_calls==1);
 wire_version="3.0";wire_outcome="fail";request("COMPLETE",2,"GR5526");assert(strstr(reply,"DENY"));
 wire_version="1.0";request("COMPLETE",2,"GR5526");assert(strstr(reply,"RELEASED"));assert(!strcmp(nv.version,"2.0"));assert(!strcmp(nv.actual_version,"1.0"));assert(!strcmp(nv.outcome,"fail"));
 wire_version="2.0";wire_outcome="success";
 assert(yp001_ota_handle_line("OTA_CTL={\"op\":\"QUERY\",\"op\":\"REQUEST\"}",strlen("OTA_CTL={\"op\":\"QUERY\",\"op\":\"REQUEST\"}")));assert(strstr(reply,"duplicate_key"));
 assert(yp001_ota_handle_line("OTA_CTL=[[[[[[[[[0]]]]]]]]]",strlen("OTA_CTL=[[[[[[[[[0]]]]]]]]]")));assert(strstr(reply,"invalid_json_depth"));
 nv.phase=OTA_INSTALL_PENDING;nv.actual_version[0]=0;nv.outcome[0]=0;nv.source_version[0]=0;load_result=1;yp001_ota_init();request("QUERY",0,"CAT1");assert(strstr(reply,"UNKNOWN"));
 memset(&nv,0xff,sizeof(nv));load_result=1;yp001_ota_init();request("QUERY",0,"CAT1");assert(strstr(reply,"UNKNOWN"));
 /* SAM | 2026-10-24 +08:00 | Cancellation requires the exact owner and empty-port proof; lost replies and resets must retain the cancelled failure. */
 load_result=0;yp001_ota_init();request("REQUEST",0,"GR5526");assert(nv.phase==OTA_DOWNLOADING);
 request("CANCEL_EMPTY",1,"GR5526");assert(strstr(reply,"DENY")&&nv.phase==OTA_DOWNLOADING);
 cancel_empty_ready=true;gates.activity=true;request("CANCEL_EMPTY",1,"GR5526");assert(strstr(reply,"DENY"));gates.activity=false;
 request("CANCEL_EMPTY",2,"GR5526");assert(strstr(reply,"stale_owner"));
 store_ok=false;request("CANCEL_EMPTY",1,"GR5526");assert(strstr(reply,"storage_error")&&nv.phase==OTA_DOWNLOADING);
 store_ok=true;load_result=1;yp001_ota_init();request("CANCEL_EMPTY",1,"GR5526");
 assert(strstr(reply,"CANCELLED")&&nv.phase==OTA_COMPLETE&&!strcmp(nv.outcome,"cancel")&&!strcmp(nv.actual_version,"1.0"));
 yp001_ota_init();request("CANCEL_EMPTY",1,"GR5526");assert(strstr(reply,"CANCELLED")&&nv.epoch==1);
 request("QUERY",0,"GR5526");assert(strstr(reply,"\"cancelled_before_install\":true")&&strstr(reply,"\"outcome\":\"fail\""));
 request("REQUEST",0,"CAT1");assert(nv.phase==OTA_DOWNLOADING&&nv.epoch==2);
 request("CANCEL_EMPTY",2,"CAT1");assert(strstr(reply,"DENY")&&nv.phase==OTA_DOWNLOADING);
 request("PREPARED",2,"CAT1");request("CANCEL_EMPTY",2,"CAT1");assert(strstr(reply,"DENY")&&nv.phase==OTA_PREPARED);
#if YP001_OTA_USB_BENCH_TEST
 /* SAM | 2026-11-07 07:14 +08:00 | Live USB replaces low battery for both components; absent USB plus 49 percent and activity still deny. */
 load_result=0;yp001_ota_init();
 gates=(yp001_ota_gates){true,true,false,false,false,false,true,49};bench_usb=true;
 request("REQUEST",0,"GR5526");request("PREPARED",1,"GR5526");
 bench_usb=false;request("ACTIVATE",1,"GR5526");assert(strstr(reply,"DENY"));bench_usb=true;
 bench_usb=false;gates.battery=49;request("ACTIVATE",1,"GR5526");assert(strstr(reply,"DENY"));bench_usb=true;
 gates.activity=true;request("ACTIVATE",1,"GR5526");assert(strstr(reply,"DENY"));gates.activity=false;
 request("ACTIVATE",1,"GR5526");assert(strstr(reply,"GRANT")&&!gates.charging);
 load_result=0;yp001_ota_init();request("REQUEST",0,"CAT1");request("PREPARED",1,"CAT1");
 request("ACTIVATE",1,"CAT1");assert(strstr(reply,"GRANT")&&!gates.charging);
 bench_usb=false;request("QUERY",0,"CAT1");assert(strstr(reply,"\"commit_safe\":false"));
 puts("USB bench GR/CAT coordinator: charging stays false, live USB and all other gates checked PASS");
#endif
 puts("coordinator fault-injection PASS");return 0;
}
