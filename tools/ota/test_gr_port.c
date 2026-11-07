/* SAM | 2026-10-23 +08:00 | Actual production journal with bounded fake HAL, no attached hardware. */
#include "yp001_ota_port.h"
#include "yp001_ota_wire.h"
#include "../../ble_app_uart_c/Src/user/business/yp001_business.h"
#include "yp001_ota_app_crypto.h"
#include "yp001_ota_trust.h"
#include <stdio.h>
#include <string.h>
#include <stddef.h>
#define CHECK(x) do{if(!(x)){printf("FAIL %d\n",__LINE__);return 1;}}while(0)
/* SAM | 2026-10-23 +08:00 | Board inputs/crypto are explicit host models; real signature is tested separately. */
/* SAM | 2026-10-25 +08:00 | Explicit peer-grant injection for actual Flash boundary tests. */
static bool flash_granted=true;
bool yp001_ota_flash_allowed(void){return flash_granted;}
static yp_business_status_t business;
static yp_business_ota_inputs_t input;
/* SAM | 2026-10-23 20:18 +08:00 | Explicit measured-peer model for the production source-version consumer. */
static bool peer_known;static const char *peer_version="1.0.2";
bool yp_business_cat_version(char *v,size_t n){if(!peer_known||n<strlen(peer_version)+1)return false;strcpy(v,peer_version);return true;}
/* SAM | 2026-10-23 +08:00 | Deterministic challenge source exists only in the host HAL model. */
int yp001_ota_random(uint8_t out[16]){static unsigned n;memset(out,0,16);out[0]=(uint8_t)++n;return 0;}
static unsigned char bflash[442368];static int b_erases,b_writes,native_ok;
/* SAM | 2026-10-23 22:30 +08:00 | Explicit signature model only; separate CNG/Python tests verify actual PSS. */
static int cat_proof_ok=1;
int yp001_ota_cat_proof_verify(const uint8_t*p,const uint8_t*h,uint32_t v){return cat_proof_ok&&p[0]==0x55&&h[0]==0xbb&&v==1005000?0:-1;}
/* SAM | 2026-10-23 19:26 +08:00 | Real install/journal/health paths; SDK crypto and power reset remain explicit models. */
char yp_test_product_version[16]="1.0.2";
static unsigned char aflash[442368],bootflash[40960],journalflash[8192],scratch[4096];
static uint32_t sca[6],running_version=1000002;static unsigned resets;
/* SAM | 2026-10-27 +08:00 | Model a Boot journal write whose durable completion ACK is lost, without altering production IO. */
static unsigned journal_writes,journal_fail_write;static bool journal_write_then_fail;
/* SAM | 2026-10-27 +08:00 | Count actual production result-path authentication before Boot trial. */
static unsigned running_auth_calls,native_auth_calls,image_auth_calls;
static uint32_t modeled_auth_ms;
void hal_nvic_system_reset(void){resets++;}
const yp_business_status_t *yp_business_status(void){return &business;}
void yp_business_ota_inputs(yp_business_ota_inputs_t *v){*v=input;v->known=input.known&&business.battery_known;}
/* SAM | 2026-11-07 07:14 +08:00 | Explicit physical input models for the production port; no charger IO or real module. */
void yp_business_ota_inputs_with_usb(yp_business_ota_inputs_t *v,bool usb){*v=input;v->known=input.known&&(business.battery_known||usb);}
#include "../../ble_app_uart_c/Src/user/charger/yp001_charger.h"
static bool test_usb_valid;
bool yp001_charger_live_input(yp001_charger_status_t *v){v->input_present=v->power_good=test_usb_valid;return test_usb_valid;}
bool yp001_charger_display_status(yp001_charger_status_t *v){memset(v,0,sizeof(*v));v->input_present=v->power_good=test_usb_valid;return test_usb_valid;}
/* SAM | 2026-10-25 +08:00 | Fault injection for the actual receiver permission path. */
static unsigned observations;
static uint16_t wdt_result;
void yp001_safety_observation_poll(void){observations++;}
void yp_business_ota_evidence(uint32_t out[5]){unsigned i;for(i=0;i<5;i++)out[i]=100+i;}
/* SAM | 2026-10-25 +08:00 | Distinct provenance words expose wrong-size copies and later-denial overwrites. */
void yp_business_peer_evidence(uint32_t out[12]){
 unsigned i;for(i=0;i<12;i++)out[i]=200+i;
 out[0]=business.transport_ready;out[1]=business.network;
}
uint16_t app_aon_wdt_refresh(void){return wdt_result;}
/* SAM | 2026-11-07 09:13 +08:00 | Model native hash verification in either slot after Boot swaps; check all digest bytes. */
int yp001_ota_native_verify(uint32_t a,uint32_t n,const uint8_t h[32],uint32_t v,yp_boot_image *i){native_auth_calls++;business.now_ms+=modeled_auth_ms;if(!native_ok||(a!=0x280000&&a!=0x202000)||n!=5000||v!=1005000)return -1;for(unsigned k=0;k<32;k++)if(h[k]!=0xbb)return -1;if(a==0x202000&&aflash[0]!=0x78)return -1;memset(i,0,sizeof(*i));i->size=4096;i->version=v;i->identity[0]=0x78;return 0;}
int yp001_ota_image_auth(void *c,uint32_t a,const yp_boot_image *i){(void)c;image_auth_calls++;return i&&i->size==4096&&((a==0x202000&&aflash[0]==i->identity[0])||(a==0x280000&&bflash[0]==i->identity[0]))?0:-1;}
int yp001_ota_running_image(uint32_t version,yp_boot_image *i){running_auth_calls++;business.now_ms+=modeled_auth_ms;if(version!=running_version)return -1;memset(i,0,sizeof(*i));i->size=4096;i->version=version;i->identity[0]=aflash[0];return 0;}
static unsigned char flash[8192];static int writes,fail_write,short_read;
uint32_t nvds_get_start_addr(void){return 0x2fe000u;}
void hal_flash_get_info(uint32_t*i,uint32_t*s){*i=1;*s=0x100000;}
uint32_t hal_flash_sector_size(void){return 4096;}
uint32_t hal_flash_read(uint32_t a,uint8_t*p,uint32_t n){
 if(!short_read){
  if(a==0x200000&&n==sizeof(sca)){memcpy(p,sca,n);return n;}
  if(a>=0x202000&&a-0x202000<sizeof aflash&&n<=sizeof aflash-(a-0x202000)){memcpy(p,aflash+a-0x202000,n);return n;}
  if(a>=0x2ec000&&a-0x2ec000<sizeof bootflash&&n<=sizeof bootflash-(a-0x2ec000)){memcpy(p,bootflash+a-0x2ec000,n);return n;}
  if(a>=0x2f7000&&a-0x2f7000<sizeof journalflash&&n<=sizeof journalflash-(a-0x2f7000)){memcpy(p,journalflash+a-0x2f7000,n);return n;}
  if(a>=0x2f6000&&a-0x2f6000<sizeof scratch&&n<=sizeof scratch-(a-0x2f6000)){memcpy(p,scratch+a-0x2f6000,n);return n;}
 }
 if(!short_read && a>=0x280000u && a-0x280000u<sizeof bflash && n<=sizeof bflash-(a-0x280000u)){memcpy(p,bflash+a-0x280000u,n);return n;}
 if(short_read||a<0x2f9000u||a+n>0x2fb000u)return 0;
 memcpy(p,flash+a-0x2f9000u,n);return n;
}
/* SAM | 2026-10-29 21:56 +08:00 | Round-2 defect 1 model: a Flash write stalls the motion sampler, so the business input reads unstable afterwards. */
static int fixture_stale_on_write;
uint32_t hal_flash_write(uint32_t a,const uint8_t*p,uint32_t n){
 uint32_t i;
 if(fixture_stale_on_write)input.stable=false;
 if(a>=0x2f7000&&a-0x2f7000<sizeof journalflash&&n<=sizeof journalflash-(a-0x2f7000)){
  bool failed=++journal_writes==journal_fail_write;
  if(failed&&!journal_write_then_fail)return 0;
  for(i=0;i<n;i++){journalflash[a-0x2f7000+i]&=p[i];}
  return failed?0:n;}
 if(a>=0x280000u && a-0x280000u<sizeof bflash && n<=sizeof bflash-(a-0x280000u)){
  b_writes++;for(i=0;i<n;i++)bflash[a-0x280000u+i]&=p[i];return n;
 }
 if(a<0x2f9000u||a+n>0x2fb000u)return 0;
 if(fail_write&&++writes==fail_write)return 0;
 for(i=0;i<n;i++){flash[a-0x2f9000u+i]&=p[i];}
 return n;
}
bool hal_flash_erase(uint32_t a,uint32_t n){
 if(n==4096&&(a==0x2f7000||a==0x2f8000)){memset(journalflash+a-0x2f7000,255,n);return true;}
 if(n==4096&&a>=0x280000u&&a%4096==0&&a-0x280000u<=sizeof bflash-4096){b_erases++;memset(bflash+a-0x280000u,255,n);return true;}
 if(n!=4096||(a!=0x2f9000u&&a!=0x2fa000u))return false;
 memset(flash+a-0x2f9000u,255,n);return true;
}
static unsigned char reply[540];static size_t reply_size;
void yp001_ota_uart_reply(const char*p,size_t n){if(n<=sizeof reply){memcpy(reply,p,n);reply_size=n;}}
/* SAM | 2026-10-23 +08:00 | Build a genuine old-layout CRC record, not a V2 structure with only its magic changed. */
typedef struct {uint32_t magic,generation;yp001_ota_record record;uint32_t crc,commit;} legacy_page;
static uint32_t crc(const void*p,unsigned n){const unsigned char*b=p;uint32_t c=~0u;unsigned i;while(n--){c^=*b++;for(i=0;i<8;i++)c=(c>>1)^((0u-(c&1u))&0xedb88320u);}return ~c;}
/* SAM | 2026-10-23 19:26 +08:00 | Emulate Boot's exclusive sector access; the production app backend cannot perform these A/B writes. */
static int model_read(void*c,uint32_t a,void*p,uint32_t n){(void)c;return hal_flash_read(0x200000+a,p,n)==n?0:-1;}
static int model_write(void*c,uint32_t a,const void*p,uint32_t n){unsigned char *to=0;uint32_t i;(void)c;
 if(a>=0x2000&&a-0x2000<sizeof aflash&&n<=sizeof aflash-(a-0x2000))to=aflash+a-0x2000;
 else if(a>=0x80000&&a-0x80000<sizeof bflash&&n<=sizeof bflash-(a-0x80000))to=bflash+a-0x80000;
 else if(a>=0xf6000&&a-0xf6000<sizeof scratch&&n<=sizeof scratch-(a-0xf6000))to=scratch+a-0xf6000;
 if(!to)return hal_flash_write(0x200000+a,p,n)==n?0:-1;
 for(i=0;i<n;i++)to[i]&=((const unsigned char*)p)[i];
 return 0;
}
static int model_erase(void*c,uint32_t a,uint32_t n){unsigned char *to=0;(void)c;
 if(n!=4096||a%4096)return -1;
 if(a>=0x2000&&a-0x2000<=sizeof aflash-4096)to=aflash+a-0x2000;
 else if(a>=0x80000&&a-0x80000<=sizeof bflash-4096)to=bflash+a-0x80000;
 else if(a==0xf6000)to=scratch;
 if(!to)return hal_flash_erase(0x200000+a,n)?0:-1;
 memset(to,255,n);return 0;
}
static int model_auth(void*c,uint32_t a,const yp_boot_image*i){return yp001_ota_image_auth(c,0x200000+a,i);}
/* SAM | 2026-10-27 +08:00 | Exercise actual staged read-only receipt without peer Flash authority. The crypto primitives above remain explicit hardware models. */
static int validate_activation(const yp001_ota_record *record){
 bool prior=flash_granted;flash_granted=false;yp001_ota_port_install_check_reset();
 CHECK(yp001_ota_port_install_check_step(record)==0);
 CHECK(yp001_ota_port_install_check_step(record)==0);
 CHECK(yp001_ota_port_install_check_step(record)==1);
 CHECK(yp001_ota_port_install_check_ready(record));flash_granted=prior;return 0;
}
/* SAM | 2026-10-27 +08:00 | First postboot identity pass occurs without a Flash grant; subsequent health passes must not repeat full crypto. */
static int prime_health(const yp001_ota_record *record){
 bool prior=flash_granted;flash_granted=false;
 (void)yp001_ota_port_result_pending(record);
 flash_granted=prior;return 0;
}
int main(void){
 {yp001_ota_record source;char v[16];memset(&source,0,sizeof source);strcpy(source.target,"CAT1");
  CHECK(!yp001_ota_port_source_version(&source,v,sizeof v));peer_known=true;
  CHECK(yp001_ota_port_source_version(&source,v,sizeof v)&&!strcmp(v,"1.0.2"));
  peer_known=false;CHECK(!yp001_ota_port_source_version(&source,v,sizeof v));}
 yp001_ota_record a,b;memset(bflash,255,sizeof bflash);memset(flash,255,sizeof flash);memset(&a,0,sizeof a);
 /* SAM | 2026-10-23 +08:00 | Invoke the actual foreground port; closed receiver must reply without any Flash access. */
 {unsigned char frame[540];unsigned n;
  n=(unsigned)yp001_ota_wire_encode(frame,sizeof frame,1,7,0,0,0,0);
  yp001_ota_port_wire(frame,n);CHECK(reply_size==44&&reply[5]==2&&yp001_ota_wire_valid(reply,reply_size));
  n=(unsigned)yp001_ota_wire_encode(frame,sizeof frame,3,7,1,0,0,0);
  yp001_ota_port_wire(frame,n);CHECK(reply[5]==129&&reply[25]==5);
 }
 CHECK(yp001_ota_port_provisioned());CHECK(yp001_ota_port_load(&b)==0);
 a.epoch=7;a.phase=OTA_DOWNLOADING;strcpy(a.target,"GR5526");
 flash_granted=false;CHECK(!yp001_ota_port_store(&a));CHECK(yp001_ota_port_load(&b)==0);flash_granted=true;
 CHECK(yp001_ota_port_store(&a));CHECK(yp001_ota_port_load(&b)==1&&b.epoch==7);
 a.epoch=8;CHECK(yp001_ota_port_store(&a));CHECK(yp001_ota_port_load(&b)==1&&b.epoch==8);
 fail_write=2;writes=0;a.epoch=9;CHECK(!yp001_ota_port_store(&a));
 /* Interrupted new page must retain the prior committed generation. */
 fail_write=0;CHECK(yp001_ota_port_load(&b)==1&&b.epoch==8);
 short_read=1;CHECK(yp001_ota_port_load(&b)==-1);short_read=0;
 /* SAM | 2026-10-23 +08:00 | Progress never skips sectors or changes owners, and survives coordinator phase updates. */
 {uint32_t total,offset;yp001_ota_record owner=b;
  CHECK(yp001_ota_port_progress_load(&owner,&total,&offset)&&total==0&&offset==0);
  CHECK(!yp001_ota_port_progress_store(&owner,5000,4096));
  CHECK(yp001_ota_port_progress_store(&owner,5000,0));
  CHECK(!yp001_ota_port_progress_store(&owner,5000,5000));
  CHECK(yp001_ota_port_progress_store(&owner,5000,4096));
  CHECK(!yp001_ota_port_progress_store(&owner,6000,4096));
  CHECK(!yp001_ota_port_progress_store(&owner,5000,0));
  CHECK(yp001_ota_port_progress_store(&owner,5000,5000));
  owner.phase=OTA_PREPARED;CHECK(yp001_ota_port_store(&owner));
  CHECK(yp001_ota_port_progress_load(&owner,&total,&offset)&&total==5000&&offset==5000);
  CHECK(!yp001_ota_port_progress_store(&owner,5000,5000));
  /* SAM | 2026-10-25 +08:00 | Retiring preserves progress; a different owner cannot inherit the old checkpoint. */
  owner.phase=OTA_COMPLETE;strcpy(owner.outcome,"retired");CHECK(yp001_ota_port_store(&owner));
  CHECK(yp001_ota_port_progress_load(&owner,&total,&offset)&&offset==5000);
  owner.epoch++;CHECK(!yp001_ota_port_progress_load(&owner,&total,&offset));
  CHECK(yp001_ota_port_store(&owner));CHECK(yp001_ota_port_progress_load(&owner,&total,&offset)&&total==0);
 }
 {legacy_page old;uint32_t total,offset;unsigned char snapshot[8192];
  memset(flash,255,sizeof flash);memset(&old,0,sizeof old);
  old.magic=0x594f5431u;old.generation=42;old.record=a;old.record.epoch=42;
  old.crc=crc(&old,offsetof(legacy_page,crc));memcpy(flash,&old,sizeof old);memcpy(snapshot,flash,sizeof flash);
  CHECK(yp001_ota_port_load(&b)==1&&b.epoch==42);CHECK(!memcmp(snapshot,flash,sizeof flash));
  CHECK(yp001_ota_port_progress_load(&b,&total,&offset)&&total==0&&offset==0);
  CHECK(yp001_ota_port_progress_store(&b,5000,0));CHECK(!memcmp(snapshot,flash,4096));
  CHECK(yp001_ota_port_progress_store(&b,5000,4096));
  CHECK(yp001_ota_port_progress_load(&b,&total,&offset)&&offset==4096);
 }
 /* Real port wiring: first unknown byte is protected, then RAM/Flash/durable progress and signature gating run through production callbacks. */
 {
  uint8_t data[512],frame[540];uint32_t at,n,total,durable;
  memset(flash,255,sizeof flash);memset(bflash,255,sizeof bflash);memset(&a,0,sizeof a);
  a.epoch=50;a.phase=OTA_DOWNLOADING;strcpy(a.target,"GR5526");strcpy(a.version,"1.5.0");
  memset(a.job,'a',64);memset(a.hash,'b',64);
  CHECK(yp001_ota_port_store(&a));
  input.known=true;input.stable=true;business.battery_known=true;business.battery_percent=90;
  business.call=YP_CALL_IDLE;business.transport_ready=true;business.network=YP_NET_MQTT;
  bflash[0]=0;CHECK(!yp001_ota_port_receive_prepare(&a,5000));CHECK(b_erases==0&&b_writes==0);
  bflash[0]=255;CHECK(yp001_ota_port_receive_prepare(&a,5000));memset(data,'x',sizeof data);
  /* SAM | 2026-10-25 +08:00 | Real frame rejects preserve Flash/progress and latch the precise first cause. Fixture resets only host RAM. */
  {unsigned fault;
   for(fault=0;fault<7;fault++){
    uint32_t expected=1u<<fault;
    memset((void*)&yp001_ota_rx_denial,0,sizeof yp001_ota_rx_denial);
    if(fault==0)input.known=false;
    if(fault==1)business.alarm_active=true;
    if(fault==2)business.call=YP_CALL_CONNECTED;
    if(fault==3)input.activity=true;
    if(fault==4)business.transport_ready=false;
    if(fault==5){wdt_result=9;expected=8192u;}
    /* SAM | 2026-10-25 +08:00 | A network-only downgrade differs from physical UART failure but must deny identically. */
    if(fault==6){business.network=YP_NET_IP;expected=16u;}
    n=(uint32_t)yp001_ota_wire_encode(frame,sizeof frame,4,50,2,0,data,512);
    yp001_ota_port_wire(frame,n);
    CHECK(reply[5]==129&&reply[25]==7&&yp001_ota_rx_denial.sequence==1);
    CHECK(yp001_ota_rx_denial.mask==expected&&yp001_ota_rx_denial.evidence[3]==103);
    CHECK(yp001_ota_rx_denial.accepted==0&&b_writes==0&&b_erases==0&&observations>0);
    CHECK(sizeof yp001_ota_rx_denial==116&&offsetof(yp001_ota_rx_denial_t,peer)==68);
    CHECK(yp001_ota_rx_denial.peer[0]==(uint32_t)business.transport_ready);
    CHECK(yp001_ota_rx_denial.peer[1]==(uint32_t)business.network&&yp001_ota_rx_denial.peer[11]==211);
    /* Later denials must not replace the cause/clock of the first one. */
    business.alarm_active=true;business.network=YP_NET_OFFLINE;yp001_ota_port_wire(frame,n);
    CHECK(yp001_ota_rx_denial.mask==expected&&yp001_ota_rx_denial.count==2);
    CHECK(yp001_ota_rx_denial.peer[1]==(uint32_t)(fault==6?YP_NET_IP:YP_NET_MQTT));
    input.known=true;input.activity=false;business.alarm_active=false;
    business.call=YP_CALL_IDLE;business.transport_ready=true;business.network=YP_NET_MQTT;wdt_result=0;
   }
  }
  for(at=0;at<4096;at+=512){n=(uint32_t)yp001_ota_wire_encode(frame,sizeof frame,4,50,at/512+2,at,data,512);yp001_ota_port_wire(frame,n);CHECK(reply[5]==128);}
  CHECK(b_erases==1&&b_writes==1);CHECK(yp001_ota_port_progress_load(&a,&total,&durable)&&durable==4096);
  n=(uint32_t)yp001_ota_wire_encode(frame,sizeof frame,8,50,20,0,0,0);yp001_ota_port_wire(frame,n);
  n=(uint32_t)yp001_ota_wire_encode(frame,sizeof frame,1,50,21,0,0,0);yp001_ota_port_wire(frame,n);CHECK(reply[5]==2);
  for(at=4096;at<5000;at+=512){uint32_t count=5000-at;if(count>512)count=512;n=(uint32_t)yp001_ota_wire_encode(frame,sizeof frame,4,50,at/512+2,at,data,count);yp001_ota_port_wire(frame,n);CHECK(reply[5]==128);}
  CHECK(!yp001_ota_port_package_ready(&a));native_ok=1;CHECK(yp001_ota_port_package_ready(&a));
  input.activity=true;CHECK(!yp001_ota_port_receive_prepare(&a,5000));input.activity=false;
  /* A later owner may reuse proven OTA-owned B; unknown data was never granted this ownership. */
  a.epoch++;CHECK(yp001_ota_port_store(&a));CHECK(yp001_ota_port_receive_prepare(&a,5000));
 }
 /* Application commits only metadata; a modeled Boot transition then exercises actual-version health/result handling. */
 {
  uint32_t provision[27];yp001_ota_record result;unsigned char before_a[64],before_b[64];
  memset(provision,0,sizeof provision);provision[0]=provision[1]=provision[2]=1;
  memcpy(provision+3,yp_ota_layout_pin,32);memcpy(provision+11,yp_ota_data_pin,32);memcpy(provision+19,yp_ota_public_pin,32);
  memset(bootflash,255,sizeof bootflash);memcpy(bootflash+256,provision,sizeof provision);
  memset(journalflash,255,sizeof journalflash);memset(aflash,0x11,sizeof aflash);memset(bflash,0x78,sizeof bflash);
  memset(flash,255,sizeof flash);a.epoch=70;a.phase=OTA_DOWNLOADING;strcpy(a.source_version,"1.0.2");
  CHECK(yp001_ota_port_store(&a));
  /* Establish existing owned B for the modeled second job without touching its bytes. */
  memset(bflash,255,sizeof bflash);CHECK(yp001_ota_port_progress_store(&a,5000,0));memset(bflash,0x78,sizeof bflash);
  CHECK(yp001_ota_port_progress_store(&a,5000,4096));CHECK(yp001_ota_port_progress_store(&a,5000,5000));
  a.phase=OTA_PREPARED;CHECK(yp001_ota_port_store(&a));
  CHECK(!yp001_ota_port_install_prepare(&a));
  sca[0]=sizeof bootflash;sca[2]=sca[3]=0x2ec000;
  ((uint32_t*)(bootflash+256))[0]=0;CHECK(!yp001_ota_port_install_prepare(&a));((uint32_t*)(bootflash+256))[0]=1;
  journalflash[8191]=0;CHECK(!yp001_ota_port_install_prepare(&a));journalflash[8191]=255;
  memcpy(before_a,aflash,64);memcpy(before_b,bflash,64);
  CHECK(!yp001_ota_port_install_prepare(&a));CHECK(validate_activation(&a)==0);
  {unsigned calls=running_auth_calls;
  CHECK(yp001_ota_port_install_prepare(&a));CHECK(yp001_ota_port_install_prepare(&a));
  CHECK(running_auth_calls==calls);}
  CHECK(!memcmp(before_a,aflash,64)&&!memcmp(before_b,bflash,64));
  a.phase=OTA_INSTALL_PENDING;CHECK(yp001_ota_port_store(&a));
  CHECK(yp001_ota_port_install_check_ready(&a));
  CHECK(yp001_ota_port_recovery_prepared(&a));
  {yp001_ota_record wrong=a;wrong.epoch++;CHECK(!yp001_ota_port_recovery_prepared(&wrong));wrong=a;strcpy(wrong.source_version,"1.0.3");CHECK(!yp001_ota_port_recovery_prepared(&wrong));}
  /* SAM | 2026-10-27 +08:00 | PREPARED is not a trial: health must not authenticate or write before activation. */
  { unsigned calls=running_auth_calls;business.now_ms=1000;
    CHECK(!yp001_ota_port_result_pending(&a));
    CHECK(!yp001_ota_port_result(&a,&result));CHECK(running_auth_calls==calls);
    CHECK(!yp001_ota_port_power_safe(&a));CHECK(running_auth_calls==calls);
    business.now_ms=0; }
  business.battery_percent=49;CHECK(!yp001_ota_port_install_commit(&a));business.battery_percent=50;
  /* SAM | 2026-10-27 +08:00 | A later failure must not replace the first precise gate refusal. */
  CHECK(g_ota_install_first_error[0]==1&&g_ota_install_first_error[2]==6&&g_ota_install_first_error[7]==8);
  {uint32_t first[14];unsigned i;yp001_ota_record wrong=a;wrong.epoch++;
   for(i=0;i<14;i++)first[i]=g_ota_install_first_error[i+2];
   CHECK(!yp001_ota_port_install_commit(&wrong));CHECK(g_ota_install_first_error[1]==2);
   for(i=0;i<14;i++)CHECK(first[i]==g_ota_install_first_error[i+2]);}
  {unsigned calls=running_auth_calls;
   CHECK(yp001_ota_port_install_commit(&a));CHECK(yp001_ota_port_install_commit(&a));CHECK(running_auth_calls==calls);}
  CHECK(!yp001_ota_port_result_pending(&a));
  CHECK(!yp001_ota_port_recovery_prepared(&a));
  business.now_ms=249;yp001_ota_port_poll();CHECK(!resets);business.now_ms=250;yp001_ota_port_poll();CHECK(resets==1);
  CHECK(!yp001_ota_port_result(&a,&result));
  {
   yp_boot boot;static uint32_t work[1024];static unsigned char trial_journal[8192];
   yp_boot_layout layout={0x100000,4096,0x2000,0x80000,442368,0xf6000,{0xf7000,0xf8000},0xfe000,8192};
   yp_boot_backend io={0,model_read,model_write,model_erase,model_auth};
   CHECK(!yp_boot_open(&boot,&layout,&io,work,sizeof work)&&boot.state==YP_BOOT_INSTALL);
   CHECK(!yp_boot_resume(&boot)&&boot.state==YP_BOOT_TRIAL);CHECK(!yp_boot_trial(&boot,3));
   memcpy(trial_journal,journalflash,sizeof trial_journal);
   strcpy(yp_test_product_version,"1.5.0");running_version=1005000;
   CHECK(prime_health(&a)==0);
   {yp001_ota_record wrong=a;wrong.epoch++;CHECK(!yp001_ota_port_result_pending(&wrong));}
   CHECK(prime_health(&a)==0);
   unsigned healthy_auth_calls=running_auth_calls;
   for(business.now_ms=2000;business.now_ms<122000;business.now_ms+=1000)CHECK(!yp001_ota_port_result(&a,&result));
   /* SAM | 2026-10-29 21:56 +08:00 | Round-2 defect 3: the first lease only confirms Boot (no result yet); the next one returns the result without another Boot write. */
   CHECK(!yp001_ota_port_result(&a,&result));
   CHECK(!yp_boot_open(&boot,&layout,&io,work,sizeof work)&&boot.state==YP_BOOT_CONFIRMED);
   CHECK(yp001_ota_port_result(&a,&result));
   CHECK(running_auth_calls==healthy_auth_calls);
   CHECK(result.phase==OTA_COMPLETE&&!strcmp(result.actual_version,"1.5.0")&&!strcmp(result.outcome,"success"));
   CHECK(!yp_boot_open(&boot,&layout,&io,work,sizeof work)&&boot.state==YP_BOOT_CONFIRMED);
   CHECK(yp001_ota_port_result_pending(&a));
   /* Restore only the host fixture to the preconfirmation cut point; production never rewinds journals or user data. */
   memcpy(journalflash,trial_journal,sizeof trial_journal);
   CHECK(!yp_boot_open(&boot,&layout,&io,work,sizeof work));
   CHECK(!yp_boot_trial(&boot,3));CHECK(!yp_boot_trial(&boot,3));CHECK(!yp_boot_trial(&boot,3)&&boot.state==YP_BOOT_ROLLBACK);
   CHECK(!yp_boot_resume(&boot)&&boot.state==YP_BOOT_REVERTED);
   strcpy(yp_test_product_version,"1.0.2");running_version=1000002;business.now_ms=124000;
   CHECK(prime_health(&a)==0);
   CHECK(yp001_ota_port_result(&a,&result)&&!strcmp(result.actual_version,"1.0.2")&&!strcmp(result.outcome,"fail"));
  }
 }
 memset(flash,255,sizeof flash);flash[8191]=0;CHECK(yp001_ota_port_load(&b)==-1);
 /* SAM | 2026-10-23 22:30 +08:00 | CAT proof is volatile, owner-bound, offset-bounded, rechecked before grant, and never writes a Flash slot. */
 {
  yp001_ota_record cat;uint8_t proof[904];uint32_t next;int before_b=b_writes;
  memset(flash,255,sizeof flash);memset(&cat,0,sizeof cat);cat.epoch=9;cat.phase=OTA_DOWNLOADING;
  memset(cat.job,'a',64);memset(cat.hash,'b',64);strcpy(cat.target,"CAT1");strcpy(cat.version,"1.5.0");strcpy(cat.source_version,"1.0.2");
  short_read=0;fail_write=0;CHECK(yp001_ota_port_store(&cat));memset(proof,0x55,sizeof proof);
  yp001_ota_port_cat_proof_reset();CHECK(!yp001_ota_port_package_ready(&cat));
  CHECK(!yp001_ota_port_cat_proof(&cat,1,proof,256,&next));
  CHECK(yp001_ota_port_cat_proof(&cat,0,proof,256,&next)&&next==256);
  CHECK(yp001_ota_port_cat_proof(&cat,0,proof,256,&next)&&next==256);
  proof[0]^=1;CHECK(!yp001_ota_port_cat_proof(&cat,0,proof,256,&next));proof[0]^=1;
  CHECK(yp001_ota_port_cat_proof(&cat,256,proof+256,256,&next));
  CHECK(yp001_ota_port_cat_proof(&cat,512,proof+512,256,&next));
  CHECK(!yp001_ota_port_cat_proof(&cat,768,proof,137,&next));
  CHECK(yp001_ota_port_cat_proof(&cat,768,proof+768,136,&next)&&next==904);
  CHECK(yp001_ota_port_package_ready(&cat));cat_proof_ok=0;CHECK(!yp001_ota_port_package_ready(&cat));cat_proof_ok=1;
  /* SAM | 2026-10-23 +08:00 | CAT completion needs a current challenge plus independent GR observations; a naked COMPLETE never releases. */
  {
   char nonce[33];yp001_ota_record done;unsigned i;
   cat.phase=OTA_INSTALL_PENDING;CHECK(yp001_ota_port_store(&cat));done=cat;
   strcpy(done.actual_version,"1.5.0");strcpy(done.outcome,"success");
   peer_known=true;peer_version="1.5.0";business.network=YP_NET_MQTT;business.transport_ready=true;
   input.known=true;business.alarm_active=false;business.call=YP_CALL_IDLE;
   CHECK(!yp001_ota_port_completed(&done));
   for(i=0;i<=120;i++){
    business.now_ms=200000+i*1000;
    CHECK(yp001_ota_port_cat_challenge(&cat,nonce));
    CHECK(!yp001_ota_port_cat_result(&cat,"00000000000000000000000000000000","1.5.0",true));
    CHECK(yp001_ota_port_cat_result(&cat,nonce,"1.5.0",true));
    CHECK(!yp001_ota_port_cat_result(&cat,nonce,"1.5.0",true));
    if(i<120)CHECK(!yp001_ota_port_completed(&done));
   }
   CHECK(yp001_ota_port_completed(&done));
   peer_version="1.0.2";CHECK(!yp001_ota_port_completed(&done));peer_version="1.5.0";
   yp001_ota_port_cat_proof_reset();CHECK(!yp001_ota_port_completed(&done));
  }
  cat.epoch++;CHECK(!yp001_ota_port_package_ready(&cat));cat.epoch--;
  yp001_ota_port_cat_proof_reset();CHECK(!yp001_ota_port_package_ready(&cat)&&b_writes==before_b);
 }
 puts("PASS GR production journal and volatile signed CAT proof bounds/owner/revalidation");return 0;
}
